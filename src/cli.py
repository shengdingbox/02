"""Buddy Tool CLI — 无窗口命令行模式

用法:
    python -m src.cli                      # 进入交互式命令行
    python -m src.cli --redeem BC_xxxx      # 直接兑换卡密
    python -m src.cli --start               # 直接启动代理服务（自动获取BuddyKey）
    python -m src.cli --credits             # 查询积分
    python -m src.cli --port 8002           # 设置端口

交互式命令:
    help              显示帮助
    status            查看当前状态
    credits           查询积分余额
    redeem <卡密>     兑换卡密
    start             启动代理服务（自动获取BuddyKey）
    stop              停止代理服务
    port <端口号>     设置代理端口
    config            显示当前配置
    quit              退出
"""

import sys
import os
import logging
import threading

# 确保日志输出到控制台
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)

# 全局代理服务实例
_proxy_server = None


def _print_banner():
    print("=" * 50)
    print("  Buddy Tool CLI — 命令行模式")
    print("=" * 50)
    print()


def _print_help():
    print("""
可用命令:
  help              显示帮助
  status            查看当前状态
  credits           查询积分余额
  redeem <卡密>     兑换卡密 (例: redeem BC_xxxx)
  start             启动代理服务（自动获取BuddyKey）
  stop              停止代理服务
  port <端口号>     设置代理端口 (例: port 8002)
  config            显示当前配置
  quit / exit       退出
""")


def _init():
    """初始化数据库"""
    from .utils.store import init_db
    init_db()


def _cmd_status():
    """查看当前状态"""
    from .utils.store import load_setting
    from .modules.proxy_server import ProxyDatabase
    from .modules.updater import get_current_version

    version = get_current_version()
    port = load_setting("proxy_port", "8002")

    print(f"版本: v{version}")
    print(f"代理端口: {port}")

    # 服务状态
    global _proxy_server
    if _proxy_server and _proxy_server._running:
        print(f"服务状态: ✅ 运行中 (http://127.0.0.1:{port})")
    else:
        print(f"服务状态: ⏹ 已停止")

    # 积分
    try:
        db = ProxyDatabase.get_instance()
        balance = db.get_cached_credits_balance()
        print(f"积分余额: {balance:.2f}")
    except Exception:
        print("积分余额: --")

    # 机器码
    from .utils.machine import get_machine_code
    print(f"机器码: {get_machine_code()}")
    print()


def _cmd_credits():
    """查询积分余额"""
    print("正在查询积分...")
    from .utils.server_api import get_credits
    result = get_credits()
    if result and "credits" in result:
        print(f"积分余额: {result.get('credits', 0):.2f}")
        print(f"累计充值: {result.get('totalRecharged', 0):.0f}")
        print(f"已用: {result.get('totalUsed', 0):.0f}")
        print(f"今日: {result.get('todayUsed', 0):.0f}")
    else:
        err = result.get("error", "未知错误") if result else "无响应"
        print(f"查询失败: {err}")
    print()


def _cmd_redeem(card_key: str):
    """兑换卡密"""
    if not card_key:
        print("用法: redeem <卡密>")
        print("例: redeem BC_xxxx\n")
        return

    print(f"正在兑换卡密: {card_key}...")
    from .utils.server_api import redeem
    result = redeem(card_key)
    if result and result.get("success"):
        print(f"✅ 兑换成功！")
        print(f"  充值金额: {result.get('amount', 0)}")
        print(f"  当前余额: {result.get('balanceCredits', 0)}")
    else:
        err = result.get("error") or result.get("message") or "未知错误" if result else "无响应"
        print(f"❌ 兑换失败: {err}")
    print()


def _cmd_stop():
    """停止代理服务"""
    global _proxy_server
    if not _proxy_server or not _proxy_server._running:
        print("服务未运行\n")
        return

    _proxy_server.stop()
    print("✅ 服务已停止\n")


def _cmd_port(port_str: str):
    """设置端口"""
    if not port_str:
        print("用法: port <端口号>")
        print("例: port 8002\n")
        return

    try:
        port = int(port_str)
        if port < 1024 or port > 65535:
            print("端口号范围: 1024-65535\n")
            return
    except ValueError:
        print(f"无效端口号: {port_str}\n")
        return

    from .utils.store import save_setting
    save_setting("proxy_port", str(port))
    print(f"✅ 端口已设置为 {port}\n")


def _cmd_config():
    """显示当前配置"""
    from .utils.store import load_setting

    print("当前配置:")
    print(f"  代理端口: {load_setting('proxy_port', '8002')}")
    print(f"  模型前缀: {load_setting('model_prefix', '')}")
    print(f"  目标 WorkBuddy: {load_setting('config_target_workbuddy', 'true')}")
    print(f"  目标 CodeBuddy: {load_setting('config_target_codebuddy', 'true')}")
    print(f"  自动备份: {load_setting('config_auto_backup', 'true')}")
    print()


def _run_interactive():
    """交互式命令行循环"""
    _print_banner()
    _print_help()

    while True:
        try:
            line = input("buddy> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].lower()
        args = parts[1:]

        if cmd in ("quit", "exit"):
            break
        elif cmd == "help":
            _print_help()
        elif cmd == "status":
            _cmd_status()
        elif cmd == "credits":
            _cmd_credits()
        elif cmd == "redeem":
            _cmd_redeem(args[0] if args else "")
        elif cmd == "start":
            _cmd_start()
        elif cmd == "stop":
            _cmd_stop()
        elif cmd == "port":
            _cmd_port(args[0] if args else "")
        elif cmd == "config":
            _cmd_config()
        else:
            print(f"未知命令: {cmd}，输入 help 查看帮助\n")

    # 退出前停止服务
    if _proxy_server and _proxy_server._running:
        _proxy_server.stop()
    print("再见！")


def main():
    """CLI 入口"""
    _init()

    # 解析命令行参数
    args = sys.argv[1:]

    if not args:
        # 无参数 → 交互模式
        _run_interactive()
        return

    # 单次命令模式
    if args[0] == "--redeem":
        if len(args) < 2:
            print("用法: python -m src.cli --redeem <卡密>")
            return
        _cmd_redeem(args[1])
    elif args[0] == "--start":
        _cmd_start()
        # 启动后保持运行
        print("服务运行中，按 Ctrl+C 退出...")
        try:
            import time
            while _proxy_server and _proxy_server._running:
                time.sleep(1)
        except KeyboardInterrupt:
            _cmd_stop()
    elif args[0] == "--credits":
        _cmd_credits()
    elif args[0] == "--port":
        _cmd_port(args[1] if len(args) > 1 else "")
    elif args[0] in ("--help", "-h"):
        print(__doc__)
    else:
        print(f"未知参数: {args[0]}")
        print(__doc__)


if __name__ == "__main__":
    main()
