"""服务端 API 客户端 — 积分查询、卡密兑换等

与 http://47.83.145.136:8787 通信，支持 AES-256-GCM 加密传输 + HMAC-SHA256 签名。
"""

import json
import base64
import os
import time
import hmac
import hashlib
import logging
import requests

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

SERVER_BASE = "http://47.83.145.136:8787"

# AES-256-GCM 密钥（与服务端一致，hex → 32 字节）
_AES_KEY_HEX = "e7283867e8d5a1da2f67de4727f12e26ca4d2f7ae83e51dd208d18e75016ed4a"
_AES_KEY = bytes.fromhex(_AES_KEY_HEX)

# HMAC-SHA256 签名
_API_KEY = "buddy-public"
_HMAC_KEY = b"d091d26fa339be10d3eabd28419ec943"

# 绕过系统代理，直连服务端
_NO_PROXY = {"http": None, "https": None}


def _build_signed_headers() -> dict:
    """构建带 HMAC-SHA256 签名的请求头"""
    timestamp = str(int(time.time()))
    msg = f"api_key={_API_KEY}&timestamp={timestamp}"
    sign = hmac.new(_HMAC_KEY, msg.encode("utf-8"), hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-API-Key": _API_KEY,
        "X-Timestamp": timestamp,
        "X-API-Sign": sign,
        "X-Sign-Method": "hmac-sha256",
    }


def _encrypt_body(data: dict) -> str:
    """AES-256-GCM 加密请求体

    流程:
        1. JSON 紧凑序列化
        2. 随机 12 字节 nonce
        3. AES-256-GCM 加密 → ciphertext+tag
        4. 拼接 nonce + ciphertext_and_tag → base64
        5. 包装为 {"data": "<base64>"}

    Returns:
        加密后的 JSON 字符串
    """
    plaintext = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    aesgcm = AESGCM(_AES_KEY)
    # cryptography 库的 encrypt 返回 ciphertext+tag（tag 在末尾）
    ct_and_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)

    # 服务端格式: nonce(12) + tag(16) + ciphertext
    # cryptography 库输出: ciphertext + tag(16)
    # 需要拆分重组: ciphertext = ct_and_tag[:-16], tag = ct_and_tag[-16:]
    ciphertext = ct_and_tag[:-16]
    tag = ct_and_tag[-16:]
    raw = nonce + tag + ciphertext
    data_b64 = base64.b64encode(raw).decode("ascii")
    return json.dumps({"data": data_b64})


def _decrypt_body(body_text: str) -> dict:
    """AES-256-GCM 解密响应体

    Args:
        body_text: 响应体原始文本

    Returns:
        解密后的 dict，如果非加密格式则直接 JSON 解析
    """
    try:
        body_json = json.loads(body_text)
    except Exception:
        return {"error": "响应非有效 JSON", "raw": body_text[:500]}

    # 非加密响应（GET 接口等），直接返回
    if "data" not in body_json:
        return body_json

    data_b64 = body_json["data"]
    raw = base64.b64decode(data_b64)

    # 服务端格式: nonce(12) + tag(16) + ciphertext
    nonce = raw[:12]
    tag = raw[12:28]
    ciphertext = raw[28:]

    # cryptography 库需要 ciphertext+tag 拼接
    ct_and_tag = ciphertext + tag
    aesgcm = AESGCM(_AES_KEY)
    try:
        plaintext = aesgcm.decrypt(nonce, ct_and_tag, associated_data=None)
        return json.loads(plaintext.decode("utf-8"))
    except Exception as e:
        logger.error(f"解密响应失败: {e}")
        return {"error": f"解密失败: {e}"}


