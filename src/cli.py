"""Buddy Tool CLI - 命令行操作入口

在 Linux 或终端环境下使用，不影响 GUI 正常运行。
用法：
  python -m src.cli <command> [args]

命令：
  info          展示当前全部信息（端口号、积分、配置、API Key）
  credits       查询积分
  redeem        卡密充值
  start         开启代理服务
  config        展示配置 JSON
"""

import sys
import os
import json
import logging

logger = logging.getLogger(__name__)


def _print_header(title: str):
    print(f"\n{'='*50}")
    print(f"  {title}")
    print(f"{'='*50}")


def _print_kv(key: str, value, indent: int = 0):
    prefix = "  " * indent
    if isinstance(value, (dict, list)):
        print(f"{prefix}{key}:")
        print(f"{prefix}  {json.dumps(value, ensure_ascii=False, indent=2)}")
    else:
        print(f"{prefix}{key}: {value}")


def _get_machine_code():
    from .utils.machine import get_machine_code
    return get_machine_code()


def cmd_credits(args):
    """查询积分"""
    _print_header("积分查询")
    from .utils.server_api import get_credits

    user_key = _get_machine_code()
    print(f"机器码: {user_key}")
    print("正在查询...")

    result = get_credits(user_key=user_key)
    if result.get("error"):
        print(f"❌ 查询失败: {result['error']}")
        return 1

    print(f"\n✅ 查询成功:")
    _print_kv("剩余积分", result.get("credits", 0))
    _print_kv("累计充值", result.get("totalRecharged", 0))
    _print_kv("累计使用", result.get("totalUsed", 0))
    _print_kv("今日使用", result.get("todayUsed", 0))
    _print_kv("今日排名", result.get("todayRank", 0))

    # 同时显示本地缓存
    try:
        from .modules.proxy_server import ProxyDatabase
        db = ProxyDatabase.get_instance()
        cached = db.get_cached_credits()
        if cached:
            print(f"\n（本地缓存）:")
            _print_kv("剩余积分", cached.get("credits", 0))
    except Exception:
        pass
    return 0


def cmd_redeem(args):
    """卡密充值"""
    if len(args) < 1:
        print("用法: python -m src.cli redeem <卡密>")
        print("示例: python -m src.cli redeem BC_xxxxx")
        return 1

    card_key = args[0]
    _print_header("卡密充值")
    from .utils.server_api import redeem

    user_key = _get_machine_code()
    print(f"机器码: {user_key}")
    print(f"卡密: {card_key}")
    print("正在兑换...")

    result = redeem(card_key=card_key, user_key=user_key)
    if result.get("error"):
        print(f"❌ 兑换失败: {result['error']}")
        return 1

    if result.get("success"):
        print(f"\n✅ 兑换成功!")
        _print_kv("卡密", result.get("cardKey", ""))
        _print_kv("兑换金额", result.get("amount", 0))
        _print_kv("当前余额", result.get("balanceCredits", 0))
    else:
        msg = result.get("message") or result.get("error") or "未知错误"
        print(f"❌ 兑换失败: {msg}")
        return 1
    return 0


def cmd_start(args):
    """开启代理服务"""
    _print_header("启动代理服务")
    from .modules.proxy_server import ProxyServer, ProxyDatabase
    from .utils.store import load_setting

    port = int(load_setting("proxy_port", "8002"))
    host = "0.0.0.0"

    print(f"端口: {port}")
    print(f"地址: http://127.0.0.1:{port}/v1/chat/completions")

    db = ProxyDatabase.get_instance()

    # 检查是否有上游 Key
    upstream_keys = db.get_upstream_keys()
    if not upstream_keys:
        print("\n⚠️  没有上游 Key，尝试获取 BuddyKey...")
        from .utils.server_api import get_buddykey
        user_key = _get_machine_code()
        result = get_buddykey(user_key=user_key)
        if result.get("success"):
            buddy_key = result.get("buddyKey", "")
            balance = result.get("balance", 0)
            print(f"✅ 获取 BuddyKey 成功，余额: {balance}")

            # 保存上游 Key 到数据库
            import secrets as _sec
            from datetime import datetime as _dt
            db.add_upstream_key({
                "key_id": f"bk_{_sec.token_hex(4)}",
                "api_key": buddy_key,
                "label": f"BuddyKey (余额 {balance:.1f})",
                "status": "active",
                "used_count": 0,
                "points": str(balance),
                "points_updated_at": _dt.now().isoformat(),
                "created_at": _dt.now().isoformat(),
            })

            # 同步积分到本地缓存（关键！否则请求时会因余额为 0 被拒绝）
            db.save_cached_credits({"credits": float(balance)})
        else:
            err = result.get("error") or result.get("message") or "未知错误"
            print(f"❌ 获取 BuddyKey 失败: {err}")
            return 1

    server = ProxyServer(host=host, port=port, mode="local")

    if server.is_running:
        print("⚠️  服务已在运行中")
    else:
        if server.start():
            print(f"\n✅ 服务已启动: http://{host}:{port}")
            print(f"   接口地址: http://{host}:{port}/v1/chat/completions")
        else:
            print("❌ 服务启动失败")
            return 1

    # 显示子 API Key
    sub_keys = db.get_sub_api_keys()
    if sub_keys:
        print(f"\nAPI Key:")
        for sk in sub_keys:
            _print_kv("Key", sk.get("api_key", ""))
            _print_kv("状态", "启用" if sk.get("is_active") else "禁用")

    print("\n按 Ctrl+C 停止服务...")
    try:
        import time
        while server.is_running:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n正在停止服务...")
        server.stop()
        print("✅ 服务已停止")
    return 0


