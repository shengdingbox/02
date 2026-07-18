# Buddy Server API 接口文档

> Base URL: `http://47.83.145.136:8787`
> 版本: v1.1.0

---

## 加密方案

### 概述

公开接口（无需鉴权的 POST 接口）**强制使用** AES-256-GCM 加密传输。请求体必须加密，明文请求将被拒绝（返回 400）。响应体始终加密返回。

### AES-256-GCM 加密

| 项目 | 值 |
|------|-----|
| 算法 | AES-256-GCM |
| 密钥 (AES_KEY) | `38502350408f8d5011606fc186daa626196beac6a529d7b79b30e713a0c6f2f0` (hex, 32字节) |
| Nonce | 12 字节随机数 |
| Tag | 16 字节认证标签 |
| 密文格式 | `base64(nonce(12) + tag(16) + ciphertext)` |
| 传输格式 | `{"data": "<base64密文>"}` |

### HMAC-SHA256 签名 (V1)

所有公开接口**必须**携带签名请求头，否则返回 401。

| 请求头 | 说明 |
|--------|------|
| `X-API-Key` | API Key，固定值 `buddy_707d23cb0832fb0f0fc4a3d7` |
| `X-Timestamp` | 当前 Unix 时间戳（秒），服务端允许 ±300 秒误差 |
| `X-API-Sign` | HMAC-SHA256 签名 |
| `X-Sign-Method` | 固定值 `hmac-sha256` |

**签名算法**:
```
HMAC_KEY = "db1a906d80eb73a82d3ded42ffb64be5"
message = "api_key={API_Key}&timestamp={timestamp}"
sign = HMAC-SHA256(HMAC_KEY, message)  # 返回 hex 字符串
```

**Python 签名示例**:
```python
import hmac, hashlib, time

API_KEY = "buddy_707d23cb0832fb0f0fc4a3d7"
HMAC_KEY = b"db1a906d80eb73a82d3ded42ffb64be5"

timestamp = str(int(time.time()))
msg = f"api_key={API_KEY}&timestamp={timestamp}"
sign = hmac.new(HMAC_KEY, msg.encode("utf-8"), hashlib.sha256).hexdigest()

headers = {
    "X-API-Key": API_KEY,
    "X-Timestamp": timestamp,
    "X-API-Sign": sign,
    "X-Sign-Method": "hmac-sha256",
    "Content-Type": "application/json",
}
```

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

AES_KEY = bytes.fromhex("38502350408f8d5011606fc186daa626196beac6a529d7b79b30e713a0c6f2f0")

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
import requests, hmac, hashlib, time

API_KEY = "buddy_707d23cb0832fb0f0fc4a3d7"
HMAC_KEY = b"db1a906d80eb73a82d3ded42ffb64be5"

timestamp = str(int(time.time()))
msg = f"api_key={API_KEY}&timestamp={timestamp}"
sign = hmac.new(HMAC_KEY, msg.encode("utf-8"), hashlib.sha256).hexdigest()

enc_body = encrypt_body({"cardKey": "BC_xxx", "userKey": "bc_xxx", "operator": "user"})
resp = requests.post("http://47.83.145.136:8787/api/redeem",
                     data=enc_body,
                     headers={
                         "Content-Type": "application/json",
                         "X-API-Key": API_KEY,
                         "X-Timestamp": timestamp,
                         "X-API-Sign": sign,
                         "X-Sign-Method": "hmac-sha256",
                     })
result = decrypt_body(resp.text)
print(result)
```

### JavaScript 客户端示例

```javascript
// 使用 Web Crypto API (浏览器原生)
// 注意: Web Crypto 的 AES-GCM 输出为 ciphertext+tag 拼接（tag 在末尾），
// 与服务端格式 nonce(12) + tag(16) + ciphertext 不同，需要手动重排字节。
async function encryptBody(data) {
  const keyHex = "38502350408f8d5011606fc186daa626196beac6a529d7b79b30e713a0c6f2f0";
  const keyBytes = new Uint8Array(keyHex.match(/.{2}/g).map(b => parseInt(b, 16)));
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["encrypt"]);

  const plaintext = new TextEncoder().encode(JSON.stringify(data));
  const nonce = crypto.getRandomValues(new Uint8Array(12));
  // Web Crypto 把 tag(16) 附在 ciphertext 末尾
  const ctWithTag = new Uint8Array(
    await crypto.subtle.encrypt({ name: "AES-GCM", iv: nonce, tagLength: 128 }, key, plaintext)
  );
  const ciphertext = ctWithTag.subarray(0, ctWithTag.length - 16);
  const tag = ctWithTag.subarray(ctWithTag.length - 16);

  // 服务端格式: nonce(12) + tag(16) + ciphertext
  const raw = new Uint8Array(12 + 16 + ciphertext.length);
  raw.set(nonce, 0);
  raw.set(tag, 12);
  raw.set(ciphertext, 28);
  const dataB64 = btoa(String.fromCharCode(...raw));
  return JSON.stringify({ data: dataB64 });
}