def get_credits(user_key: str = None) -> dict:
    """查询用户积分额度（POST 加密接口）

    Args:
        user_key: 用户密钥（机器码），为空时使用本机动态机器码

    Returns:
        {
            "credits": float,
            "totalUsed": float,
            "totalRecharged": float,
            "todayUsed": float,
            "todayRank": int,
            "userKey": str,
        }
        失败时返回 {"error": "..."}
    """
    from .machine import get_machine_code

    key = user_key or get_machine_code()
    url = f"{SERVER_BASE}/api/user/credits"
    payload = {"userKey": key}

    try:
        encrypted_body = _encrypt_body(payload)
        resp = requests.post(
            url,
            data=encrypted_body,
            headers=_build_signed_headers(),
            timeout=15,
            proxies=_NO_PROXY,
        )
        if resp.ok:
            return _decrypt_body(resp.text)
        else:
            return {"error": f"HTTP {resp.status_code}: {resp.text[:200]}"}
    except Exception as e:
        logger.error(f"查询积分失败: {e}")
        return {"error": str(e)}


def redeem(card_key: str, user_key: str = None, operator: str = "user") -> dict:
    """卡密兑换（POST 加密接口）

    Args:
        card_key: 卡密 (BC_ 前缀)
        user_key: 机器码，为空时使用本机动态机器码
        operator: 操作者标识

    Returns:
        成功: {"success": true, "cardKey": "...", "userKey": "...", "amount": ..., "balanceCredits": ...}
        失败: {"error": "..."} 或 {"success": false, ...}
    """
    from .machine import get_machine_code

    key = user_key or get_machine_code()
    url = f"{SERVER_BASE}/api/redeem"

    payload = {
        "cardKey": card_key,
        "userKey": key,
        "operator": operator,
    }

    try:
        encrypted_body = _encrypt_body(payload)
        resp = requests.post(
            url,
            data=encrypted_body,
            headers=_build_signed_headers(),
            timeout=30,
            proxies=_NO_PROXY,
        )
        # 响应始终加密
        return _decrypt_body(resp.text)
    except Exception as e:
        logger.error(f"卡密兑换失败: {e}")
        return {"success": False, "message": str(e)}


def get_buddykey(user_key: str = None) -> dict:
    """获取激活码 BuddyKey（POST 加密接口）

    Args:
        user_key: 机器码，为空时使用本机动态机器码

    Returns:
        成功: {"success": true, "userKey": "...", "buddyKey": "ck_...", "expiresAt": "...", "balance": ..., "buddyKeyId": int}
        失败: {"success": false, "error": "..."}
    """
    from .machine import get_machine_code

    key = user_key or get_machine_code()
    url = f"{SERVER_BASE}/api/buddykey/get"

    payload = {"userKey": key}

    try:
        encrypted_body = _encrypt_body(payload)
        resp = requests.post(
            url,
            data=encrypted_body,
            headers=_build_signed_headers(),
            timeout=30,
            proxies=_NO_PROXY,
        )
        return _decrypt_body(resp.text)
    except Exception as e:
        logger.error(f"获取 BuddyKey 失败: {e}")
        return {"success": False, "message": str(e)}


def report_usage(
    device_fingerprint: str,
    credits_used: float,
    model: str = "",
    request_tokens: int = 0,
    response_tokens: int = 0,
    upstream_id: str = "",
    record_id: str = "",
) -> dict:
    """使用量上报（POST 加密接口）

    Args:
        device_fingerprint: 设备码（机器码）
        credits_used: 消耗积分
        model: 模型名称
        request_tokens: 请求 token 数
        response_tokens: 响应 token 数
        upstream_id: 上游 ID
        record_id: 记录 ID

    Returns:
        {"success": true, "device_fingerprint": "...", "credits_used": ..., "balance_before": ..., "balance_after": ..., "report_id": int}
    """
    url = f"{SERVER_BASE}/api/usage/report"

    payload = {
        "device_fingerprint": device_fingerprint,
        "credits_used": credits_used,
        "model": model,
        "request_tokens": request_tokens,
        "response_tokens": response_tokens,
        "upstream_id": upstream_id,
    }
    if record_id:
        payload["record_id"] = record_id

    try:
        encrypted_body = _encrypt_body(payload)
        resp = requests.post(
            url,
            data=encrypted_body,
            headers=_build_signed_headers(),
            timeout=15,
            proxies=_NO_PROXY,
        )
        return _decrypt_body(resp.text)
    except Exception as e:
        logger.error(f"使用量上报失败: {e}")
        return {"success": False, "message": str(e)}
