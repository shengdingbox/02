"""环境检测 — 启动时检测本机代理软件和 Hook 程序

检测项:
1. 系统代理设置 (HTTP_PROXY / HTTPS_PROXY / Windows 注册表)
2. 常见代理软件进程 (Clash, V2Ray, Shadowsocks, Surge 等)
3. Hook/注入工具进程 (Fiddler, Charles, Wireshark, mitmproxy, HTTPToolkit 等)
"""

import os
import sys
import logging
import platform

logger = logging.getLogger(__name__)

# 常见代理软件进程名（小写匹配）
_PROXY_PROCESSES = [
    "",
]

# 常见 Hook/抓包工具进程名
_HOOK_PROCESSES = [
    "fiddler", "fiddler everywhere",
    "charles", "charles-proxy",
    "wireshark", "tshark", "dumpcap",
    "mitmproxy", "mitmdump", "mitmweb",
    "httptoolkit",
    "burpsuite", "burp",
    "proxyman",
    "reqable",
    "wpe pro", "wpespy",
    "frida", "frida-server", "frida-trace",
    "x64dbg", "x32dbg", "windbg", "ollydbg",
    "cheatengine", "cheat engine",
    "processhacker",
    "api-monitor", "apimonitor",
    "httpdebugger", "http debugger",
]


def _get_running_processes() -> list[str]:
    """获取当前运行的进程名列表（小写）"""
    processes = []
    system = platform.system()

    try:
        if system == "Windows":
            import subprocess
            result = subprocess.run(
                ["tasklist", "/FO", "CSV", "/NH"],
                capture_output=True, text=True, timeout=10,
                creationflags=0x08000000,  # CREATE_NO_WINDOW，防止黑窗口闪烁
            )
            for line in result.stdout.strip().splitlines():
                # CSV 格式: "名称","PID","会话名","会话#","内存"
                parts = line.split('","')
                if parts:
                    name = parts[0].strip('"').lower()
                    if name:
                        processes.append(name)
        elif system == "Darwin":
            import subprocess
            result = subprocess.run(
                ["ps", "aux"],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().splitlines()[1:]:
                parts = line.split()
                if len(parts) >= 11:
                    name = os.path.basename(parts[10]).lower()
                    if name:
                        processes.append(name)
        elif system == "Linux":
            import subprocess
            result = subprocess.run(
                ["ps", "-A", "-o", "comm="],
                capture_output=True, text=True, timeout=10,
            )
            for line in result.stdout.strip().splitlines():
                name = os.path.basename(line.strip()).lower()
                if name:
                    processes.append(name)
    except Exception as e:
        logger.debug(f"获取进程列表失败: {e}")

    return processes


def _check_system_proxy() -> dict:
    """检测系统代理设置"""
    result = {"enabled": False, "http_proxy": "", "https_proxy": "", "source": ""}

    # 1. 环境变量
    http_proxy = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy") or ""
    https_proxy = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy") or ""
    all_proxy = os.environ.get("ALL_PROXY") or os.environ.get("all_proxy") or ""

    if http_proxy or https_proxy or all_proxy:
        result["enabled"] = True
        result["http_proxy"] = http_proxy or all_proxy
        result["https_proxy"] = https_proxy or all_proxy
        result["source"] = "环境变量"
        return result

    # 2. Windows 注册表
    if platform.system() == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings",
            )
            proxy_enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if proxy_enable:
                proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                result["enabled"] = True
                result["http_proxy"] = proxy_server
                result["https_proxy"] = proxy_server
                result["source"] = "Windows 系统代理"
            winreg.CloseKey(key)
        except Exception:
            pass

    return result


def check_environment() -> dict:
    """检测代理软件和 Hook 程序

    Returns:
        {
            "proxy_software": list[str],   # 检测到的代理软件
            "hook_tools": list[str],       # 检测到的 Hook 工具
            "system_proxy": dict,          # 系统代理设置
        }
    """
    processes = _get_running_processes()
    process_set = set(processes)

    # 检测代理软件
    found_proxy = []
    for name in _PROXY_PROCESSES:
        # 精确匹配或包含匹配
        for proc in process_set:
            if name in proc:
                found_proxy.append(proc)
                break

    # 检测 Hook 工具
    found_hooks = []
    for name in _HOOK_PROCESSES:
        for proc in process_set:
            if name in proc:
                found_hooks.append(proc)
                break

    # 检测系统代理
    sys_proxy = _check_system_proxy()

    result = {
        "proxy_software": found_proxy,
        "hook_tools": found_hooks,
        "system_proxy": sys_proxy,
    }

    if found_proxy:
        logger.info(f"[环境检测] 检测到代理软件: {found_proxy}")
    if found_hooks:
        logger.warning(f"[环境检测] 检测到 Hook/抓包工具: {found_hooks}")
    if sys_proxy["enabled"]:
        logger.info(f"[环境检测] 系统代理已开启 ({sys_proxy['source']}): {sys_proxy['http_proxy']}")

    return result


def format_env_warnings(check_result: dict) -> str:
    """格式化环境检测结果为提示文本"""
    warnings = []

    proxy_apps = check_result.get("proxy_software", [])
    hook_tools = check_result.get("hook_tools", [])
    sys_proxy = check_result.get("system_proxy", {})

    if not proxy_apps and not hook_tools and not sys_proxy.get("enabled"):
        return ""

    lines = ["检测到以下可能影响服务运行的程序：", ""]

    if proxy_apps:
        lines.append("📡 代理软件:")
        for app in proxy_apps:
            lines.append(f"  • {app}")
        lines.append("")

    if hook_tools:
        lines.append("🔧 Hook/抓包工具:")
        for tool in hook_tools:
            lines.append(f"  • {tool}")
        lines.append("")

    if sys_proxy.get("enabled"):
        lines.append(f"🌐 系统代理已开启 ({sys_proxy.get('source', '')})")
        lines.append(f"  代理地址: {sys_proxy.get('http_proxy', '')}")

    return "\n".join(lines)
