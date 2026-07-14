# Buddy Server API 接口文档

> Base URL: `http://127.0.0.1:8787`
> 版本: v1.0.0

---

## 加密方案

### 概述

公开接口（无需鉴权的 POST 接口）支持 **AES-256-GCM 加密传输**。客户端可选择加密或明文发送请求，服务端会自动识别。响应体始终加密返回。

### AES-256-GCM 加密

| 项目 | 值 |
|------|-----|
| 算法 | AES-256-GCM |
| 密钥 (AES_KEY) | `e7283867e8d5a1da2f67de4727f12e26ca4d2f7ae83e51dd208d18e75016ed4a` (hex, 32字节) |
| Nonce | 12 字节随机数 |
| Tag | 16 字节认证标签 |
| 密文格式 | `base64(nonce(12) + tag(16) + ciphertext)` |
| 传输格式 | `{"data": "<base64密文>"}` |

### 请求体加密流程

```
1. 将原始 JSON 序列化为紧凑字符串 (无空格)
   例如: {"cardKey":"BC_xxx","userKey":"bc_xxx"}

2. 生成 12 字节随机 nonce

3. AES-256-GCM 加密:
   cipher = AES.new(AES_KEY, AES.MODE_GCM, nonce=nonce)
   ciphertext, tag = cipher.encrypt_and_digest(plaintext_bytes)

4. 拼接: raw = nonce(12) + tag(16) + ciphertext

5. Base64 编码: data_b64 = base64(raw)

6. 包装为 JSON: {"data": "<data_b64>"}

7. 作为请求体发送, Content-Type: application/json
```

### 响应体解密流程

```
1. 响应头 X-Encrypted: 1 表示响应已加密

2. 解析响应 JSON: {"data": "<base64密文>"}

3. Base64 解码: raw = base64_decode(data)

4. 分拆: nonce = raw[:12], tag = raw[12:28], ciphertext = raw[28:]

5. AES-256-GCM 解密:
   cipher = AES.new(AES_KEY, AES.MODE_GCM, nonce=nonce)
   plaintext = cipher.decrypt_and_verify(ciphertext, tag)

6. JSON 解析得到原始响应数据
```

### Python 客户端示例

```python
import json, base64, os
from Crypto.Cipher import AES

AES_KEY = bytes.fromhex("e7283867e8d5a1da2f67de4727f12e26ca4d2f7ae83e51dd208d18e75016ed4a")

def encrypt_body(data: dict) -> str:
    """加密请求体"""
    raw_pt = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    cipher = AES.new(AES_KEY, AES.MODE_GCM, nonce=nonce)
    ciphertext, tag = cipher.encrypt_and_digest(raw_pt)
    raw = nonce + tag + ciphertext
    data_b64 = base64.b64encode(raw).decode("ascii")
    return json.dumps({"data": data_b64})

def decrypt_body(body_text: str) -> dict:
    """解密响应体"""
    body_json = json.loads(body_text)
    data_b64 = body_json["data"]
    raw = base64.b64decode(data_b64)
    nonce, tag, ct = raw[:12], raw[12:28], raw[28:]
    cipher = AES.new(AES_KEY, AES.MODE_GCM, nonce=nonce)
    pt = cipher.decrypt_and_verify(ct, tag)
    return json.loads(pt.decode("utf-8"))

# 示例: 加密请求兑换接口
import requests
enc_body = encrypt_body({"cardKey": "BC_xxx", "userKey": "bc_xxx", "operator": "user"})
resp = requests.post("http://127.0.0.1:8787/api/redeem",
                     data=enc_body,
                     headers={"Content-Type": "application/json"})
result = decrypt_body(resp.text)
print(result)
```

### JavaScript 客户端示例

