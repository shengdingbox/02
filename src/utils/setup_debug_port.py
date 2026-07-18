# -*- coding: utf-8 -*-
"""
WorkBuddy 调试端口配置器
========================
管理 WorkBuddy 快捷方式的 --remote-debugging-port 参数。

用法：
  python setup_debug_port.py              # 安装（给快捷方式加调试端口参数）
  python setup_debug_port.py --check      # 检查当前状态
  python setup_debug_port.py --remove     # 卸载（去掉调试端口参数）
  python setup_debug_port.py --port 9223  # 自定义端口（默认 9222）

原理：
  找到 WorkBuddy 桌面快捷方式 → 设置 Arguments = --remote-debugging-port=N
  以后每次双击图标启动都自动带调试端口，无需手动加参数。
"""
import os, sys, subprocess, re

PORT = 9222
ARG_PREFIX = "--remote-debugging-port="

# 注册表卸载信息位置（HKLM + HKCU + WOW6432Node）
REG_UNINSTALL_KEYS = [
    r'HKLM\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
    r'HKLM\SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall',
    r'HKCU\SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
]


def find_exe_from_registry():
    """从注册表 Uninstall 项查找 WorkBuddy.exe 路径"""
    for reg_root in REG_UNINSTALL_KEYS:
        ps = (
            "Get-ChildItem 'Registry::" + reg_root + "' -ErrorAction SilentlyContinue | "
            "ForEach-Object { $p = Get-ItemProperty $_.PSPath -ErrorAction SilentlyContinue; "
            "if ($p.DisplayName -like '*WorkBuddy*') { "
            "Write-Output ('DisplayIcon=' + $p.DisplayIcon); "
            "Write-Output ('UninstallString=' + $p.UninstallString); "
            "Write-Output ('InstallLocation=' + $p.InstallLocation) } }"
        )
        r = subprocess.run(['powershell', '-Command', ps], capture_output=True, text=True, timeout=10)
        if r.stdout.strip():
            for line in r.stdout.strip().split('\n'):
                line = line.strip()
                if line.startswith('DisplayIcon='):
                    # 格式: "D:\path\WorkBuddy.exe,0" 或 "D:\path\WorkBuddy.exe"
                    val = line[len('DisplayIcon='):]
                    exe = val.split(',')[0].strip().strip('"')
                    if exe and os.path.exists(exe):
                        return exe
                elif line.startswith('InstallLocation='):
                    val = line[len('InstallLocation='):]
                    if val:
                        exe = os.path.join(val, 'WorkBuddy.exe')
                        if os.path.exists(exe):
                            return exe
                elif line.startswith('UninstallString='):
                    val = line[len('UninstallString='):]
                    # 从 "D:\path\Uninstall WorkBuddy.exe" 提取目录
                    m = re.search(r'"?([^"]+?)[\\/][^\\/]+\.exe"', val)
                    if m:
                        exe = os.path.join(m.group(1), 'WorkBuddy.exe')
                        if os.path.exists(exe):
                            return exe
    return None


def find_shortcuts():
    """扫描常见位置查找 WorkBuddy 快捷方式"""
    userprofile = os.environ.get('USERPROFILE', '')
    appdata = os.environ.get('APPDATA', '')
    programdata = os.environ.get('ProgramData', r'C:\ProgramData')
    search_dirs = [
        os.path.join(userprofile, 'Desktop'),
        os.path.join(appdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
        os.path.join(programdata, 'Microsoft', 'Windows', 'Start Menu', 'Programs'),
    ]
    found = []
    for d in search_dirs:
        if not os.path.isdir(d):
            continue
        for root, dirs, files in os.walk(d):
            for f in files:
                if f.lower().endswith('.lnk') and 'workbuddy' in f.lower():
                    found.append(os.path.join(root, f))
    return found


def find_exe():
    """查找 WorkBuddy.exe：先注册表，再常见路径"""
    # 1. 注册表
    exe = find_exe_from_registry()
    if exe:
        return exe
    # 2. 常见路径
    candidates = [
        os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'WorkBuddy', 'WorkBuddy.exe'),
        os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'WorkBuddy', 'WorkBuddy.exe'),
        os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs', 'WorkBuddy', 'WorkBuddy.exe'),
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return None