def cmd_config(args):
    """展示配置 JSON"""
    _print_header("客户端配置")
    from .modules.proxy_server import ProxyDatabase, SUPPORTED_MODELS, MODEL_CONTEXT_LENGTHS, MODEL_MAX_OUTPUT_TOKENS
    from .utils.store import load_setting

    port = int(load_setting("proxy_port", "8002"))
    db = ProxyDatabase.get_instance()
    sub_keys = db.get_sub_api_keys()
    api_key = sub_keys[0].get("api_key", "") if sub_keys else ""
    url = f"http://127.0.0.1:{port}/v1/chat/completions"

    # 优先从服务端获取模型列表
    models = []
    try:
        from .utils.server_api import get_models_list
        result = get_models_list()
        if result and not result.get("error") and result.get("models"):
            for m in result["models"]:
                model_id = m.get("id", "")
                if not model_id:
                    continue
                models.append({
                    "id": model_id,
                    "name": m.get("name", model_id),
                    "vendor": "Buddy",
                    "apiKey": api_key,
                    "url": url,
                    "maxInputTokens": m.get("maxInputTokens", 128000),
                    "maxOutputTokens": m.get("maxOutputTokens", 8192),
                    "supportsToolCall": m.get("supportsToolCall", True),
                    "supportsImages": m.get("supportsImages", True),
                    "supportsReasoning": m.get("supportsReasoning", True),
                })
    except Exception as e:
        print(f"⚠️  从服务端获取模型列表失败: {e}")

    # fallback 本地硬编码
    if not models:
        _name_map = {
            "auto": "自动模式（智能选择）",
            "deepseek-v4-pro": "DeepSeek V4 Pro",
            "deepseek-v4-flash": "DeepSeek V4 Flash",
            "deepseek-v3-2-volc": "DeepSeek V3.2",
            "deepseek-v3-1": "DeepSeek V3.1",
            "deepseek-v3-0324": "DeepSeek V3-0324",
            "deepseek-r1": "DeepSeek R1",
            "glm-5.2": "GLM-5.2",
            "glm-5.1": "GLM-5.1",
            "glm-5.0": "GLM-5.0",
            "glm-5.0-turbo": "GLM-5.0 Turbo",
            "glm-5v-turbo": "GLM-5v Turbo",
            "glm-4.7": "GLM-4.7",
            "glm-4.6": "GLM-4.6",
            "minimax-m3": "MiniMax M3",
            "minimax-m2.7": "MiniMax M2.7",
            "minimax-m2.5": "MiniMax M2.5",
            "kimi-k2.6": "Kimi K2.6",
            "kimi-k2.5": "Kimi K2.5",
            "kimi-k2.7": "Kimi K2.7",
            "hy3": "Hy3",
            "hy3-preview": "Hy3 Preview",
            "hunyuan-chat": "Hunyuan Chat",
            "hunyuan-2.0-thinking": "Hunyuan 2.0 Thinking",
        }
        for m in SUPPORTED_MODELS:
            models.append({
                "id": m,
                "name": _name_map.get(m, m),
                "vendor": "Buddy",
                "apiKey": api_key,
                "url": url,
                "maxInputTokens": MODEL_CONTEXT_LENGTHS.get(m, 128000),
                "maxOutputTokens": MODEL_MAX_OUTPUT_TOKENS.get(m, 8192),
                "supportsToolCall": True,
                "supportsImages": True,
                "supportsReasoning": True,
            })

    config = {"models": models}
    print(json.dumps(config, ensure_ascii=False, indent=2))
    return 0


