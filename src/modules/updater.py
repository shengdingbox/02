"""自动更新模块 - 检测新版本 + 下载 + 应用更新

更新流程:
1. 启动时 & 每小时检测 http://103.36.63.44:9680/version.json
2. 对比本地版本号 (src/VERSION)
3. 有新版本 → 弹窗提示(含changelog) → 用户确认 → 下载update.zip
4. 解压到临时目录 → 复制覆盖 src/ → 删除临时文件 → 重启

version.json 支持分平台发布:
{
    "version": "1.3.0",
    "platforms": {
        "windows": { "version": "1.3.0", "changelog": "...", "download_url": "...", "sha256": "..." },
        "mac": { "version": "1.2.0", "changelog": "...", "download_url": "...", "sha256": "..." }
    }
}
Windows 只看 platforms.windows，Mac 只看 platforms.mac，互不干扰。
如果某平台没有条目，不提示更新。
"""

import json
import logging
import os
import shutil
import sys
import tempfile
import threading
import zipfile
from pathlib import Path

from PySide6.QtCore import QObject, Signal, QTimer, Slot

logger = logging.getLogger(__name__)

# 更新服务器地址
UPDATE_SERVER = "http://103.36.63.44:9680"
VERSION_URL = f"{UPDATE_SERVER}/version.json"

# 本地版本文件
VERSION_FILE = Path(__file__).parent.parent / "VERSION"


def get_current_version() -> str:
    """读取本地版本号"""
    if VERSION_FILE.exists():
        return VERSION_FILE.read_text(encoding="utf-8").strip()
    return "0.0.0"


def _get_platform_key() -> str:
    """获取当前平台标识（windows / mac）"""
    if sys.platform == "darwin":
        return "mac"
    return "windows"


def _compare_versions(remote: str, local: str) -> bool:
    """比较版本号，remote > local 返回 True"""
    try:
        r_parts = [int(x) for x in remote.strip().split(".")]
        l_parts = [int(x) for x in local.strip().split(".")]
        # 补齐长度
        max_len = max(len(r_parts), len(l_parts))
        r_parts += [0] * (max_len - len(r_parts))
        l_parts += [0] * (max_len - len(l_parts))
        return r_parts > l_parts
    except (ValueError, AttributeError):
        return False


def _fetch_version_info(timeout: int = 10) -> dict | None:
    """从服务器获取版本信息"""
    try:
        import urllib.request
        req = urllib.request.Request(VERSION_URL)
        req.add_header("User-Agent", "AntigravityTools/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data
    except Exception as e:
        logger.warning(f"检查更新失败: {e}")
        return None


def _download_update(url: str, dest: Path, progress_callback=None, timeout: int = 300) -> bool:
    """下载更新包，支持进度回调"""
    try:
        import urllib.request
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "AntigravityTools/1.0")

        with urllib.request.urlopen(req, timeout=timeout) as resp:
            total = int(resp.headers.get("Content-Length", 0))
            downloaded = 0
            chunk_size = 65536

            with open(dest, "wb") as f:
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    f.write(chunk)
                    downloaded += len(chunk)
                    if progress_callback and total > 0:
                        progress_callback(downloaded, total)

        return dest.exists() and dest.stat().st_size > 0
    except Exception as e:
        logger.error(f"下载更新失败: {e}")
        return False


def _verify_sha256(file_path: Path, expected: str) -> bool:
    """验证文件 SHA256"""
    if not expected:
        return True  # 没有校验值则跳过
    import hashlib
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest() == expected


def _apply_update(zip_path: Path) -> bool:
    """应用更新包 — 解压覆盖 src/ 目录

    注意：PyInstaller 打包后此功能不可用（代码在 _MEIPASS 临时目录中）。
    打包模式下提示用户到官网下载新版。
    """
    try:
        if getattr(sys, 'frozen', False):
            logger.warning("打包模式下不支持自动更新覆盖，请手动下载新版")
            return False

        project_root = Path(__file__).parent.parent.parent  # 项目根目录
        src_dir = project_root / "src"

        # 解压到临时目录
        with tempfile.TemporaryDirectory(prefix="ag_update_") as tmp_dir:
            tmp = Path(tmp_dir)
            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(tmp)

            # 查找解压后的 src 目录（可能在根目录或子目录下）
            extracted_src = tmp / "src"
            if not extracted_src.exists():
                # 可能有一层包装目录
                for sub in tmp.iterdir():
                    if sub.is_dir() and (sub / "src").exists():
                        extracted_src = sub / "src"
                        break

            if not extracted_src.exists():
                logger.error("更新包中未找到 src/ 目录")
                return False

            # 备份当前 src
            backup_dir = project_root / f"src_backup_{get_current_version()}"
            if backup_dir.exists():
                shutil.rmtree(backup_dir)
            shutil.copytree(src_dir, backup_dir)

            # 复制新文件覆盖
            for item in extracted_src.iterdir():
                dest = src_dir / item.name
                if dest.is_dir():
                    if dest.exists():
                        shutil.rmtree(dest)
                    shutil.copytree(item, dest)
                else:
                    shutil.copy2(item, dest)

            # 更新版本号文件
            version_in_zip = extracted_src.parent / "VERSION"
            if version_in_zip.exists():
                shutil.copy2(version_in_zip, VERSION_FILE)

            # 清理备份（延迟删除，避免文件锁定）
            try:
                shutil.rmtree(backup_dir)
            except Exception:
                pass

        logger.info("更新应用成功")
        return True

    except Exception as e:
        logger.error(f"应用更新失败: {e}")
        return False


