"""机器码生成工具 — 基于硬件信息生成唯一机器码

持久化策略：
- 首次启动时计算机器码并保存到 proxy_db.key 的 settings.machine_code 字段
- 后续启动优先从 proxy_db.key 读取，避免因硬件信息读取顺序变化导致机器码漂移
- 这样换网络、网卡变化都不会影响已绑定的机器码
"""

import hashlib
import platform
import os
import logging

logger = logging.getLogger(__name__)

# Windows 下隐藏子进程窗口的标志
_NO_WINDOW = 0x08000000 if platform.system() == "Windows" else 0


def _get_disk_serial() -> str:
    """获取磁盘序列号（Windows 用 wmic，macOS 用 ioreg，Linux 用 /sys）"""
    try:
        if platform.system() == "Windows":
            import subprocess
            result = subprocess.run(
                ["wmic", "diskdrive", "get", "serialnumber"],
                capture_output=True, text=True, timeout=5,
                creationflags=_NO_WINDOW,
            )
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if lines:
                # 跳过标题行，取第一个序列号
                serials = [l for l in lines if l.lower() != "serialnumber"]
                if serials:
                    return serials[0]
        elif platform.system() == "Darwin":
            import subprocess
            result = subprocess.run(
                ["ioreg", "-rd1", "-c", "IOPlatformIODevice"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.splitlines():
                if "IOPlatformSerialNumber" in line:
                    parts = line.split('"')
                    if len(parts) >= 4:
                        return parts[-2]
        elif platform.system() == "Linux":
            # 尝试读取 /sys/class/dmi/id/product_serial
            try:
                with open("/sys/class/dmi/id/product_serial", "r") as f:
                    return f.read().strip()
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"获取磁盘序列号失败: {e}")
    return ""


def _get_cpu_id() -> str:
    """获取 CPU ID"""
    try:
        if platform.system() == "Windows":
            import subprocess
            result = subprocess.run(
                ["wmic", "cpu", "get", "ProcessorId"],
                capture_output=True, text=True, timeout=5,
                creationflags=_NO_WINDOW,
            )
            lines = [l.strip() for l in result.stdout.strip().splitlines() if l.strip()]
            if lines:
                ids = [l for l in lines if l.lower() != "processorid"]
                if ids:
                    return ids[0]
        elif platform.system() == "Darwin":
            import subprocess
            result = subprocess.run(
                ["sysctl", "-n", "machdep.cpu.brand_string"],
                capture_output=True, text=True, timeout=5
            )
            return result.stdout.strip()
        elif platform.system() == "Linux":
            try:
                with open("/proc/cpuinfo", "r") as f:
                    for line in f:
                        if line.lower().startswith("model name"):
                            return line.split(":")[-1].strip()
            except Exception:
                pass
    except Exception as e:
        logger.debug(f"获取 CPU ID 失败: {e}")
    return ""


def _get_hostname() -> str:
    """获取主机名"""
    try:
        return platform.node() or os.uname().nodename
    except Exception:
        return ""


def _to_base62(num: int) -> str:
    """将大整数转为 Base62 字符串（0-9, a-z, A-Z），更短且不可逆"""
    chars = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
    if num == 0:
        return "0"
    result = []
    while num > 0:
        num, rem = divmod(num, 62)
        result.append(chars[rem])
    return "".join(reversed(result))


_cached_machine_code = None


def _load_cached_machine_code() -> str:
    """从 proxy_db.key 读取已保存的机器码（如果有）"""
    try:
        # 延迟导入，避免循环依赖
        from ..modules.proxy_server import ProxyDatabase
        db = ProxyDatabase.get_instance()
        settings = db.get_settings()
        return settings.get("machine_code", "") or ""
    except Exception as e:
        logger.debug(f"从 proxy_db.key 读取机器码失败: {e}")
        return ""


def _persist_machine_code(code: str) -> None:
    """将机器码保存到 proxy_db.key"""
    try:
        from ..modules.proxy_server import ProxyDatabase
        db = ProxyDatabase.get_instance()
        db.update_settings({"machine_code": code})
    except Exception as e:
        logger.debug(f"保存机器码到 proxy_db.key 失败: {e}")


def _compute_machine_code() -> str:
    """根据硬件信息计算机器码（不含 MAC 地址，避免网络变化影响）

    综合磁盘序列号、CPU ID、主机名，通过 SHA256 哈希后 Base62 编码。
    """
    parts = [
        _get_disk_serial(),
        _get_cpu_id(),
        _get_hostname(),
    ]
    raw = "buddy|" + "|".join(parts)
    sha256_hex = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    encoded = _to_base62(int(sha256_hex, 16))
    return f"buddy_{encoded}"


def get_machine_code() -> str:
    """生成当前机器的唯一机器码

    持久化逻辑：
    1. 优先从 proxy_db.key 读取已保存的机器码
    2. 若无记录，则基于硬件信息重新计算
    3. 计算后立即保存到 proxy_db.key，后续启动直接复用

    这样换网络、网卡变化都不会影响已绑定的机器码。
    首次计算后缓存到内存，避免重复 IO。

    Returns:
        Base62 编码的机器码字符串（约 43 字符，前缀 buddy_）
    """
    global _cached_machine_code
    if _cached_machine_code is not None:
        return _cached_machine_code

    # 1. 尝试从 proxy_db.key 读取
    cached = _load_cached_machine_code()
    if cached:
        _cached_machine_code = cached
        return cached

    # 2. 重新计算
    code = _compute_machine_code()
    _cached_machine_code = code

    # 3. 保存到 proxy_db.key
    _persist_machine_code(code)
    return code


def get_short_machine_code() -> str:
    """生成短机器码（取前 16 位，便于显示）"""
    return get_machine_code()[:16]
