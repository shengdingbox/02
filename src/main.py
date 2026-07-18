"""Buddy Tool - 多平台 IDE 工具管理器

入口文件 - 使用 python -m src.main 运行
"""

import atexit
import os
import signal
import sys
import logging

from PySide6.QtWidgets import QApplication
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from .main_window import MainWindow


def _is_gui_mode():
    """检测是否以 GUI 模式运行（无控制台）或 PyInstaller 打包模式"""
    if getattr(sys, 'frozen', False):
        return True
    # macOS: pythonw 不带 .exe 后缀
    exe_name = os.path.basename(sys.executable).lower()
    return exe_name == "pythonw" or exe_name == "pythonw.exe"


def _setup_logging():
    """配置日志 - 统一输出到控制台"""
    log_format = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    date_fmt = "%H:%M:%S"
    logging.basicConfig(level=logging.INFO, format=log_format, datefmt=date_fmt)


logger = logging.getLogger(__name__)

# 全局引用主窗口，用于 atexit 和信号清理
_main_window = None


def _force_cleanup():
    """强制清理所有资源（atexit 和信号处理时调用）"""
    global _main_window
    if _main_window:
        # 注意：不杀 WorkBuddy！它是独立应用，关闭本软件不应影响它
        # 停止代理服务器
        try:
            if hasattr(_main_window, '_proxy_page') and _main_window._proxy_page:
                _main_window._proxy_page._cleanup()
        except Exception:
            pass


def _signal_handler(signum, frame):
    """信号处理：Ctrl+C 或系统关闭信号"""
    logger.info(f"收到信号 {signum}，正在退出...")
    _force_cleanup()
    os._exit(0)


def _check_single_instance() -> bool:
    """检查是否已有实例在运行，如有则提示并返回 False
    
    使用 QtNetwork 的 QLocalSocket/QLocalServer 实现单实例锁，
    比文件锁/PID 更可靠，且能唤醒已运行窗口。
    """
    from PySide6.QtNetwork import QLocalSocket

    _single_server = None

    # 尝试连接已有服务器
    socket = QLocalSocket()
    socket.connectToServer("buddy-tool-single-instance")
    socket.waitForConnected(500)

    if socket.state() == QLocalSocket.ConnectedState:
        # 已有实例在运行，发送唤醒信号
        socket.write(b"SHOW")
        socket.flush()
        socket.waitForBytesWritten(1000)
        socket.disconnectFromServer()
        return False

    # 没有已有实例，创建本地服务器监听
    from PySide6.QtNetwork import QLocalServer

    _single_server = QLocalServer()
    _single_server.listen("buddy-tool-single-instance")

    # 保存到全局以便 main() 中使用
    global _single_instance_server
    _single_instance_server = _single_server

    return True


# 单实例服务器引用
_single_instance_server = None