```javascript
// 使用 Web Crypto API (浏览器原生)
async function encryptBody(data) {
  const keyHex = "e7283867e8d5a1da2f67de4727f12e26ca4d2f7ae83e51dd208d18e75016ed4a";
  const keyBytes = new Uint8Array(keyHex.match(/.{2}/g).map(b => parseInt(b, 16)));
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["encrypt"]);

  const plaintext = new TextEncoder().encode(JSON.stringify(data));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  const ciphertext = await crypto.subtle.encrypt(
    { name: "AES-GCM", iv: nonce, tagLength: 128 },
    key,
    plaintext
  );

  // nonce(12) + ciphertext+tag(16)
  const raw = new Uint8Array(12 + ciphertext.byteLength);
  raw.set(nonce, 0);
  raw.set(new Uint8Array(ciphertext), 12);
  const dataB64 = btoa(String.fromCharCode(...raw));
  return JSON.stringify({ data: dataB64 });
}

async function decryptBody(bodyText) {
  const keyHex = "e7283867e8d5a1da2f67de4727f12e26ca4d2f7ae83e51dd208d18e75016ed4a";
  const keyBytes = new Uint8Array(keyHex.match(/.{2}/g).map(b => parseInt(b, 16)));
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["decrypt"]);

  const bodyJson = JSON.parse(bodyText);
  const raw = Uint8Array.from(atob(bodyJson.data), c => c.charCodeAt(255));
  const nonce = raw.slice(0, 12);
  const ctWithTag = raw.slice(12);
  const plaintext = await crypto.subtle.decrypt(
    { name: "AES-GCM", iv: nonce, tagLength: 128 },
    key,
    ctWithTag
  );
  return JSON.parse(new TextDecoder().decode(plaintext));
}
```

---

## 公开接口（无需鉴权）

### 1. 卡密兑换

```
POST /api/redeem
```

**请求体**（支持加密）:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| cardKey | string | 是 | 卡密 (BC_ 前缀) |
| userKey | string | 是 | 机器码 (bc_ 前缀) |
| operator | string | 否 | 操作者标识 |

**加密请求示例**:
```json
{"data": "加密后的base64字符串"}
```

**明文请求示例**（兼容）:
```json
{"cardKey": "BC_xxx", "userKey": "bc_xxx", "operator": "user"}
```

**成功响应**（加密，解密后）:
```json
{
  "success": true,
  "cardKey": "BC_xxx",
  "userKey": "bc_xxx",
  "amount": 1000.0,
  "balanceCredits": 1000.0,
  "operator": "user"
}
```

**失败响应**（加密，解密后）:
```json
{"error": "Invalid cardKey"}
```

---

### 2. 获取激活码 (BuddyKey)

```
POST /api/buddykey/get
```

**请求体**（支持加密）:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| userKey | string | 是 | 机器码 (bc_ 前缀) |

**处理流程**:
1. 查机器码余额 → ≤0 返回"余额不足"
2. 查 `buddy_keys` 表中余额 > 100 的可用记录
3. 有则直接分配返回
4. 无则调 DataPulse 上游获取 → 存表 → 分配 → 解密 → 返回

**成功响应**（加密，解密后）:
```json
{
  "success": true,
  "userKey": "bc_xxx",
  "buddyKey": "ck_frwcgvuwnu2o.NXtiXziMcq0QeHZgkrflm1JkTPaxn4NY5cZ15fHmsZk",
  "expiresAt": "2026-08-01 15:07:34",
  "balance": 998.5,
  "buddyKeyId": 1
}
```

**余额不足**:
```json
{
  "success": false,
  "error": "余额不足，请先兑换卡密",
  "balance": 0.0,
  "userKey": "bc_xxx"
}
```

---

### 3. 使用量上报

```
POST /api/usage/report
```

**请求体**（支持加密）:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| device_fingerprint | string | 是 | 设备码（机器码） |
| record_id | string | 否 | 记录ID |
| credits_used | number | 是 | 消耗积分 |
| model | string | 否 | 模型名称 |
| request_tokens | integer | 否 | 请求token数 |
| response_tokens | integer | 否 | 响应token数 |
| upstream_id | string | 否 | 上游ID（获取的key） |

**成功响应**（加密，解密后）:
```json
{
  "success": true,
  "device_fingerprint": "bc_xxx",
  "credits_used": 1.5,
  "balance_before": 1000.0,
  "balance_after": 998.5,
  "report_id": 1
}
```

---

### 4. 查询用户积分

```
GET /api/user/credits?userKey=bc_xxx
```