def get_shortcut_info(lnk_path):
    """读取快捷方式的 TargetPath 和 Arguments（pywin32 优先，失败 fallback PowerShell）"""
    # 方案1: pywin32
    try:
        import pythoncom
        from win32com.shell import shell, shellcon
        pythoncom.CoInitialize()
        try:
            pidl = shell.SHParseDisplayName(lnk_path, None)[0]
            uuid_shelllink = pythoncom.MakeIID("{00021401-0000-0000-C000-000000000046}")
            persist_file = pythoncom.CoCreateInstance(uuid_shelllink, None, pythoncom.CLSCTX_INPROC_SERVER, pythoncom.IID_IPersistFile)
            persist_file.Load(lnk_path)
            ishell = persist_file.QueryInterface(pythoncom.IID_IShellLink)
            target = ishell.GetPath(shellcon.SLGP_SHORTPATH)[0]
            args = ishell.GetArguments()
            return target, args
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        pass

    # 方案2: PowerShell
    try:
        ps = (
            "$ws=New-Object -ComObject WScript.Shell;"
            "$s=$ws.CreateShortcut('" + lnk_path + "');"
            "Write-Output $s.TargetPath;"
            "Write-Output '---';"
            "Write-Output $s.Arguments"
        )
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=10,
                           creationflags=0x08000000)
        parts = r.stdout.split('---\n')
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
    except Exception:
        pass
    return '', ''


def set_shortcut_args(lnk_path, args):
    """设置快捷方式的 Arguments（pywin32 优先，失败 fallback PowerShell）"""
    # 方案1: pywin32
    try:
        import pythoncom
        from win32com.shell import shellcon
        pythoncom.CoInitialize()
        try:
            uuid_shelllink = pythoncom.MakeIID("{00021401-0000-0000-C000-000000000046}")
            persist_file = pythoncom.CoCreateInstance(uuid_shelllink, None, pythoncom.CLSCTX_INPROC_SERVER, pythoncom.IID_IPersistFile)
            persist_file.Load(lnk_path)
            ishell = persist_file.QueryInterface(pythoncom.IID_IShellLink)
            ishell.SetArguments(args)
            persist_file.Save(lnk_path, 0)
            return True
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        pass

    # 方案2: PowerShell
    try:
        ps = (
            "$ws=New-Object -ComObject WScript.Shell;"
            "$s=$ws.CreateShortcut('" + lnk_path + "');"
            "$s.Arguments='" + args + "';"
            "$s.Save()"
        )
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=10,
                           creationflags=0x08000000)
        return r.returncode == 0
    except Exception:
        return False


def do_install(port):
    target_arg = ARG_PREFIX + str(port)
    print("=" * 50)
    print("WorkBuddy 调试端口配置器 - 安装")
    print("端口: " + str(port))
    print("=" * 50)

    shortcuts = find_shortcuts()
    if not shortcuts:
        print("[WARN] 未找到 WorkBuddy 快捷方式，尝试创建...")
        exe = find_exe()
        if not exe:
            print("[ERR] 找不到 WorkBuddy.exe，请确认安装路径")
            sys.exit(1)
        # 创建桌面快捷方式
        desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop', 'WorkBuddy.lnk')
        if _create_shortcut(desktop, exe, target_arg):
            print("[OK] 已创建桌面快捷方式: " + desktop)
        else:
            print("[ERR] 创建快捷方式失败")
            sys.exit(1)
    else:
        for lnk in shortcuts:
            target, args = get_shortcut_info(lnk)
            print("[INFO] " + lnk)
            print("  Target: " + target)
            print("  Args: " + (args if args else "(无)"))

            if target_arg in args:
                print("  [SKIP] 已有调试端口参数，无需修改")
                continue

            # 保留原有非调试端口参数，追加新的
            other_args = [a for a in args.split() if not a.startswith(ARG_PREFIX)]
            new_args = ' '.join(other_args + [target_arg])
            if set_shortcut_args(lnk, new_args):
                print("  [OK] 已添加 " + target_arg)
            else:
                print("  [ERR] 修改失败")

    print("\n[DONE] 完成！以后双击 WorkBuddy 图标启动会自动带调试端口")
    print("  验证: 启动 WorkBuddy 后访问 http://127.0.0.1:" + str(port) + "/json")
    print("\n  卸载: python setup_debug_port.py --remove")


