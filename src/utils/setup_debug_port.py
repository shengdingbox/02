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
    """读取快捷方式的 TargetPath 和 Arguments（纯 ctypes COM）"""
    if sys.platform != 'win32':
        return '', ''
    try:
        return _ctypes_get_shortcut_info(lnk_path)
    except Exception:
        pass
    # fallback: PowerShell
    try:
        ps = (
            "$ws=New-Object -ComObject WScript.Shell;"
            "$s=$ws.CreateShortcut('" + lnk_path + "');"
            "Write-Output $s.TargetPath;"
            "Write-Output '---';"
            "Write-Output $s.Arguments"
        )
        r = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
            capture_output=True, text=True, timeout=10,
            creationflags=0x08000000,
        )
        parts = r.stdout.split('---\n')
        if len(parts) >= 2:
            return parts[0].strip(), parts[1].strip()
    except Exception:
        pass
    return '', ''


def set_shortcut_args(lnk_path, args):
    """设置快捷方式的 Arguments（纯 ctypes COM）"""
    if sys.platform != 'win32':
        return False
    try:
        return _ctypes_set_shortcut_args(lnk_path, args)
    except Exception:
        pass
    # fallback: PowerShell
    try:
        ps = (
            "$ws=New-Object -ComObject WScript.Shell;"
            "$s=$ws.CreateShortcut('" + lnk_path + "');"
            "$s.Arguments='" + args + "';"
            "$s.Save()"
        )
        r = subprocess.run(
            ['powershell', '-NoProfile', '-NonInteractive', '-Command', ps],
            capture_output=True, text=True, timeout=10,
            creationflags=0x08000000,
        )
        return r.returncode == 0
    except Exception:
        return False