**Query 参数**:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| userKey | string | 是 | 机器码/上游key |

**响应**（明文）:
```json
{
  "credits": 100.0,
  "totalUsed": 50.0,
  "totalRecharged": 150.0,
  "todayUsed": 0,
  "todayRank": 1,
  "userKey": "bc_xxx"
}
```

---

### 5. 查询今日用量

```
GET /api/user/today-usage?userKey=bc_xxx
```

**响应**（明文）:
```json
{
  "records": [
    {
      "id": 1,
      "userKey": "bc_xxx",
      "amount": 1.5,
      "balanceAfter": 998.5,
      "model": "gpt-4",
      "tokens": 1500,
      "note": "redeem from BC_xxx",
      "createdAt": "2026-07-14T10:00:00+00:00"
    }
  ]
}
```

---

### 6. 激活 Token

```
POST /api/activate
```

**请求体**（明文）:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| keyword | string | 是 | 搜索关键词 |

**成功响应**:
```json
{
  "success": true,
  "buddyKey": "sk-xxxxx"
}
```

---

## 管理接口（需鉴权）

> 所有管理接口需携带请求头: `Authorization: Bearer <ADMIN_API_KEY>`
> 默认 ADMIN_API_KEY: `admin`

### 卡密管理

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | POST | `/api/admin/cards` | 创建卡密（body: `{"initialCredits": 1000}`） |
| 2 | GET | `/api/admin/cards?limit=20&offset=0` | 卡密列表 |
| 3 | GET | `/api/admin/cards/:key` | 卡密详情 |
| 4 | POST | `/api/admin/cards/:key/recharge` | 卡密充值（body: `{"credits": 100}`） |

### 兑换记录

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 5 | GET | `/api/admin/redeem-records?limit=20&offset=0&userKey=&cardKey=` | 兑换记录列表 |

### 机器码管理

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 6 | GET | `/api/admin/machines?limit=20&offset=0&search=` | 机器码列表（含兑换汇总） |
| 7 | GET | `/api/admin/machines/:key` | 机器码详情（含最近10条兑换） |
| 8 | POST | `/api/admin/machines/:key/recharge` | 机器码充值（body: `{"credits": 100}`） |

### BuddyKey 管理

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 9 | GET | `/api/admin/buddy-keys?limit=20&offset=0&status=&search=` | BuddyKey列表 |
| 10 | POST | `/api/admin/buddy-keys/:id/balance` | 修改余额（body: `{"balance": 50}`） |
| 11 | DELETE | `/api/admin/buddy-keys/:id` | 删除BuddyKey |

### 使用记录

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 12 | GET | `/api/admin/usage-reports?limit=20&offset=0&device=&search=` | 使用记录列表 |

---

## 静态页面

| 路径 | 页面 | 说明 |
|------|------|------|
| `/redeem/` | 卡密兑换 | 用户输入卡密+机器码兑换 |
| `/records/` | 兑换记录 | 管理后台查看兑换流水 |
| `/usagereports/` | 使用记录 | 管理后台查看使用上报 |
| `/machines/` | 机器码管理 | 管理后台管理机器码额度 |
| `/buddykeys/` | BuddyKey管理 | 管理后台管理激活码 |
| `/admin/` | 卡密管理 | 管理后台创建/充值卡密 |

---

## 通用说明

### CORS

所有接口响应包含以下 CORS 头:
```
Access-Control-Allow-Origin: *
Access-Control-Allow-Methods: GET, POST, PUT, DELETE, PATCH, OPTIONS
Access-Control-Allow-Headers: Authorization, Content-Type, x-api-key
```

### OPTIONS 预检

所有路径支持 `OPTIONS` 方法，返回 `204 No Content` + CORS 头。

### 加密兼容性

- **请求**: 服务端自动检测请求体格式，加密格式 `{"data": "..."}` 和明文 JSON 均可接受
- **响应**: 加密接口的响应始终为加密格式（响应头 `X-Encrypted: 1`），GET 接口响应为明文
- **加密接口**: `POST /api/redeem`、`POST /api/buddykey/get`、`POST /api/usage/report`
- **明文接口**: 所有 GET 接口、`POST /api/activate`、所有管理接口