def main():
    """应用入口"""
    _setup_logging()

    # CLI 模式：第一个参数是 cli 子命令时，走命令行不启动 GUI
    if len(sys.argv) >= 2 and sys.argv[1] in ("info", "credits", "redeem", "start", "config", "help", "--help", "-h"):
        # Linux 下避免 Qt xcb 插件加载失败（无 X11 环境）
        if sys.platform.startswith('linux'):
            os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

        # 打包后 --windows-console-mode=disable 模式下，需要动态分配控制台
        if sys.platform == 'win32' and not sys.stdin.isatty():
            import ctypes
            import io
            kernel32 = ctypes.windll.kernel32
            # 附加到父进程的控制台（从 cmd 运行时）
            if kernel32.AttachConsole(-1) == 0:
                # 附加失败则分配新控制台
                kernel32.AllocConsole()
            # 重定向 stdout/stderr 到控制台
            try:
                # 打开 CONOUT$ 并重定向
                conout = ctypes.c_void_p(kernel32.CreateFileW(
                    b"CONOUT$\x00".decode('ascii'),
                    0x40000000,  # GENERIC_WRITE
                    0x00000003,  # FILE_SHARE_READ | FILE_SHARE_WRITE
                    None,
                    3,           # OPEN_EXISTING
                    0,
                    None,
                ))
                if conout.value:
                    # 重定向标准输出
                    kernel32.SetStdHandle(-11, conout)  # STD_OUTPUT_HANDLE
                    # 重定向标准错误
                    conerr = ctypes.c_void_p(kernel32.CreateFileW(
                        b"CONOUT$\x00".decode('ascii'),
                        0x40000000, 3, None, 3, 0, None,
                    ))
                    if conerr.value:
                        kernel32.SetStdHandle(-12, conerr)  # STD_ERROR_HANDLE
                    # 重新绑定 Python 的 sys.stdout/stderr
                    sys.stdout = io.TextIOWrapper(
                        io.FileIO(conout.value, 'w'), encoding='utf-8', errors='replace'
                    )
                    sys.stderr = sys.stdout
            except Exception:
                pass

        from .cli import main as cli_main
        sys.exit(cli_main())

    # 注册 atexit 清理（即使异常退出也尝试清理）
    atexit.register(_force_cleanup)

    # 注册信号处理（Ctrl+C / 系统关闭）
    try:
        signal.signal(signal.SIGINT, _signal_handler)
        signal.signal(signal.SIGTERM, _signal_handler)
    except (OSError, ValueError):
        pass  # 某些环境不允许注册信号

    # 高 DPI 支持
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setApplicationName("Buddy Tool")
    app.setOrganizationName("Buddy")

    # 单实例检查
    if not _check_single_instance():
        logger.info("已有 Buddy Tool 实例在运行，退出重复启动")
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.warning(None, "提示", "Buddy Tool 已在运行中！\n如需使用，请在系统托盘或任务栏中找到已打开的窗口。")
        sys.exit(0)

    # 设置默认字体（跨平台）
    import platform
    if platform.system() == "Darwin":
        font = QFont("PingFang SC", 13)  # macOS 中文字体
    else:
        font = QFont("Microsoft YaHei", 10)  # Windows 中文字体
    app.setFont(font)

    # 创建主窗口
    global _main_window
    _main_window = MainWindow()
    _main_window.show()

    # 监听单实例服务器的唤醒信号（第二次启动时显示窗口）
    global _single_instance_server
    if _single_instance_server:
        def _on_new_connection():
            client = _single_instance_server.nextPendingConnection()
            if client:
                client.waitForReadyRead(1000)
                data = client.readAll().data()
                client.disconnectFromServer()
                if data == b"SHOW":
                    logger.info("收到唤醒信号，显示主窗口")
                    _main_window.show()
                    _main_window.activateWindow()
                    _main_window.raise_()
        _single_instance_server.newConnection.connect(_on_new_connection)

    logger.info("Buddy Tool 已启动")

    # 启动时环境检测（代理软件 / Hook 工具 / 系统代理）
    try:
        from .utils.env_check import check_environment, format_env_warnings
        env_result = check_environment()
        env_text = format_env_warnings(env_result)
        if env_text:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.warning(_main_window, "环境检测", env_text)
    except Exception as e:
        logger.warning(f"环境检测失败: {e}")

    # 启动时补交未上报的使用量记录
    try:
        from .utils.usage_reporter import flush_pending_reports_async
        flush_pending_reports_async()
    except Exception as e:
        logger.warning(f"补交使用量记录失败: {e}")

    # 运行 Qt 事件循环
    ret = app.exec()

    # 事件循环退出后，执行清理
    _force_cleanup()

    # 给非 daemon 线程 2 秒时间退出，超时则强制终止
    import threading
    non_daemon = [t for t in threading.enumerate() if t is not threading.main_thread() and t.is_alive() and not t.daemon]
    if non_daemon:
        logger.info(f"等待 {len(non_daemon)} 个线程退出...")
        for t in non_daemon:
            t.join(timeout=2.0)
        still_alive = [t for t in threading.enumerate() if t is not threading.main_thread() and t.is_alive() and not t.daemon]
        if still_alive:
            logger.warning(f"仍有 {len(still_alive)} 个线程未退出，强制终止进程")
            os._exit(ret)

    sys.exit(ret)


if __name__ == "__main__":
    main()