def do_remove():
    print("=" * 50)
    print("WorkBuddy 调试端口配置器 - 卸载")
    print("=" * 50)

    shortcuts = find_shortcuts()
    if not shortcuts:
        print("[WARN] 未找到任何 WorkBuddy 快捷方式")
        return

    for lnk in shortcuts:
        target, args = get_shortcut_info(lnk)
        print("[INFO] " + lnk)
        print("  Args: " + (args if args else "(无)"))

        if ARG_PREFIX not in args:
            print("  [SKIP] 没有调试端口参数，无需处理")
            continue

        # 去掉调试端口参数，保留其他
        other_args = [a for a in args.split() if not a.startswith(ARG_PREFIX)]
        new_args = ' '.join(other_args)
        if set_shortcut_args(lnk, new_args):
            print("  [OK] 已移除调试端口参数")
        else:
            print("  [ERR] 修改失败")

    print("\n[DONE] 已移除调试端口参数，WorkBuddy 将正常启动")


def do_check():
    print("=" * 50)
    print("WorkBuddy 调试端口配置器 - 检查")
    print("=" * 50)

    shortcuts = find_shortcuts()
    if not shortcuts:
        print("[WARN] 未找到 WorkBuddy 快捷方式")
        exe = find_exe()
        if exe:
            print("[INFO] 找到 WorkBuddy.exe: " + exe)
        return

    found_port = None
    for lnk in shortcuts:
        target, args = get_shortcut_info(lnk)
        print("[INFO] " + lnk)
        print("  Target: " + target)
        print("  Args: " + (args if args else "(无)"))

        # 提取端口号
        for a in args.split():
            if a.startswith(ARG_PREFIX):
                found_port = a[len(ARG_PREFIX):]
                print("  -> 调试端口: " + found_port)
                break
        if not found_port:
            print("  -> 无调试端口参数")

    # 检查端口是否在监听
    if found_port:
        import urllib.request
        try:
            urllib.request.urlopen("http://127.0.0.1:" + found_port + "/json", timeout=3).read()
            print("\n[OK] 调试端口 " + found_port + " 正在监听（WorkBuddy 已启动带调试端口）")
        except:
            print("\n[INFO] 调试端口 " + found_port + " 未在监听（WorkBuddy 未启动或未带参数）")


def setup_and_restart(port=PORT):
    """安装调试端口配置并重启 WorkBuddy

    流程:
        1. 尝试修改快捷方式（pywin32 优先，失败 fallback PowerShell，再失败跳过）
        2. 优雅关闭 WorkBuddy（ctypes 发 WM_CLOSE）
        3. 直接用 exe + 调试端口参数启动（不依赖快捷方式）

    Returns:
        tuple: (success: bool, message: str)
    """
    import time

    # macOS / Linux 不支持
    if sys.platform != 'win32':
        return False, "此功能仅支持 Windows"

    target_arg = ARG_PREFIX + str(port)

    # 1. 找到 exe 路径
    exe = find_exe()
    if not exe:
        return False, "找不到 WorkBuddy.exe，请确认已安装"

    # 2. 尝试修改快捷方式（可选，失败不影响启动）
    try:
        shortcuts = find_shortcuts()
        if shortcuts:
            for lnk in shortcuts:
                target, args = get_shortcut_info(lnk)
                if target_arg in (args or ""):
                    continue
                other_args = [a for a in (args or "").split() if not a.startswith(ARG_PREFIX)]
                new_args = ' '.join(other_args + [target_arg])
                set_shortcut_args(lnk, new_args)
        else:
            # 没有快捷方式，创建一个（可选，失败跳过）
            desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop', 'WorkBuddy.lnk')
            _create_shortcut(desktop, exe, target_arg)
    except Exception:
        pass  # 快捷方式修改失败不影响直接启动

    # 3. 优雅关闭正在运行的 WorkBuddy
    _close_workbuddy_gracefully()

    # 4. 直接用 exe + 调试端口参数启动
    try:
        subprocess.Popen(
            [exe, target_arg],
            creationflags=0x08000000,  # CREATE_NO_WINDOW
        )
        time.sleep(3)
        return True, "WorkBuddy 已配置调试端口并重启"
    except Exception as e:
        return False, f"启动 WorkBuddy 失败: {e}"