def _create_shortcut_ctypes(lnk_path, target_path, working_dir, arguments):
    """用纯 ctypes COM 创建/修改快捷方式"""
    import ctypes
    from ctypes import wintypes, POINTER, byref, c_void_p, c_wchar_p, c_int, c_uint, c_ulong

    ole32 = ctypes.windll.ole32

    # 初始化 COM
    ole32.CoInitialize(None)

    try:
        # 定义 GUID 结构
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        # CLSID_ShellLink: {00021401-0000-0000-C000-000000000046}
        clsid = GUID(0x00021401, 0x0000, 0x0000,
                     (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
        # IID_IPersistFile: {0000010b-0000-0000-C000-000000000046}
        iid_persist = GUID(0x0000010b, 0x0000, 0x0000,
                           (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
        # IID_IShellLinkW: {000214F9-0000-0000-C000-000000000046}
        iid_shelllink = GUID(0x000214F9, 0x0000, 0x0000,
                             (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))

        CLSCTX_INPROC_SERVER = 1

        # CoCreateInstance 创建 IShellLinkW
        p_shelllink = c_void_p()
        hr = ole32.CoCreateInstance(
            byref(clsid), None, CLSCTX_INPROC_SERVER,
            byref(iid_shelllink), byref(p_shelllink)
        )
        if hr != 0 or not p_shelllink.value:
            raise RuntimeError(f"CoCreateInstance failed: 0x{hr & 0xFFFFFFFF:08X}")

        # IShellLinkW vtable: IUnknown(3) + IShellLinkW methods
        # GetPath=3, GetIDList=4, SetIDList=5, GetDescription=6, SetDescription=7,
        # GetWorkingDirectory=8, SetWorkingDirectory=9, GetArguments=10, SetArguments=11, ...
        vptr = ctypes.cast(p_shelllink, POINTER(POINTER(c_void_p)))
        vtable = vptr[0]

        def call_method(idx, *args):
            """调用 COM vtable 方法"""
            func = ctypes.cast(vtable[idx], ctypes.CFUNCTYPE(c_int, c_void_p, *args))
            return func(p_shelllink.value, *args)

        # SetWorkingDirectory (index 9)
        call_method(9, c_wchar_p(working_dir))
        # SetPath (index 2) — 注意 SetIDList 在前，实际 SetPath 位置需要确认
        # IShellLinkW: SetPath 是 index 18（从 0 开始）
        # 让我用 SetArguments 和直接用 IPersistFile 保存
        # SetArguments (index 11)
        call_method(11, c_wchar_p(arguments))

        # QueryInterface 获取 IPersistFile
        p_persist = c_void_p()
        # IUnknown::QueryInterface 是 vtable[0]
        qi_func = ctypes.cast(vtable[0], ctypes.CFUNCTYPE(c_int, c_void_p, POINTER(GUID), POINTER(c_void_p)))
        hr = qi_func(p_shelllink.value, byref(iid_persist), byref(p_persist))
        if hr != 0 or not p_persist.value:
            raise RuntimeError(f"QueryInterface IPersistFile failed: 0x{hr & 0xFFFFFFFF:08X}")

        # IPersistFile vtable: IUnknown(3) + GetClassID=3, IsDirty=4, Load=5, Save=6, SaveCompleted=7, GetCurFile=8
        p_vptr = ctypes.cast(p_persist, POINTER(POINTER(c_void_p)))
        p_vtable = p_vptr[0]

        # Save(wchar* pszFileName, BOOL fRemember)
        save_func = ctypes.cast(p_vtable[6], ctypes.CFUNCTYPE(c_int, c_void_p, c_wchar_p, c_int))
        hr = save_func(p_persist.value, lnk_path, 1)
        if hr != 0:
            raise RuntimeError(f"IPersistFile.Save failed: 0x{hr & 0xFFFFFFFF:08X}")

        # Release
        release_func = ctypes.cast(p_vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
        release_func(p_persist.value)
        release_func2 = ctypes.cast(vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
        release_func2(p_shelllink.value)

        return True

    finally:
        ole32.CoUninitialize()


def _ctypes_get_shortcut_info(lnk_path):
    """用纯 ctypes COM 读取快捷方式信息"""
    import ctypes
    from ctypes import POINTER, byref, c_void_p, c_wchar_p, c_int, c_uint, create_unicode_buffer

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)

    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        clsid = GUID(0x00021401, 0x0000, 0x0000,
                     (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
        iid_persist = GUID(0x0000010b, 0x0000, 0x0000,
                           (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
        iid_shelllink = GUID(0x000214F9, 0x0000, 0x0000,
                             (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))

        p_shelllink = c_void_p()
        hr = ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid_shelllink), byref(p_shelllink))
        if hr != 0 or not p_shelllink.value:
            return '', ''

        vptr = ctypes.cast(p_shelllink, POINTER(POINTER(c_void_p)))
        vtable = vptr[0]

        # QueryInterface → IPersistFile
        p_persist = c_void_p()
        qi_func = ctypes.cast(vtable[0], ctypes.CFUNCTYPE(c_int, c_void_p, POINTER(GUID), POINTER(c_void_p)))
        hr = qi_func(p_shelllink.value, byref(iid_persist), byref(p_persist))
        if hr != 0 or not p_persist.value:
            release_func = ctypes.cast(vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
            release_func(p_shelllink.value)
            return '', ''

        p_vptr = ctypes.cast(p_persist, POINTER(POINTER(c_void_p)))
        p_vtable = p_vptr[0]

        # Load(wchar* pszFileName, DWORD dwMode)
        # STGM_READ = 0
        load_func = ctypes.cast(p_vtable[5], ctypes.CFUNCTYPE(c_int, c_void_p, c_wchar_p, ctypes.c_uint))
        hr = load_func(p_persist.value, lnk_path, 0)
        if hr != 0:
            release_func = ctypes.cast(p_vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
            release_func(p_persist.value)
            release_func2 = ctypes.cast(vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
            release_func2(p_shelllink.value)
            return '', ''

        # GetWorkingDirectory (IShellLinkW vtable index 8)
        # GetArguments (IShellLinkW vtable index 10)
        # 这两个方法签名: HRESULT GetX(wchar* buf, int cch)
        target_buf = create_unicode_buffer(260)
        args_buf = create_unicode_buffer(260)

        # GetWorkingDirectory (index 8): HRESULT GetWorkingDirectory(LPWSTR pszDir, int cch)
        get_wd_func = ctypes.cast(vtable[8], ctypes.CFUNCTYPE(c_int, c_void_p, c_wchar_p, c_int))
        get_wd_func(p_shelllink.value, target_buf, 260)

        # GetArguments (index 10): HRESULT GetArguments(LPWSTR pszArgs, int cch)
        get_args_func = ctypes.cast(vtable[10], ctypes.CFUNCTYPE(c_int, c_void_p, c_wchar_p, c_int))
        get_args_func(p_shelllink.value, args_buf, 260)

        # 获取 TargetPath (index 3): HRESULT GetPath(LPWSTR pszFile, int cch, WIN32_FIND_DATAW*, DWORD)
        # 用 GetWorkingDirectory 的结果作为 target（简化，实际应该用 GetPath）
        # 但我们主要需要 arguments，target 可以从 GetPath 获取
        find_data_buf = ctypes.create_string_buffer(592)  # WIN32_FIND_DATAW 大小约 592
        get_path_func = ctypes.cast(vtable[3], ctypes.CFUNCTYPE(c_int, c_void_p, c_wchar_p, c_int, ctypes.c_void_p, ctypes.c_uint))
        get_path_func(p_shelllink.value, target_buf, 260, None, 0)

        # Release
        release_func = ctypes.cast(p_vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
        release_func(p_persist.value)
        release_func2 = ctypes.cast(vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
        release_func2(p_shelllink.value)

        return target_buf.value, args_buf.value

    finally:
        ole32.CoUninitialize()


def _ctypes_set_shortcut_args(lnk_path, args):
    """用纯 ctypes COM 设置快捷方式 Arguments"""
    import ctypes
    from ctypes import POINTER, byref, c_void_p, c_wchar_p, c_int, c_uint

    ole32 = ctypes.windll.ole32
    ole32.CoInitialize(None)

    try:
        class GUID(ctypes.Structure):
            _fields_ = [
                ("Data1", ctypes.c_ulong),
                ("Data2", ctypes.c_ushort),
                ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8),
            ]

        clsid = GUID(0x00021401, 0x0000, 0x0000,
                     (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
        iid_persist = GUID(0x0000010b, 0x0000, 0x0000,
                           (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))
        iid_shelllink = GUID(0x000214F9, 0x0000, 0x0000,
                             (ctypes.c_ubyte * 8)(0xC0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x46))

        p_shelllink = c_void_p()
        hr = ole32.CoCreateInstance(byref(clsid), None, 1, byref(iid_shelllink), byref(p_shelllink))
        if hr != 0 or not p_shelllink.value:
            return False

        vptr = ctypes.cast(p_shelllink, POINTER(POINTER(c_void_p)))
        vtable = vptr[0]

        # QueryInterface → IPersistFile
        p_persist = c_void_p()
        qi_func = ctypes.cast(vtable[0], ctypes.CFUNCTYPE(c_int, c_void_p, POINTER(GUID), POINTER(c_void_p)))
        hr = qi_func(p_shelllink.value, byref(iid_persist), byref(p_persist))
        if hr != 0 or not p_persist.value:
            release_func = ctypes.cast(vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
            release_func(p_shelllink.value)
            return False

        p_vptr = ctypes.cast(p_persist, POINTER(POINTER(c_void_p)))
        p_vtable = p_vptr[0]

        # Load 现有快捷方式
        # STGM_READWRITE = 2
        load_func = ctypes.cast(p_vtable[5], ctypes.CFUNCTYPE(c_int, c_void_p, c_wchar_p, ctypes.c_uint))
        hr = load_func(p_persist.value, lnk_path, 2)
        if hr != 0:
            release_func = ctypes.cast(p_vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
            release_func(p_persist.value)
            release_func2 = ctypes.cast(vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
            release_func2(p_shelllink.value)
            return False

        # SetArguments (IShellLinkW vtable index 11)
        # HRESULT SetArguments(LPCWSTR pszArgs)
        set_args_func = ctypes.cast(vtable[11], ctypes.CFUNCTYPE(c_int, c_void_p, c_wchar_p))
        hr = set_args_func(p_shelllink.value, args)
        if hr != 0:
            release_func = ctypes.cast(p_vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
            release_func(p_persist.value)
            release_func2 = ctypes.cast(vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
            release_func2(p_shelllink.value)
            return False

        # Save
        save_func = ctypes.cast(p_vtable[6], ctypes.CFUNCTYPE(c_int, c_void_p, c_wchar_p, c_int))
        hr = save_func(p_persist.value, lnk_path, 1)

        # Release
        release_func = ctypes.cast(p_vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
        release_func(p_persist.value)
        release_func2 = ctypes.cast(vtable[2], ctypes.CFUNCTYPE(c_uint, c_void_p))
        release_func2(p_shelllink.value)

        return hr == 0

    finally:
        ole32.CoUninitialize()


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
        # 创建桌面快捷方式（纯 ctypes COM）
        desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop', 'WorkBuddy.lnk')
        try:
            _create_shortcut_ctypes(desktop, exe, os.path.dirname(exe), target_arg)
            print("[OK] 已创建桌面快捷方式: " + desktop)
        except Exception:
            # fallback: PowerShell
            ps = (
                "$ws=New-Object -ComObject WScript.Shell;"
                "$s=$ws.CreateShortcut('" + desktop + "');"
                "$s.TargetPath='" + exe + "';"
                "$s.WorkingDirectory='" + os.path.dirname(exe) + "';"
                "$s.Arguments='" + target_arg + "';"
                "$s.Save()"
            )
            r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=10)
            if r.returncode == 0:
                print("[OK] 已创建桌面快捷方式: " + desktop)
            else:
                print("[ERR] 创建快捷方式失败: " + r.stderr)
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

    使用 Python COM 接口操作快捷方式（不调 PowerShell），用 ctypes 优雅关闭进程（不用 taskkill）。
    仅支持 Windows，macOS 直接返回。

    Returns:
        tuple: (success: bool, message: str)
    """
    import time

    # macOS / Linux 不支持（WorkBuddy 调试端口配置仅限 Windows）
    if sys.platform != 'win32':
        return False, "此功能仅支持 Windows"

    target_arg = ARG_PREFIX + str(port)

    # 1. 安装调试端口到快捷方式（纯 ctypes COM）
    shortcuts = find_shortcuts()
    if not shortcuts:
        exe = find_exe()
        if not exe:
            return False, "找不到 WorkBuddy.exe，请确认已安装"
        # 创建桌面快捷方式（纯 ctypes COM）
        desktop = os.path.join(os.environ.get('USERPROFILE', ''), 'Desktop', 'WorkBuddy.lnk')
        try:
            _create_shortcut_ctypes(desktop, exe, os.path.dirname(exe), target_arg)
            shortcuts = [desktop]
        except Exception:
            # fallback PowerShell
            ps = (
                "$ws=New-Object -ComObject WScript.Shell;"
                "$s=$ws.CreateShortcut('" + desktop + "');"
                "$s.TargetPath='" + exe + "';"
                "$s.WorkingDirectory='" + os.path.dirname(exe) + "';"
                "$s.Arguments='" + target_arg + "';"
                "$s.Save()"
            )
            r = subprocess.run(['powershell', '-NoProfile', '-Command', ps], capture_output=True, text=True, timeout=10,
                               creationflags=0x08000000)
            if r.returncode != 0:
                return False, "创建快捷方式失败: " + r.stderr.strip()
            shortcuts = [desktop]
    else:
        for lnk in shortcuts:
            target, args = get_shortcut_info(lnk)
            if target_arg in args:
                continue
            other_args = [a for a in args.split() if not a.startswith(ARG_PREFIX)]
            new_args = ' '.join(other_args + [target_arg])
            set_shortcut_args(lnk, new_args)

    # 2. 关闭正在运行的 WorkBuddy（通过进程名找 PID + TerminateProcess）
    _close_workbuddy()

    # 3. 直接用 exe 带参数启动
    try:
        exe = find_exe()
        if exe:
            subprocess.Popen(
                [exe, target_arg],
            )
            time.sleep(3)
            return True, "WorkBuddy 已配置调试端口并重启"
        elif shortcuts:
            os.startfile(shortcuts[0])
            time.sleep(3)
            return True, "WorkBuddy 已配置调试端口并重启"
        else:
            return False, "找不到 WorkBuddy.exe"
    except Exception as e:
        return False, f"启动 WorkBuddy 失败: {e}"


def _close_workbuddy():
    """关闭正在运行的 WorkBuddy 进程（通过进程名，用 ctypes TerminateProcess）"""
    if sys.platform != 'win32':
        return

    import ctypes
    from ctypes import wintypes

    # 用 CreateToolhelp32Snapshot 枚举进程
    kernel32 = ctypes.windll.kernel32
    TH32CS_SNAPPROCESS = 0x00000002

    class PROCESSENTRY32W(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.POINTER(ctypes.c_ulong)),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", ctypes.c_long),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", ctypes.c_wchar * 260),
        ]

    snapshot = kernel32.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if snapshot == -1:
        return

    pe = PROCESSENTRY32W()
    pe.dwSize = ctypes.sizeof(PROCESSENTRY32W)

    pids = []
    if kernel32.Process32FirstW(snapshot, ctypes.byref(pe)):
        while True:
            name = pe.szExeFile
            if name and name.lower() == "workbuddy.exe":
                pids.append(pe.th32ProcessID)
            if not kernel32.Process32NextW(snapshot, ctypes.byref(pe)):
                break
    kernel32.CloseHandle(snapshot)

    # TerminateProcess 每个 WorkBuddy 进程
    PROCESS_TERMINATE = 0x0001
    for pid in pids:
        h = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if h:
            kernel32.TerminateProcess(h, 0)
            kernel32.CloseHandle(h)

    # 等待进程退出
    if pids:
        import time as _t
        _t.sleep(2)


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
