"""机器码生成工具 — 基于硬件信息生成唯一机器码"""

import hashlib
import platform
import uuid
import os
import logging

logger = logging.getLogger(__name__)


def _get_disk_serial() -> str:
    """获取磁盘序列号（Windows 用 wmic，macOS 用 ioreg，Linux 用 /sys）"""
    try:
        if platform.system() == "Windows":
            import subprocess
            result = subprocess.run(
                ["wmic", "diskdrive", "get", "serialnumber"],
                capture_output=True, text=True, timeout=5
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


def _get_mac_address() -> str:
    """获取第一个非回环 MAC 地址"""
    try:
        mac = uuid.getnode()
        mac_str = ":".join(f"{(mac >> ele) & 0xff:02x}" for ele in range(40, -1, -8))
        return mac_str
    except Exception:
        return ""


def _get_cpu_id() -> str:
    """获取 CPU ID"""
    try:
        if platform.system() == "Windows":
            import subprocess
            result = subprocess.run(
                ["wmic", "cpu", "get", "ProcessorId"],
                capture_output=True, text=True, timeout=5
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


def get_machine_code() -> str:
    """生成当前机器的唯一机器码

    综合磁盘序列号、MAC 地址、CPU ID、主机名等硬件信息，
    通过 SHA256 生成哈希后，再用 Base62 编码缩短长度。

    Returns:
        Base62 编码的机器码字符串（约 43 字符，前缀 buddy_）
    """
    parts = [
        _get_disk_serial(),
        _get_mac_address(),
        _get_cpu_id(),
        _get_hostname(),
        str(uuid.getnode()),  # MAC 数值形式作为兜底
    ]

    raw = "buddy|" + "|".join(parts)
    sha256_hex = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    # 将 hex 转为大整数再 Base62 编码，长度从 64 缩短到约 43
    encoded = _to_base62(int(sha256_hex, 16))
    return f"buddy_{encoded}"


def get_short_machine_code() -> str:
    """生成短机器码（取前 16 位，便于显示）"""
    return get_machine_code()[:16]