def _create_shortcut(lnk_path, exe_path, args):
    """创建快捷方式（优先 pywin32，失败 fallback PowerShell）"""
    # 方案1: pywin32
    try:
        import pythoncom
        pythoncom.CoInitialize()
        try:
            uuid_shelllink = pythoncom.MakeIID("{00021401-0000-0000-C000-000000000046}")
            persist_file = pythoncom.CoCreateInstance(uuid_shelllink, None, pythoncom.CLSCTX_INPROC_SERVER, pythoncom.IID_IPersistFile)
            ishell = persist_file.QueryInterface(pythoncom.IID_IShellLink)
            ishell.SetPath(exe_path)
            ishell.SetWorkingDirectory(os.path.dirname(exe_path))
            ishell.SetArguments(args)
            persist_file.Save(lnk_path, 0)
            return True
        finally:
            pythoncom.CoUninitialize()
    except Exception:
        pass

    # 方案2: PowerShell
    try:
        ps = (
            "$ws=New-Object -ComObject WScript.Shell;"
            "$s=$ws.CreateShortcut('" + lnk_path + "');"
            "$s.TargetPath='" + exe_path + "';"
            "$s.WorkingDirectory='" + os.path.dirname(exe_path) + "';"
            "$s.Arguments='" + args + "';"
            "$s.Save()"
        )
        r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=10,
                           creationflags=0x08000000)
        return r.returncode == 0
    except Exception:
        return False


def _close_workbuddy_gracefully(timeout=5):
    """优雅关闭 WorkBuddy 进程（发 WM_CLOSE，不用 taskkill）

    仅 Windows 可用。

    Args:
        timeout: 等待关闭的超时秒数
    """
    if sys.platform != 'win32':
        return

    import ctypes
    from ctypes import wintypes

    # 枚举所有窗口，找到 WorkBuddy 的主窗口并发 WM_CLOSE
    user32 = ctypes.windll.user32
    WM_CLOSE = 0x0010
    found_hwnds = []

    # 获取所有进程的窗口
    EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def _enum_callback(hwnd, lparam):
        # 获取窗口标题
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            title = buf.value
            # 获取窗口所属进程
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            # 检查是否是 WorkBuddy 窗口
            if "WorkBuddy" in title or "workbuddy" in title.lower():
                found_hwnds.append(hwnd)
        return True

    user32.EnumWindows(EnumWindowsProc(_enum_callback), 0)

    # 发送 WM_CLOSE 到每个 WorkBuddy 窗口
    for hwnd in found_hwnds:
        user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)

    # 等待进程退出
    if found_hwnds:
        time_module = __import__('time')
        time_module.sleep(2)


def main():
    global PORT
    action = 'install'
    for i, a in enumerate(sys.argv):
        if a == '--check': action = 'check'
        elif a == '--remove': action = 'remove'
        elif a == '--port' and i + 1 < len(sys.argv):
            PORT = int(sys.argv[i + 1])

    if action == 'check':
        do_check()
    elif action == 'remove':
        do_remove()
    else:
        do_install(PORT)


if __name__ == '__main__':
    main()
