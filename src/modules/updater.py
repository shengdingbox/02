"""自动更新模块 - 检测新版本并打开浏览器跳转下载

更新流程:
1. 启动时 & 每小时检测更新（POST /api/version/check 加密接口）
2. 服务端返回 has_update=true → 弹窗提示(含changelog) → 用户确认 → 打开浏览器跳转 download_url
"""

import logging
import sys
import threading
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer, Slot

logger = logging.getLogger(__name__)

# 本地版本文件
VERSION_FILE = Path(__file__).parent.parent / "VERSION"


def get_current_version() -> str:
    """读取本地版本号

    源码模式: src/VERSION（项目根目录下）
    打包模式: Nuitka onefile 解压后 VERSION 通过 --include-data-file 打包进来
    """
    candidates = [
        VERSION_FILE,                                    # 源码: <root>/src/VERSION
        Path(__file__).parent / "VERSION",               # 同目录
        Path(__file__).parent.parent / "VERSION",        # src/VERSION
        Path(__file__).parent.parent.parent / "VERSION", # 根目录 VERSION
    ]
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
        candidates.extend([
            exe_dir / "src" / "VERSION",
            exe_dir / "VERSION",
        ])
    if hasattr(sys, "_MEIPASS"):
        meipass = Path(sys._MEIPASS)
        candidates.extend([
            meipass / "src" / "VERSION",
            meipass / "VERSION",
        ])
    for candidate in candidates:
        try:
            if candidate.is_file():
                ver = candidate.read_text(encoding="utf-8").strip()
                if ver:
                    return ver
        except Exception:
            continue
    return "0.0.0"


def _get_platform_key() -> str:
    """获取当前平台标识（windows / mac）。"""
    return "mac" if sys.platform == "darwin" else "windows"


def _compare_versions(remote: str, local: str) -> bool:
    """比较版本号，remote > local 返回 True"""
    try:
        r_parts = [int(x) for x in remote.strip().split(".")]
        l_parts = [int(x) for x in local.strip().split(".")]
        max_len = max(len(r_parts), len(l_parts))
        r_parts += [0] * (max_len - len(r_parts))
        l_parts += [0] * (max_len - len(l_parts))
        return r_parts > l_parts
    except (ValueError, AttributeError):
        return False


def _fetch_version_info() -> dict | None:
    """获取版本信息 — 仅使用服务端 /api/version/check 接口

    服务端返回 has_update / download_url / changelog 等，
    检测到新版本后由 UI 层打开浏览器跳转 download_url。
    """
    from ..utils.server_api import check_version

    current = get_current_version()
    platform_key = _get_platform_key()
    api_platform = "mac" if platform_key == "mac" else "win"

    try:
        ver_info = check_version(current_version=current, platform=api_platform)
    except Exception as e:
        logger.warning(f"服务端版本检查接口异常: {e}")
        return None

    if not ver_info or ver_info.get("error"):
        logger.warning(f"服务端版本检查失败: {ver_info.get('error', '无响应') if ver_info else '无响应'}")
        return None

    if not ver_info.get("has_update"):
        logger.info(f"服务端版本检查: 当前 {current} 已是最新")
        return None

    download_url = str(ver_info.get("download_url", "")).strip()
    latest_ver = str(ver_info.get("latest_version") or ver_info.get("version", "")).strip()
    changelog = str(ver_info.get("changelog", ""))

    if not latest_ver or not download_url:
        logger.warning("服务端版本检查: has_update=true 但缺少 version 或 download_url")
        return None

    logger.info(f"服务端版本检查: {current} → {latest_ver}（源: API）")
    return {
        "version": latest_ver,
        "platforms": {
            platform_key: {
                "version": latest_ver,
                "changelog": changelog,
                "download_url": download_url,
                "sha256": "",
            }
        },
        "source": "api",
    }


class UpdateChecker(QObject):
    """自动更新检查器 — 在主线程中运行，通过信号通知UI"""

    # 信号：发现新版本 (version, changelog, download_url, sha256)
    update_available = Signal(str, str, str, str)
    # 信号：检查完成但无更新 (is_manual: bool)
    no_update = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._checking = False
        self._manual_check = False
        self._notified_version = ""

    def start_periodic_check(self, interval_ms: int = 3600_000):
        """启动时检查一次（不再定时轮询）"""
        QTimer.singleShot(5000, self.check_update)

    def stop(self):
        """停止定期检查"""
        self._timer.stop()

    @Slot()
    def check_update(self):
        """检查是否有新版本（后台线程）"""
        if self._checking:
            return
        self._checking = True

        def _do_check():
            current = get_current_version()
            info = _fetch_version_info()
            self._checking = False

            if not info:
                self.no_update.emit(self._manual_check)
                return

            platform_key = _get_platform_key()
            platforms = info.get("platforms", {})

            if platforms:
                platform_info = platforms.get(platform_key)
                if not platform_info:
                    logger.info(f"平台 {platform_key} 暂无更新信息")
                    self.no_update.emit(self._manual_check)
                    return
                remote_ver = platform_info.get("version", "0.0.0")
                changelog = platform_info.get("changelog", "")
                download_url = platform_info.get("download_url", "")
                sha256 = platform_info.get("sha256", "")
            else:
                remote_ver = info.get("version", "0.0.0")
                changelog = info.get("changelog", "")
                download_url = info.get("download_url", "")
                sha256 = info.get("sha256", "")

            if _compare_versions(remote_ver, current):
                from ..utils.store import load_setting
                skip_ver = load_setting("skip_version", "")
                if skip_ver == remote_ver and not self._manual_check:
                    logger.info(f"版本 {remote_ver} 已被跳过")
                    self.no_update.emit(self._manual_check)
                elif self._notified_version == remote_ver and not self._manual_check:
                    logger.info(f"版本 {remote_ver} 已提示过，不重复弹窗")
                    self.no_update.emit(self._manual_check)
                else:
                    self._notified_version = remote_ver
                    self.update_available.emit(remote_ver, changelog, download_url, sha256)
            else:
                self.no_update.emit(self._manual_check)

            self._manual_check = False

        threading.Thread(target=_do_check, daemon=True).start()