def cmd_info(args):
    """展示当前全部信息"""
    _print_header("当前信息")
    from .modules.proxy_server import ProxyDatabase
    from .utils.store import load_setting, init_db
    from .modules.updater import get_current_version

    # 初始化数据库
    init_db()

    # 基本信息
    print("\n📋 基本信息:")
    _print_kv("版本号", get_current_version())
    _print_kv("机器码", _get_machine_code(), indent=1)

    # 端口和地址
    port = int(load_setting("proxy_port", "8002"))
    print(f"\n🔌 代理服务:")
    _print_kv("端口", port, indent=1)
    _print_kv("接口地址", f"http://127.0.0.1:{port}/v1/chat/completions", indent=1)

    # 积分
    print(f"\n💎 积分:")
    # 本地缓存
    try:
        db = ProxyDatabase.get_instance()
        cached = db.get_cached_credits()
        if cached:
            _print_kv("剩余积分（缓存）", cached.get("credits", 0), indent=1)
            _print_kv("累计充值", cached.get("totalRecharged", 0), indent=1)
            _print_kv("累计使用", cached.get("totalUsed", 0), indent=1)
            _print_kv("今日使用", cached.get("todayUsed", 0), indent=1)
        else:
            print("  （无本地缓存，使用 'credits' 命令查询）")
    except Exception as e:
        print(f"  读取缓存失败: {e}")

    # API Key
    print(f"\n🔑 API Key:")
    try:
        db = ProxyDatabase.get_instance()
        sub_keys = db.get_sub_api_keys()
        if sub_keys:
            for sk in sub_keys:
                _print_kv("Key", sk.get("api_key", ""), indent=1)
                _print_kv("状态", "启用" if sk.get("is_active") else "禁用", indent=1)
        else:
            print("  （未配置）")
    except Exception as e:
        print(f"  读取失败: {e}")

    # 上游 Key
    print(f"\n🔗 上游 Key:")
    try:
        upstream_keys = db.get_upstream_keys()
        if upstream_keys:
            for uk in upstream_keys:
                _print_kv("Key ID", uk.get("key_id", ""), indent=1)
                _print_kv("标签", uk.get("label", ""), indent=1)
                _print_kv("状态", uk.get("status", ""), indent=1)
                _print_kv("积分", uk.get("points", ""), indent=1)
        else:
            print("  （未配置）")
    except Exception as e:
        print(f"  读取失败: {e}")

    # 设置
    print(f"\n⚙️  设置:")
    try:
        settings = db.get_settings()
        if settings:
            for k, v in settings.items():
                _print_kv(k, v, indent=1)
        else:
            print("  （无）")
    except Exception as e:
        print(f"  读取失败: {e}")

    # 配置 JSON 预览
    print(f"\n📄 配置 JSON 预览:")
    print("  （使用 'config' 命令查看完整配置）")

    print()
    return 0


COMMANDS = {
    "info": ("展示当前全部信息", cmd_info),
    "credits": ("查询积分", cmd_credits),
    "redeem": ("卡密充值 <卡密>", cmd_redeem),
    "start": ("开启代理服务", cmd_start),
    "config": ("展示配置 JSON", cmd_config),
}


def main():
    """CLI 入口"""
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print("Buddy Tool CLI - 命令行操作")
        print(f"\n用法: python -m src.cli <command> [args]")
        print(f"\n命令:")
        for cmd, (desc, _) in COMMANDS.items():
            print(f"  {cmd:12s} {desc}")
        print(f"\n示例:")
        print(f"  python -m src.cli info")
        print(f"  python -m src.cli credits")
        print(f"  python -m src.cli redeem BC_xxxxx")
        print(f"  python -m src.cli start")
        print(f"  python -m src.cli config")
        return 0

    cmd_name = sys.argv[1]
    cmd_args = sys.argv[2:]

    if cmd_name not in COMMANDS:
        print(f"未知命令: {cmd_name}")
        print(f"可用命令: {', '.join(COMMANDS.keys())}")
        return 1

    desc, func = COMMANDS[cmd_name]
    try:
        return func(cmd_args)
    except KeyboardInterrupt:
        print("\n已取消")
        return 130
    except Exception as e:
        print(f"❌ 执行失败: {e}")
        logger.exception("CLI 命令执行异常")
        return 1


if __name__ == "__main__":
    sys.exit(main())
