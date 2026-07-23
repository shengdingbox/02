# BuddyTool 防逆向分析加固方案报告

> 基于对 `BuddyTool.exe` v1.1.5 的逆向分析结果，针对其暴露的 7 大弱点，提出系统性的客户端软件加固方案。
> 编写日期：2026-07-23

---

## 目录

1. [现状分析：当前程序为何如此容易被逆向](#一现状分析当前程序为何如此容易被逆向)
2. [打包层加固：阻止 payload 提取](#二打包层加固阻止-payload-提取)
3. [代码层加固：消除静态字符串泄露](#三代码层加固消除静态字符串泄露)
4. [密钥管理加固：从根本上解决硬编码问题](#四密钥管理加固从根本上解决硬编码问题)
5. [反分析层加固：增加动态分析成本](#五反分析层加固增加动态分析成本)
6. [数据层加固：保护本地存储与数据库](#六数据层加固保护本地存储与数据库)
7. [通信层加固：强化网络传输安全](#七通信层加固强化网络传输安全)
8. [针对 BuddyTool 的具体改造路线图](#八针对-buddytool-的具体改造路线图)
9. [加固效果评估矩阵](#九加固效果评估矩阵)
10. [重要现实提醒与合规边界](#十重要现实提醒与合规边界)
11. [附录：关键工具与资源](#附录关键工具与资源)

---

## 一、现状分析：当前程序为何如此容易被逆向

通过前三轮分析（PE 结构 → Nuitka 解包 → 字符串提取 → 加密分析），BuddyTool 在约 1 小时内被完全还原了内部逻辑。根本原因在于以下 7 个弱点：

### 弱点 1：打包方式标准化，公开工具可直接解包

**现象**：
- 使用 Nuitka Onefile 打包
- payload 存放在 PE 资源的 RCDATA id=27
- 以固定 magic `KAY`（3 字节）开头，紧随其后是标准 zstd 压缩流（magic `28 B5 2F FD`）
- 解压后是简单的归档格式：`[UTF-16LE 文件名\0\0][uint64 size][文件数据]` 循环

**后果**：用 `pefile` + `zstandard` 两个库，20 行 Python 代码即完整解包出 69 个文件，包括核心的 `app.dll`（22.6MB）。

**攻击成本**：5 分钟。

### 弱点 2：所有密钥硬编码在二进制中

**现象**：从 `app.dll` 字符串中直接提取到：
```
_AES_KEY_HEX = "38502350408f8d5011606fc186daa626196beac6a529d7b79b30e713a0c6f2f0"  # AES-256 密钥
_HMAC_KEY    = (附近字节)  # HMAC 签名密钥
_XXTEA_KEY   = (附近字节)  # 本地密钥池加密密钥
_API_KEY     = "buddy_707d23cb0832fb0f0fc4a3d7"  # API 标识
```

**后果**：
- AES-256-GCM 加密的通信可被完全解密
- HMAC-SHA256 签名可被伪造
- 本地 `proxy_db.key` 密钥池可被还原出所有上游 API Key

**攻击成本**：10 分钟（字符串搜索）。

### 弱点 3：Nuitka 编译后保留完整 Python 符号

**现象**：`app.dll` 中包含完整的：
- 模块路径：`src.utils.server_api`、`src.modules.proxy_server`、`src.ui.pages.dashboard`
- 类名：`MainWindow`、`DashboardPage`、`AccountsPage`、`ProxyServer`、`CheckinManager`
- 方法名：`_fetch_buddykey`、`_encrypt_body`、`_decrypt_vscdb_secret`、`inject_credits_to_workbuddy`
- 内部变量名：`buddykey_refresh_count`、`_cached_upstream_keys`

**后果**：整个软件架构、功能模块、调用关系被 100% 还原，等于源码级可读性。

**攻击成本**：30 分钟（字符串提取 + 分类）。

### 弱点 4：docstring 原样保留

**现象**：函数文档字符串完整保留，例如：
```
"AES-256-GCM 加密流程：
 1. JSON 序列化明文 → UTF-8 字节
 2. 生成 12 字节随机 nonce (os.urandom(12))
 3. AES-256-GCM 加密（associated_data 关联数据可选）
 4. 输出 = nonce(12B) + ciphertext + tag(16B)"
```

还有签到逻辑、WorkBuddy 凭据提取步骤的详细说明。

**后果**：等于自带使用说明书，攻击者无需猜测即可理解每段逻辑的意图。

**攻击成本**：0（直接阅读）。

### 弱点 5：SQLite Schema 明文

**现象**：
```sql
CREATE TABLE IF NOT EXISTS accounts (
    uid TEXT PRIMARY KEY,
    auth_token TEXT DEFAULT '',    -- 敏感字段名暴露
    ck TEXT DEFAULT '',            -- cookie
    api_key TEXT DEFAULT '',
    ...
);
CREATE TABLE IF NOT EXISTS api_keys (
    key_id TEXT PRIMARY KEY,
    key_value TEXT DEFAULT '',     -- 上游密钥值
    ...
);
```

**后果**：数据库结构、字段含义、敏感数据位置一目了然，便于定向提取。

### 弱点 6：URL/端点/业务常量以明文散落

**现象**：20+ 个业务 URL、API 路径、响应格式模板均以明文字符串存在：
```
https://www.codebuddy.cn/auth/realms/copilot/protocol/openid-connect/token
https://copilot.tencent.com/v2/chat/completions
https://buddy.shengdingit.com/api/redeem
{"success": true, "buddyKey": "ck_...", "expiresAt": "...", "balance": ...}
```

**后果**：完整 API 接口清单、请求/响应格式被提取，可直接编写第三方客户端。

### 弱点 7：无任何反分析措施

**现象**：
- 无反调试检测
- 无完整性校验
- 无反虚拟机/沙箱检测
- 无代码混淆
- 无壳保护
- payload 解压后直接落盘到 `%TEMP%\onefile_*\`

**后果**：可在 IDA/x64dbg/沙箱中随意静态和动态分析，无任何阻碍。

---

## 二、打包层加固：阻止 payload 提取

### 目标
让攻击者无法用公开工具一键解包，必须逆向 bootloader 才能提取 payload。

### 方案 A：Nuitka Standalone + 文件加密（推荐基础方案）

**做法**：
- 放弃 onefile 模式，改用 standalone 目录分发
- 对敏感文件（`app.dll`、数据文件）用 AES-256-GCM 加密
- 运行时解密到内存，不落盘

**优点**：实现简单，Nuitka 原生支持 standalone
**缺点**：分发变成多文件，需要额外加密层

### 方案 B：修改 Nuitka bootloader 源码（中等方案）

Nuitka 是开源的（GPL 协议），可以修改其 bootloader：

```c
// 修改 OnefileBootloader 的解包逻辑（C 代码）

// 1. 替换 magic
// 原始: 'K' 'A' 'Y'
// 修改: 随机 3 字节 + 校验和，每次构建不同

// 2. 替换 zstd 为自定义压缩
// 原始: zstd 标准流
// 修改: AES-CTR 加密 + LZ4 压缩
//       密钥从机器特征派生（MAC + CPU ID + 安装时间）

// 3. 内存加载，不落盘
#ifdef _WIN32
// Windows: 用内存模块加载
HANDLE hMap = CreateFileMapping(INVALID_HANDLE_VALUE, ...);
// 或用 NtCreateSection + NtMapViewOfSection
#else
// Linux: memfd_create
int fd = memfd_create("app", MFD_CLOEXEC);
#endif
```

**优点**：公开工具（pyinstxtractor、nuitka extractor）全部失效
**缺点**：需要维护 Nuitka fork，升级麻烦

### 方案 C：商业壳保护（最有效方案）

对编译后的 `BuddyTool.exe` 的 bootloader 段（124KB `.text`）加商业壳：

| 工具 | 特性 | 价格 |
|---|---|---|
| **VMProtect** | 代码虚拟化、反调试、许可证管理 | ~$399+ |
| **Themida** | 多层加密、反 dump、反虚拟机 | ~$319+ |
| **Enigma Protector** | 文件加密、反调试、许可证 | ~$129+ |
| **Safengine Shielden** | 虚拟机引擎、元数据加密 | ~$199+ |

**推荐组合**：VMProtect 保护 bootloader 的解包关键函数，配合自定义 payload 格式。

**关键点**：必须保护"payload 解压逻辑"本身，否则只换 magic 没用——攻击者逆一次 bootloader 就能写出通用解包器。

### 方案 D：payload 内存加载（高级方案）

```
传统流程：
  exe 启动 → 解压 payload 到 %TEMP%\onefile_*\ → 加载 DLL → 运行

加固流程：
  exe 启动 → 解密 payload 到匿名内存映射 → 
  Windows: 用 Memory Module Loader 从内存加载 DLL（不经过 LoadLibrary）
  Linux:   用 dlopen 配合 memfd_create
  → 运行 → 退出时内存自动释放
```

**优点**：磁盘上不存在解压后的文件，无法被文件系统监控捕获
**缺点**：实现复杂，杀毒软件可能误报（内存加载 DLL 是可疑行为）

---

## 三、代码层加固：消除静态字符串泄露

这是**性价比最高**的加固方向，即使打包层被突破，也能大幅减少信息泄露。

### 3.1 字符串加密：让密钥/URL/SQL 不再明文

#### 现状（反面教材）
```python
# src/utils/server_api.py
_AES_KEY_HEX = "38502350408f8d5011606fc186daa626196beac6a529d7b79b30e713a0c6f2f0"
SERVER_BASE = "https://buddy.shengdingit.com/api"
```
这些字符串在编译后的 `app.dll` 中以明文存在，`strings` 命令即可提取。

#### 加固方案 1：编译期 XOR 加密

```python
# 构建时脚本：把明文字符串加密成字节序列
def obfuscate(s: str, key: int = 0x5A) -> bytes:
    return bytes(b ^ key for b in s.encode('utf-8'))

# 构建时生成
_OBFUSCATED = {
    'AES_KEY': obfuscate("38502350408f8d5011606fc186daa626196beac6a529d7b79b30e713a0c6f2f0"),
    'SERVER': obfuscate("https://buddy.shengdingit.com/api"),
    # ...
}

# 运行时解密
def _reveal(obfuscated: bytes, key: int = 0x5A) -> str:
    return bytes(b ^ key for b in obfuscated).decode('utf-8')

_AES_KEY_HEX = _reveal(_OBFUSCATED['AES_KEY'])
```

二进制中只看到 `b'\x52\x0b\x02\x02\x0a...'`（XOR 后的乱码），看不到明文。

**进阶**：每个字符串用不同的 key，key 从函数调用栈哈希派生，增加分析难度。

#### 加固方案 2：PyArmor 字符串混淆（推荐）

[PyArmor](https://pyarmor.dashingsoft.com/) 专门做 Python 代码保护：

```bash
# 先用 PyArmor 混淆源码
pyarmor gen --mix-str --restrict-mode=2 src/

# 再用 Nuitka 编译混淆后的代码
nuitka --onefile --follow-imports dist/obfuscated/main.py
```

PyArmor 的 RFT 模式会：
- 把字符串在运行时通过 JIT 解密
- 静态二进制中看不到任何明文字符串
- 配合 Nuitka 编译，效果叠加

#### 加固方案 3：敏感数据放入 C 扩展

```c
// secret_keys.c（编译成 _secrets.pyd）
#include <Python.h>

static char key[] = { 0x38, 0x50, 0x23, ... };  // 拆散的字节

static PyObject* get_aes_key(PyObject* self, PyObject* args) {
    // 运行时重组 + XOR 解密
    char buf[65];
    for (int i = 0; i < 64; i++)
        buf[i] = key[i] ^ 0x00;
    buf[64] = 0;
    return PyUnicode_FromString(buf);
}

static PyMethodDef methods[] = {
    {"_g", get_aes_key, METH_NOARGS, ""},
    {NULL, NULL, 0, NULL}
};
```

Python 侧调用 `from _secrets import _g; key = _g()`。这样字符串深埋在编译后的 `.pyd` 里，且可以用反调试保护。

### 3.2 消除符号信息：让函数名不再可读

#### 现状
```
src.utils.server_api
src.modules.proxy_server  
DashboardPage._fetch_buddykey
ProxyServer._build_workbuddy_relay_headers
```

#### 加固方案 1：Nuitka 编译选项

```bash
nuitka --onefile \
       --no-docstrings \          # 关键：去掉所有 docstring
       --remove-output \          # 删除中间文件
       --lto=yes \                # 链接时优化，减少符号
       main.py
```

`--no-docstrings` 是最低成本的改进，能去掉所有"使用说明书"。

#### 加固方案 2：源码层符号混淆

构建前用脚本把所有标识符替换为无意义名：

```python
# build_obfuscate.py
import ast, astor

rename_map = {
    'DashboardPage': '_cls_a3f',
    'fetch_buddykey': '_m_7b2',
    'encrypt_body': '_m_9c1',
    'server_api': '_mod_2e5',
    # ... 自动生成
}

# 遍历 AST，替换所有 Name 节点
```

注意：Nuitka 会保留 Python 对象的 `__name__` 属性，所以必须**在源码层**改名，不能只靠编译选项。

#### 加固方案 3：PyArmor 符号混淆

```bash
pyarmor gen --obf-code=2 --obf-module=2 --mix-str src/
```

PyArmor 会把函数名、类名、变量名替换为不可读形式，且运行时动态还原。

### 3.3 docstring 剥离

```bash
# Nuitka 编译时
nuitka --no-docstrings main.py

# 或构建前预处理
python -c "
import ast, sys
tree = ast.parse(open('src/main.py').read())
for node in ast.walk(tree):
    if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module)):
        node.body = [n for n in node.body if not isinstance(n, ast.Expr) or not isinstance(n.value, ast.Constant)]
ast.fix_missing_locations(tree)
# 写回
"
```

---

## 四、密钥管理加固：从根本上解决硬编码问题

这是**比加密算法选择更重要**的部分。AES-256 的密钥再长，写在 exe 里就等于零安全。

### 4.1 现状问题

```
exe 中硬编码：
  _AES_KEY_HEX = "38502350408f8d5011606fc186daa626196beac6a529d7b79b30e713a0c6f2f0"
  _HMAC_KEY = <bytes>
  _XXTEA_KEY = <bytes>
```

任何拿到 exe 的人都能提取这些密钥，解密所有通信和本地数据。

### 4.2 方案 A：服务端下发会话密钥（推荐）

```
登录流程：
1. 客户端 → 服务端：Keycloak JWT（证明身份）
2. 服务端 → 客户端：会话密钥（用客户端公钥加密后下发）

通信流程：
3. 客户端用会话密钥加密请求 → 服务端
4. 会话密钥有效期短（如 1 小时），过期重新协商

密钥不在 exe 中：
- 攻击者拿到 exe 也无法解密通信
- 每个用户/会话的密钥不同
- 密钥仅存在内存，用完即销毁
```

实现：
```python
# 客户端
from cryptography.hazmat.primitives.asymmetric import x25519

# 1. 生成临时密钥对
private_key = x25519.X25519PrivateKey.generate()
public_key = private_key.public_key()

# 2. 发送公钥给服务端（附带 JWT 认证）
resp = requests.post(SERVER + "/key-exchange", 
    headers={"Authorization": f"Bearer {jwt}"},
    json={"pubkey": public_key.public_bytes_raw().hex()})

# 3. 服务端返回用此公钥加密的会话密钥
server_pubkey = x25519.X25519PublicKey.from_public_bytes(bytes.fromhex(resp.json()["pubkey"]))
shared_key = private_key.exchange(server_pubkey)  # ECDH 共享密钥

# 4. 派生 AES 密钥
from cryptography.hazmat.primitives.kdf.hkdf import HKDF
session_key = HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"buddy-session").derive(shared_key)

# 5. 后续通信用 session_key 加密
```

### 4.3 方案 B：机器绑定密钥派生

```python
import hashlib, uuid, platform

def derive_machine_key(salt_from_server: bytes) -> bytes:
    """从机器特征 + 服务端 salt 派生唯一密钥"""
    machine_id = str(uuid.getnode())  # MAC 地址
    cpu_id = platform.processor()
    disk = str(hash(str(platform.uname())))
    
    material = f"{machine_id}{cpu_id}{disk}".encode()
    
    # PBKDF2 慢派生，增加暴力成本
    key = hashlib.pbkdf2_hmac('sha256', material, salt_from_server, 100000, dklen=32)
    return key
```

**特点**：
- 每台机器密钥不同
- 换机器/重装系统密钥失效
- 服务端 salt 可定期轮换
- 攻击者即使有 exe，也无法解密其他用户的本地数据

### 4.4 方案 C：Windows DPAPI 本地缓存

```python
import win32crypt

def protect_data(data: bytes) -> bytes:
    """用 Windows DPAPI 加密，绑定当前用户"""
    blob = win32crypt.CryptProtectData(data, None, None, None, None, 0)
    return blob

def unprotect_data(blob: bytes) -> bytes:
    """只有当前用户/机器能解密"""
    _, data = win32crypt.CryptUnprotectData(blob, None, None, None, 0)
    return data

# 用法：服务端下发的密钥用 DPAPI 加密后存本地
encrypted_key = protect_data(session_key)
# 存到 %APPDATA%\BuddyTool\key.dat
# 离线攻击者无法解密（需要用户登录态）
```

### 4.5 方案 D：TPM 2.0 封存（最高强度）

```python
# 需要 TPM 2.0 芯片支持（现代 Windows 机器标配）
# 用 Windows TBS API 或 tpm2-tss 库
# 密钥被封存在 TPM 硬件中，软件层完全无法提取
# 换硬盘/克隆系统都失效
```

**推荐组合**：**服务端下发（方案 A）+ DPAPI 缓存（方案 C）+ 机器绑定（方案 B）**

---

## 五、反分析层加固：增加动态分析成本

### 5.1 反调试检测

#### C 层（修改 Nuitka bootloader，最有效）

```c
// anti_debug.c
#include <windows.h>
#include <winternl.h>

BOOL check_debugger() {
    // 1. 直接 API
    if (IsDebuggerPresent()) return TRUE;
    
    // 2. PEB 检查（绕过 IsDebuggerPresent hook）
    PPEB peb = __readgsqword(0x60);
    if (peb->BeingDebugged) return TRUE;
    
    // 3. 检查 NtGlobalFlag（调试器会设置特定标志）
    DWORD flags = *(DWORD*)(__readgsqword(0x60) + 0xBC);
    if (flags & 0x70) return TRUE;  // FLG_HEAP_ENABLE_TAIL_CHECK etc.
    
    // 4. 检查硬件断点
    CONTEXT ctx = {0};
    ctx.ContextFlags = CONTEXT_DEBUG_REGISTERS;
    GetThreadContext(GetCurrentThread(), &ctx);
    if (ctx.Dr0 || ctx.Dr1 || ctx.Dr2 || ctx.Dr3) return TRUE;
    
    return FALSE;
}

// 检测到调试器后的响应（不要立即退出）
void on_debugger_detected() {
    // 静默 corrupt 关键数据，让程序"看似正常但结果错误"
    // 比如把 AES 密钥的某个字节改掉，解密全错
    // 这样攻击者很难定位是哪里检测到了
}
```

#### Python 层（辅助，效果弱但增加成本）

```python
import os, sys, psutil

DEBUGGER_PROCESSES = {
    'x64dbg.exe', 'x32dbg.exe', 'ida.exe', 'ida64.exe', 
    'ollydbg.exe', 'windbg.exe', 'processhacker.exe',
    'cheatengine-x86_64.exe', 'httpdebugger.exe',
}

def check_debugger_processes():
    for proc in psutil.process_iter(['name']):
        if proc.info['name'] and proc.info['name'].lower() in DEBUGGER_PROCESSES:
            return True
    return False

def check_parent_process():
    parent = psutil.Process(os.getpid()).parent()
    # 检查父进程是否是调试器
    if parent and parent.name().lower() in DEBUGGER_PROCESSES:
        return True
```

### 5.2 反虚拟机/沙箱检测

```python
import platform, subprocess, os

def is_virtual_machine() -> bool:
    # 1. MAC 地址前缀
    mac = hex(uuid.getnode())
    vm_prefixes = ['0x000c29', '0x000569', '0x080027', '0x005056', '0x001c42']
    for prefix in vm_prefixes:
        if mac.startswith(prefix):
            return True
    
    # 2. 注册表检测（Windows）
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                           r"SOFTWARE\VMware, Inc.") as _:
            return True
    except OSError:
        pass
    
    # 3. CPUID hypervisor bit
    # (需要 C 扩展或 ctypes 调用)
    
    # 4. 时间加速检测（沙箱常跳过 sleep）
    import time
    t1 = time.time()
    time.sleep(1.0)
    if time.time() - t1 < 0.9:  # 实际睡眠远小于 1 秒
        return True
    
    return False

def is_sandbox() -> bool:
    # 检测常见沙箱特征
    sandbox_files = [
        r"C:\analysis", r"C:\sandbox",
        r"C:\_analysis",  # Cuckoo
        os.path.expandvars(r"%USERPROFILE%\Desktop\analysis"),  
    ]
    for f in sandbox_files:
        if os.path.exists(f):
            return True
    return False
```

### 5.3 完整性校验

```python
import hashlib, sys, os

def verify_integrity(expected_hash: str) -> bool:
    """校验自身未被篡改"""
    exe_path = sys.executable
    with open(exe_path, 'rb') as f:
        actual = hashlib.sha256(f.read()).hexdigest()
    return actual == expected_hash

# expected_hash 从服务端动态获取（不硬编码）
def get_expected_hash() -> str:
    # 登录后从服务端拉取当前版本的合法 hash
    resp = requests.get(SERVER + "/version/check", 
                       headers={"Authorization": f"Bearer {jwt}"})
    return resp.json()["exe_hash"]

# 检测到篡改后的响应
def on_tamper_detected():
    # 不要立即退出
    # 1. 静默上报（带上机器码）
    # 2. 延迟 30-60 秒后随机崩溃（让攻击者难定位检测点）
    # 3. 或"功能降级"——某些功能静默失效
    pass
```

### 5.4 反内存 Dump

```python
import ctypes

def secure_zero_memory(data: bytearray):
    """安全清零内存，防止 dump 后残留"""
    ctypes.memset(
        (ctypes.c_char * len(data)).from_buffer(data),
        0, len(data)
    )

# 用法：密钥用完立即清零
session_key = bytearray(get_session_key())
try:
    encrypt_data(session_key, plaintext)
finally:
    secure_zero_memory(session_key)  # 用完即毁
```

C 层加固：
```c
// 把关键代码段设为不可读，执行时临时开放
DWORD oldProtect;
VirtualProtect(sensitive_code, size, PAGE_NOACCESS, &oldProtect);
// 执行时：VirtualProtect(..., PAGE_EXECUTE_READ, ...)
// 执行后：VirtualProtect(..., PAGE_NOACCESS, ...)
```

### 5.5 反 Hook 检测

```python
# 检测常见 hook 框架
def check_hooks():
    # Frida 检测
    import ctypes
    try:
        # 检查 frida-agent 是否加载
        ctypes.CDLL('frida-agent')  # 如果能加载说明已被注入
        return True
    except OSError:
        pass
    
    # 检查可疑 DLL
    import ctypes.wintypes
    # 枚举已加载模块，查找 frida-*.dll, detoured.dll 等
```

---

## 六、数据层加固：保护本地存储与数据库

### 6.1 现状问题

```sql
-- 明文 schema，字段含义暴露
CREATE TABLE IF NOT EXISTS accounts (
    auth_token TEXT DEFAULT '',  -- 攻击者知道这里存 token
    api_key TEXT DEFAULT '',     -- 这里存 API Key
    ck TEXT DEFAULT '',          -- 这里存 cookie
);
```

本地 `proxy_db.key` 用弱 XXTEA 加密，密钥硬编码。

### 6.2 加固方案

#### 数据库 Schema 混淆

```sql
-- 不要用有意义的字段名
CREATE TABLE IF NOT EXISTS t1 (
    f1 TEXT PRIMARY KEY,    -- uid
    f2 TEXT DEFAULT '',     -- auth_token (加密)
    f3 TEXT DEFAULT '',     -- api_key (加密)
    f4 INTEGER DEFAULT 0,   -- streak_days
    -- 字段映射表加密存储在代码里
);
```

#### 字段值加密

```python
# 每个敏感字段用机器绑定密钥加密
def encrypt_field(plaintext: str, field_key: bytes) -> str:
    nonce = os.urandom(12)
    cipher = AESGCM(field_key)
    ct = cipher.encrypt(nonce, plaintext.encode(), None)
    return base64.b64encode(nonce + ct).decode()

# 读取时解密
def decrypt_field(ciphertext: str, field_key: bytes) -> str:
    raw = base64.b64decode(ciphertext)
    nonce, ct = raw[:12], raw[12:]
    cipher = AESGCM(field_key)
    return cipher.decrypt(nonce, ct, None).decode()
```

#### 弃用 XXTEA

XXTEA 是过时的弱算法：
- 密钥空间小（实际用 128 位）
- 无认证（无 MAC/GCM tag，可被篡改）
- 公开攻击工具

替换为 **AES-256-GCM** 或 **ChaCha20-Poly1305**（无需硬件 AES-NI 也能高效）。

#### 数据库文件加密

用 **SQLCipher** 替代明文 SQLite：
```python
import pysqlcipher3.dbapi2 as sqlcipher

conn = sqlcipher.connect("data.db")
conn.execute(f"PRAGMA key = '{machine_bound_key}'")  # 机器绑定密钥
# 之后正常操作，整个数据库文件加密
```

SQLCipher 提供：
- 整库 AES-256-CBC 加密
- 每页独立 IV
- HMAC-SHA512 完整性校验
- 机器绑定密钥后，离线无法打开

---

## 七、通信层加固：强化网络传输安全

### 7.1 现状问题

- HTTPS 用标准证书，可被中间人代理（Fiddler/Charles）拦截
- 程序内字符串提到 mitmproxy，说明开发者知道但未防护
- API 签名密钥硬编码，签名可伪造

### 7.2 加固方案

#### Certificate Pinning（证书固定）

```python
import requests
import urllib3
from urllib3.util.ssl_ import create_urllib3_context

# 固定服务端证书的公钥指纹
PINNED_HASH = "sha256/abcdef1234567890..."  # 从服务端获取

class PinnedAdapter(requests.adapters.HTTPAdapter):
    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.verify_flags |= ssl.VERIFY_X509_STRICT
        # 自定义校验逻辑：只接受指纹匹配的证书
        kwargs['ssl_context'] = ctx
        super().init_poolmanager(*args, **kwargs)

session = requests.Session()
session.mount('https://', PinnedAdapter())
```

效果：即使攻击者安装了自签 CA 证书（Fiddler/Charles 的常规手段），也无法拦截流量。

#### 请求签名升级

```python
# 现状：HMAC 密钥硬编码
# 加固：用服务端下发的临时签名密钥

def sign_request(method, path, body, session_secret):
    timestamp = int(time.time())
    nonce = os.urandom(16).hex()
    
    msg = f"{method}\n{path}\n{timestamp}\n{nonce}\n{hashlib.sha256(body).hexdigest()}"
    sig = hmac.new(session_secret, msg.encode(), hashlib.sha256).hexdigest()
    
    return {
        'X-Timestamp': str(timestamp),
        'X-Nonce': nonce,
        'X-Signature': sig,
    }
```

特点：
- session_secret 从服务端获取（不硬编码）
- 每个请求有 nonce 防重放
- body 参与 hash 防篡改

#### 响应加密

现状：服务端响应是 AES-256-GCM 加密，但密钥硬编码。

加固：响应用 ECDH 协商的会话密钥加密，每个会话不同。

---

## 八、针对 BuddyTool 的具体改造路线图

按**性价比**（效果/成本）排序：

### 阶段 1：快速止血（1-3 天，效果显著）

| 序号 | 任务 | 成本 | 效果 |
|---|---|---|---|
| 1.1 | Nuitka 加 `--no-docstrings` | 10 分钟 | 去掉所有"使用说明书" |
| 1.2 | 密钥改服务端下发 + DPAPI 缓存 | 1-2 天 | 彻底解决密钥泄露 |
| 1.3 | URL/SQL/错误信息字符串加密 | 半天 | 消除 80% 静态分析信息 |
| 1.4 | 弃用 XXTEA，改 AES-256-GCM + 机器绑定密钥 | 半天 | 本地存储安全 |

**阶段 1 后效果**：攻击者无法再通过简单 `strings` 提取密钥和 URL，通信无法解密。

### 阶段 2：中度加固（1 周，显著提升）

| 序号 | 任务 | 成本 | 效果 |
|---|---|---|---|
| 2.1 | 源码层符号混淆（PyArmor 或脚本） | 1-2 天 | 消除模块结构信息 |
| 2.2 | bootloader 加 VMProtect 壳 | 半天（需购买） | onefile 难以解包 |
| 2.3 | 自定义 payload 格式（换 magic + AES 加密压缩） | 2-3 天 | 公开解包工具失效 |
| 2.4 | Certificate Pinning | 1 天 | 防中间人抓包 |
| 2.5 | 数据库改 SQLCipher | 1 天 | 本地数据加密 |

**阶段 2 后效果**：逆向需要专家级 1-2 周工作量，且每个版本要重新分析。

### 阶段 3：深度加固（2-3 周，接近商业级）

| 序号 | 任务 | 成本 | 效果 |
|---|---|---|---|
| 3.1 | payload 内存加载（不落盘） | 3-5 天 | 阻止文件提取 |
| 3.2 | C 层反调试（修改 bootloader） | 3-5 天 | 增加动态分析难度 |
| 3.3 | 反 VM/沙箱检测 | 1-2 天 | 阻止自动化分析 |
| 3.4 | 完整性校验 + 篡改上报 | 2 天 | 检测 patch |
| 3.5 | 反 Hook 检测（Frida 等） | 2 天 | 阻止运行时注入 |
| 3.6 | 关键逻辑 C 扩展化 | 5-7 天 | 核心算法下沉到编译层 |

**阶段 3 后效果**：接近商业软件保护水平，逆向需专业团队 1 个月以上。

### 阶段 4：持续运营

| 任务 | 说明 |
|---|---|
| 版本轮换 | 每 1-2 个月更新混淆密钥、反调试特征码 |
| 服务端下发规则 | 反调试规则、完整性 hash 从服务端动态下发，攻击者无法静态分析 |
| 多层校验 | 不同位置重复检测，攻击者 patch 一处还有多处 |
| 蜜罐字段 | 故意放一些"看起来像密钥"的假数据，追踪是否被利用 |

---

## 九、加固效果评估矩阵

| 攻击手段 | 当前 | 阶段1后 | 阶段2后 | 阶段3后 |
|---|---|---|---|---|
| 一键解包工具 | ✅ 5分钟 | ✅ 5分钟 | ❌ 失效 | ❌ 失效 |
| `strings` 提取密钥 | ✅ 10分钟 | ❌ 失效 | ❌ 失效 | ❌ 失效 |
| `strings` 提取 URL | ✅ 10分钟 | ❌ 失效 | ❌ 失效 | ❌ 失效 |
| 静态读 docstring | ✅ 直接读 | ❌ 失效 | ❌ 失效 | ❌ 失效 |
| 解密通信流量 | ✅ 10分钟 | ❌ 失效 | ❌ 失效 | ❌ 失效 |
| 解密本地数据库 | ✅ 10分钟 | ❌ 失效 | ❌ 失效 | ❌ 失效 |
| 符号还原架构 | ✅ 30分钟 | ✅ 30分钟 | ❌ 需逆向 | ❌ 需逆向 |
| 动态调试 | ✅ 无阻碍 | ✅ 无阻碍 | ⚠️ 需绕壳 | ❌ 需绕反调试 |
| 中间人抓包 | ✅ 标准HTTPS | ✅ 标准HTTPS | ❌ Pinning | ❌ Pinning |
| 沙箱自动分析 | ✅ 无阻碍 | ✅ 无阻碍 | ⚠️ 需绕壳 | ❌ 反VM检测 |
| 完整逆向 | **1小时** | **1天** | **1-2周** | **1个月+** |

---

## 十、重要现实提醒与合规边界

### 10.1 防分析的终极真相

**没有任何方案能 100% 防止逆向**。客户端软件的安全目标是：

> **提高攻击成本，让攻击收益低于成本。**

- 如果破解一个软件需要 1 个月专家工作，但软件授权费只有 50 元/月，没人会去破解
- 如果核心价值在服务端（密钥、算法、数据），客户端被逆向也无妨

### 10.2 真正的机密永远在服务端

| 放客户端 | 放服务端 |
|---|---|
| ❌ AES 加密密钥 | ✅ 加密密钥 |
| ❌ API 签名密钥 | ✅ 签名密钥 |
| ❌ 上游 API Key 池 | ✅ Key 池管理 |
| ❌ 核心业务算法 | ✅ 核心算法 |
| ✅ UI 代码 | ✅ 配置数据 |
| ✅ 本地缓存逻辑 | ✅ 授权校验 |

BuddyTool 当前把所有敏感数据都放客户端，这是根本问题。即使加固到极致，也只是延缓泄露。

### 10.3 防分析 ≠ 合法

特别需要指出：**加固技术不改变软件的合法性质**。

根据前三轮分析，BuddyTool 涉及以下**敏感行为**：
- 从 WorkBuddy 客户端离线提取 access token（`_decrypt_vscdb_secret`）
- 向 WorkBuddy 注入积分（`inject_credits_to_workbuddy`）
- 清理 WorkBuddy 数据库会话（`_clear_workbuddy_db_sessions`）
- 密钥池轮转转发 AI 请求（可能违反上游服务条款）
- 自动签到刷奖励

这些行为可能涉及：
- **未授权访问计算机系统**（《刑法》第285条）
- **破坏计算机信息系统**（《刑法》第286条）
- **侵犯著作权/商业秘密**
- **违反服务条款的民事责任**

**加固只是延缓被发现，不改变法律性质。** 如果软件本身违法，加固反而可能加重量刑（"主观恶性"）。

### 10.4 合法的防分析场景

防逆向技术在以下场景是**完全合法**的：
- 保护自有知识产权（自研算法、业务逻辑）
- 防止作弊（游戏反外挂）
- 保护用户隐私（本地数据加密）
- 满足合规要求（PCI-DSS、等保要求客户端保护）
- 防止许可证绕过（付费软件防盗版）

---

## 附录：关键工具与资源

### 字符串/符号保护
| 工具 | 用途 | 链接 |
|---|---|---|
| PyArmor | Python 字节码混淆、字符串加密 | https://pyarmor.dashingsoft.com |
| Cython | Python → C 编译（替代 Nuitka） | https://cython.org |
| Nuitka `--no-docstrings` | 去除文档字符串 | https://nuitka.net |

### 商业壳
| 工具 | 平台 | 特性 |
|---|---|---|
| VMProtect | Windows/Linux | 代码虚拟化、反调试 |
| Themida | Windows | 多层加密、反dump |
| Enigma Protector | Windows | 文件加密、许可证 |
| Safengine Shielden | Windows | 虚拟机引擎 |

### 密钥管理
| 技术 | 说明 |
|---|---|
| Windows DPAPI | `CryptProtectData`/`CryptUnprotectData`，绑定用户 |
| TPM 2.0 | 硬件封存密钥 |
| ECDH (X25519) | 前向保密的密钥协商 |
| SQLCipher | SQLite 透明加密 |

### 反分析
| 技术 | 说明 |
|---|---|
| IsDebuggerPresent + PEB 检查 | 反调试基础 |
| CPUID hypervisor bit | 反虚拟机 |
| Certificate Pinning | 防中间人 |
| 完整性校验 | 防篡改 |
| Frida 检测 | 防 hook 注入 |

### 检测工具（用于自测加固效果）
| 工具 | 用途 |
|---|---|
| Detect It Easy (DIE) | 检测壳/编译器/特征 |
| PEiD | PE 文件特征识别 |
| Process Monitor | 监控文件/注册表访问 |
| x64dbg | 动态调试（测试反调试） |
| Frida | 运行时 hook（测试反 hook） |
| `strings` | 字符串提取（测试字符串加密效果） |

---

## 总结

BuddyTool v1.1.5 当前处于**"零防护"**状态，1 小时内可被完全逆向。根本原因是：
1. 敏感数据（密钥、URL、算法）全放客户端
2. 打包方式标准化
3. 无任何反分析措施

最小化改造（阶段 1，1-3 天）即可解决 80% 问题：**密钥服务端化 + 字符串加密 + 去 docstring**。

但要达到商业级防护，需要系统性加固（阶段 2-3，1 个月），核心思路是：**让客户端不含任何真正的机密，所有敏感逻辑和密钥都在服务端。**

最终原则：**客户端加固是"提高成本"，服务端架构才是"安全保障"。**