async function decryptBody(bodyText) {
  const keyHex = "38502350408f8d5011606fc186daa626196beac6a529d7b79b30e713a0c6f2f0";
  const keyBytes = new Uint8Array(keyHex.match(/.{2}/g).map(b => parseInt(b, 16)));
  const key = await crypto.subtle.importKey("raw", keyBytes, { name: "AES-GCM" }, false, ["decrypt"]);

  const bodyJson = JSON.parse(bodyText);
  const raw = Uint8Array.from(atob(bodyJson.data), c => c.charCodeAt(0));
  const nonce = raw.slice(0, 12);
  const tag = raw.slice(12, 28);
  const ciphertext = raw.slice(28);
  // Web Crypto 需要 ciphertext+tag 拼接
  const ctWithTag = new Uint8Array(ciphertext.length + tag.length);
  ctWithTag.set(ciphertext, 0);
  ctWithTag.set(tag, ciphertext.length);
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

> 以下接口均需携带签名请求头并加密请求体，响应也加密返回。

### 1. 卡密兑换

```
POST /api/redeem
```

**请求体**（加密）:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| cardKey | string | 是 | 卡密 (BC_ 前缀) |
| userKey | string | 是 | 机器码 (bc_ 前缀) |
| operator | string | 否 | 操作者标识 |

**处理流程**:
1. 校验签名 + 解密请求体
2. 机器码不存在时自动创建（余额 0）
3. 调用 `store.redeem` 扣减卡密余额、增加机器码余额
4. 写入 `buddy_redeem_records` 兑换记录

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

**请求体**（加密）:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| userKey | string | 是 | 机器码 (bc_ 前缀) |

**处理流程**:
1. 查机器码余额 → 不存在返回 404，≤0 返回"余额不足"
2. 查 `buddy_buddy_keys` 表中余额 > 100 的可用记录
3. 有则直接分配返回
4. 无则调 DataPulse 上游获取 → 解密 `encrypted_key` → 存表（去重）→ 分配 → 返回

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

**余额不足**（加密，解密后）:
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

**请求体**（加密）:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| device_fingerprint | string | 是 | 设备码（机器码） |
| record_id | string | 否 | 记录ID |
| credits_used | number | 是 | 消耗积分 |
| model | string | 否 | 模型名称 |
| request_tokens | integer | 否 | 请求token数 |
| response_tokens | integer | 否 | 响应token数 |
| upstream_id | string | 否 | 上游ID（获取的key） |

**处理流程**:
1. 校验签名 + 解密请求体
2. 扣减机器码余额，写入 `buddy_usage_reports`

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
POST /api/user/credits
```

**请求体**（必须加密）:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| userKey | string | 是 | 机器码 |

**说明**: 机器码不存在或查询异常时，返回全 0 而非报错。

**响应**（加密，解密后）:
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
      "nodeId": null,
      "phone": null,
      "tokens": 1500,
      "note": null,
      "userNote": null,
      "clientIp": null,
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

### 7. 版本检查

```
POST /api/version/check
```

**请求体**（必须加密）:

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| platform | string | 否 | 平台 (win/mac/linux/all)，默认 win |
| current_version | string | 否 | 当前版本号 |

**响应**（加密，解密后）:
```json
{
  "has_update": true,
  "version": "1.1.0",
  "latest_version": "1.1.0",
  "platform": "win",
  "download_url": "https://example.com/download/v1.1.0.exe",
  "changelog": "1. 新增签到功能\n2. 修复已知问题",
  "min_version": "1.0.0",
  "is_force_update": false,
  "created_at": "2026-07-16T10:00:00+00:00"
}
```

---

### 8. 获取可用模型列表

```
POST /api/models/list
```

**请求体**（必须加密）: 无必填字段，传空对象 `{}` 即可，仅用于校验加密签名。

**响应**（加密，解密后）:
```json
{
  "models": [
    {
      "id": "gpt-4",
      "name": "GPT-4",
      "maxInputTokens": 128000,
      "maxOutputTokens": 8192,
      "supportsToolCall": true,
      "supportsImages": true,
      "supportsReasoning": false
    }
  ]
}
```

---

## 管理接口（需鉴权）

> 所有管理接口需携带请求头: `Authorization: Bearer <ADMIN_API_KEY>`
> 默认 ADMIN_API_KEY: `xiaobaobuddy`

### 卡密管理

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 1 | POST | `/api/admin/cards` | 创建卡密（body: `{"initialCredits": 1000}`） |
| 2 | POST | `/api/admin/cards/batch` | 批量创建卡密（body: `{"count": 5, "initialCredits": 1000}`，返回 `{"keys": [...], "count": 5}`） |
| 3 | GET | `/api/admin/cards?limit=20&offset=0` | 卡密列表 |
| 4 | GET | `/api/admin/cards/:key` | 卡密详情 |
| 5 | POST | `/api/admin/cards/:key/recharge` | 卡密充值（body: `{"credits": 100}`） |
| 6 | DELETE | `/api/admin/cards/:key` | 删除卡密 |

### 兑换记录

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 7 | GET | `/api/admin/redeem-records?limit=20&offset=0&userKey=&cardKey=` | 兑换记录列表 |

### 机器码管理

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 8 | GET | `/api/admin/machines?limit=20&offset=0&search=` | 机器码列表（含兑换汇总） |
| 9 | GET | `/api/admin/machines/:key` | 机器码详情（含最近10条兑换） |
| 10 | POST | `/api/admin/machines/:key/recharge` | 机器码充值（body: `{"credits": 100}`，不存在则自动创建） |

### BuddyKey 管理

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 11 | GET | `/api/admin/buddy-keys?limit=20&offset=0&status=&search=` | BuddyKey列表 |
| 12 | POST | `/api/admin/buddy-keys/:id/balance` | 修改余额（body: `{"balance": 50}`） |
| 13 | POST | `/api/admin/buddy-keys/:id/refresh` | 刷新单个上游积分 |
| 14 | POST | `/api/admin/buddy-keys/:id/checkin` | 单个签到 |
| 15 | POST | `/api/admin/buddy-keys/refresh-all` | 全部刷新积分 |
| 16 | POST | `/api/admin/buddy-keys/checkin-all` | 全部签到 |
| 17 | DELETE | `/api/admin/buddy-keys/:id` | 删除BuddyKey |

### 使用记录

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 18 | GET | `/api/admin/usage-reports?limit=20&offset=0&device=&search=` | 使用记录列表 |

### 版本管理

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 19 | GET | `/api/admin/versions?limit=20&offset=0&platform=` | 版本列表 |
| 20 | POST | `/api/admin/versions` | 创建版本 |
| 21 | POST | `/api/admin/versions/:id` | 编辑版本 |
| 22 | DELETE | `/api/admin/versions/:id` | 删除版本 |

### 模型管理

| # | 方法 | 路径 | 说明 |
|---|------|------|------|
| 23 | GET | `/api/admin/models?limit=50&offset=0&search=` | 模型列表 |
| 24 | POST | `/api/admin/models` | 创建模型 |
| 25 | POST | `/api/admin/models/:dbId` | 编辑模型 |
| 26 | DELETE | `/api/admin/models/:dbId` | 删除模型 |

**创建/编辑模型 body 字段**:

| 字段 | 类型 | 说明 |
|------|------|------|
| model_id (或 id) | string | 模型ID，如 `gpt-4` |
| name | string | 模型名称 |
| max_input_tokens (或 maxInputTokens) | integer | 最大输入token，默认 128000 |
| max_output_tokens (或 maxOutputTokens) | integer | 最大输出token，默认 8192 |
| supports_tool_call (或 supportsToolCall) | bool | 是否支持工具调用 |
| supports_images (或 supportsImages) | bool | 是否支持图片 |
| supports_reasoning (或 supportsReasoning) | bool | 是否支持推理 |
| sort_order | integer | 排序权重，默认 0 |
| is_active | bool | 是否启用，默认 true |

---

## 静态页面

| 路径 | 页面 | 说明 |
|------|------|------|
| `/xiaofeibuddy/` | 卡密管理 | 管理后台创建/充值/删除卡密 |
| `/redeem/` | 卡密兑换 | 用户输入卡密+机器码兑换 |
| `/records/` | 兑换记录 | 管理后台查看兑换流水 |
| `/usagereports/` | 使用记录 | 管理后台查看使用上报 |
| `/machines/` | 机器码管理 | 管理后台管理机器码额度 |
| `/buddykeys/` | BuddyKey管理 | 管理后台管理激活码 |
| `/versions/` | 版本管理 | 管理后台管理版本发布 |
| `/models/` | 模型管理 | 管理后台管理可用模型 |

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

- **加密接口**: `/api/redeem`、`/api/buddykey/get`、`/api/usage/report`、`/api/user/credits`、`/api/version/check`、`/api/models/list` — 请求必须加密并携带签名头，响应加密返回
- **明文接口**: `GET /api/user/today-usage`、`POST /api/activate`、所有管理接口使用明文 JSON