class UpdateChecker(QObject):
    """自动更新检查器 — 在主线程中运行，通过信号通知UI"""

    # 信号：发现新版本 (version, changelog, download_url, sha256)
    update_available = Signal(str, str, str, str)
    # 信号：更新下载进度 (downloaded_bytes, total_bytes)
    download_progress = Signal(int, int)
    # 信号：更新完成 (success: bool, message: str)
    update_finished = Signal(bool, str)
    # 信号：检查完成但无更新 (is_manual: bool)
    no_update = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.timeout.connect(self.check_update)
        self._checking = False
        self._downloading = False
        self._manual_check = False  # 标记是否为手动检查
        self._notified_version = ""  # 已经提示过的版本号，同一版本不重复弹窗

    def start_periodic_check(self, interval_ms: int = 3600_000):
        """启动定期检查（默认1小时）"""
        # 首次延迟5秒检查（等UI完全加载）
        QTimer.singleShot(5000, self.check_update)
        self._timer.start(interval_ms)

    def stop(self):
        """停止定期检查"""
        self._timer.stop()

    @Slot()
    def check_update(self):
        """检查是否有新版本（后台线程）"""
        if self._checking or self._downloading:
            return
        self._checking = True

        def _do_check():
            current = get_current_version()
            info = _fetch_version_info()
            self._checking = False

            if not info:
                self.no_update.emit(self._manual_check)
                return

            # 分平台读取版本信息
            platform_key = _get_platform_key()
            platforms = info.get("platforms", {})

            if platforms:
                # 新格式：分平台
                platform_info = platforms.get(platform_key)
                if not platform_info:
                    # 该平台没有发布更新，不提示
                    logger.info(f"平台 {platform_key} 暂无更新信息")
                    self.no_update.emit(self._manual_check)
                    return
                remote_ver = platform_info.get("version", "0.0.0")
                changelog = platform_info.get("changelog", "")
                download_url = platform_info.get("download_url", "")
                sha256 = platform_info.get("sha256", "")
            else:
                # 兼容旧格式（无 platforms 字段）
                remote_ver = info.get("version", "0.0.0")
                changelog = info.get("changelog", "")
                download_url = info.get("download_url", "")
                sha256 = info.get("sha256", "")

            if _compare_versions(remote_ver, current):
                # 检查是否跳过了此版本
                from ..utils.store import load_setting
                skip_ver = load_setting("skip_version", "")
                if skip_ver == remote_ver and not self._manual_check:
                    logger.info(f"版本 {remote_ver} 已被跳过")
                    self.no_update.emit(self._manual_check)
                elif self._notified_version == remote_ver and not self._manual_check:
                    # 已经提示过这个版本了，用户没关窗口前不重复弹
                    logger.info(f"版本 {remote_ver} 已提示过，不重复弹窗")
                    self.no_update.emit(self._manual_check)
                else:
                    self._notified_version = remote_ver
                    self.update_available.emit(remote_ver, changelog, download_url, sha256)
            else:
                self.no_update.emit(self._manual_check)

            self._manual_check = False

        threading.Thread(target=_do_check, daemon=True).start()

    def download_and_apply(self, download_url: str, sha256: str = ""):
        """下载并应用更新（后台线程）"""
        if self._downloading:
            return
        self._downloading = True

        def _do_download():
            try:
                # 下载到临时文件
                tmp_dir = Path(tempfile.gettempdir()) / "antigravity-update"
                tmp_dir.mkdir(exist_ok=True)
                zip_path = tmp_dir / "update.zip"

                def _progress(downloaded, total):
                    self.download_progress.emit(downloaded, total)

                if not _download_update(download_url, zip_path, _progress):
                    self.update_finished.emit(False, "下载更新包失败")
                    return

                # 校验
                if sha256 and not _verify_sha256(zip_path, sha256):
                    self.update_finished.emit(False, "文件校验失败，可能被篡改")
                    return

                # 应用更新
                if _apply_update(zip_path):
                    self.update_finished.emit(True, "更新成功，需要重启应用才能生效。")
                else:
                    self.update_finished.emit(False, "应用更新失败")

            except Exception as e:
                self.update_finished.emit(False, f"更新出错: {e}")
            finally:
                self._downloading = False
                # 清理临时文件
                try:
                    tmp_dir = Path(tempfile.gettempdir()) / "antigravity-update"
                    if tmp_dir.exists():
                        shutil.rmtree(tmp_dir, ignore_errors=True)
                except Exception:
                    pass

        threading.Thread(target=_do_download, daemon=True).start()
