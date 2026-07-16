"""使用量上报管理器 — 本地缓存 + 加密存储 + 后台上报

对话结束时生成缓存文件记录未上报数据（加密存储，.dll 后缀），后台提交后删除对应缓存。
应用启动时扫描缓存目录，补交未上报的记录。
"""

import os
import json
import time
import uuid
import base64
import logging
import threading
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

logger = logging.getLogger(__name__)

# 缓存目录: ~/.buddy-tool/usage_pending/
_CACHE_DIR = Path.home() / ".buddy-tool" / "usage_pending"

# 加密密钥（AES-256-GCM，与服务端一致）
_AES_KEY = bytes.fromhex("38502350408f8d5011606fc186daa626196beac6a529d7b79b30e713a0c6f2f0")


def _encrypt(data: dict) -> bytes:
    """AES-256-GCM 加密 dict → 二进制"""
    plaintext = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    nonce = os.urandom(12)
    aesgcm = AESGCM(_AES_KEY)
    ct_and_tag = aesgcm.encrypt(nonce, plaintext, associated_data=None)
    # 格式: nonce(12) + tag(16) + ciphertext
    ciphertext = ct_and_tag[:-16]
    tag = ct_and_tag[-16:]
    return nonce + tag + ciphertext


def _decrypt(raw: bytes) -> dict:
    """AES-256-GCM 解密二进制 → dict"""
    nonce = raw[:12]
    tag = raw[12:28]
    ciphertext = raw[28:]
    ct_and_tag = ciphertext + tag
    aesgcm = AESGCM(_AES_KEY)
    plaintext = aesgcm.decrypt(nonce, ct_and_tag, associated_data=None)
    return json.loads(plaintext.decode("utf-8"))


def _ensure_cache_dir():
    """确保缓存目录存在"""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _generate_record_id() -> str:
    """生成唯一记录 ID（用于缓存文件名）"""
    return f"{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"


def add_pending_report(
    credits_used: float,
    model: str = "",
    request_tokens: int = 0,
    response_tokens: int = 0,
    upstream_id: str = "",
) -> str:
    """将一条使用记录写入本地缓存文件（加密存储，.dll 后缀）

    Args:
        credits_used: 消耗积分
        model: 模型名称
        request_tokens: 请求 token 数
        response_tokens: 响应 token 数
        upstream_id: 上游 key ID

    Returns:
        缓存文件路径（上报成功后用于删除）
    """
    from .machine import get_machine_code

    _ensure_cache_dir()

    record = {
        "record_id": _generate_record_id(),
        "device_fingerprint": get_machine_code(),
        "credits_used": credits_used,
        "model": model,
        "request_tokens": request_tokens,
        "response_tokens": response_tokens,
        "upstream_id": upstream_id,
        "created_at": time.time(),
    }

    file_path = _CACHE_DIR / f"{record['record_id']}.dll"
    try:
        file_path.write_bytes(_encrypt(record))
        logger.debug(f"[上报] 缓存记录: {file_path.name}")
    except Exception as e:
        logger.error(f"[上报] 写入缓存失败: {e}")
        return ""

    # 后台异步上报
    _report_in_background(file_path)
    return str(file_path)


def _report_one(file_path: Path) -> bool:
    """上报单条记录

    Returns:
        True=上报成功（文件已删除），False=失败（文件保留）
    """
    try:
        record = _decrypt(file_path.read_bytes())
    except Exception as e:
        logger.error(f"[上报] 读取缓存失败，删除损坏文件: {file_path.name} - {e}")
        try:
            file_path.unlink()
        except Exception:
            pass
        return True

    from .server_api import report_usage

    result = report_usage(
        device_fingerprint=record.get("device_fingerprint", ""),
        credits_used=record.get("credits_used", 0),
        model=record.get("model", ""),
        request_tokens=record.get("request_tokens", 0),
        response_tokens=record.get("response_tokens", 0),
        upstream_id=record.get("upstream_id", ""),
        record_id=record.get("record_id", ""),
    )

    if result and (result.get("success") or "report_id" in result):
        try:
            file_path.unlink()
            logger.info(f"[上报] 成功，已删除缓存: {file_path.name}")
        except Exception:
            pass
        return True
    else:
        err = (result or {}).get("error", "未知错误")
        logger.warning(f"[上报] 失败，保留缓存: {file_path.name} - {err}")
        return False


def _report_in_background(file_path: Path):
    """后台线程上报单条记录"""
    def _worker():
        try:
            _report_one(file_path)
        except Exception as e:
            logger.error(f"[上报] 后台上报异常: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()


def flush_pending_reports():
    """扫描缓存目录，补交所有未上报的记录

    应用启动时调用。逐条上报，失败的保留。
    """
    _ensure_cache_dir()

    pending_files = sorted(_CACHE_DIR.glob("*.dll"))
    if not pending_files:
        return

    logger.info(f"[上报] 发现 {len(pending_files)} 条未上报记录，开始补交")

    success_count = 0
    fail_count = 0

    for file_path in pending_files:
        if _report_one(file_path):
            success_count += 1
        else:
            fail_count += 1
        # 每条之间间隔 200ms，避免请求过快
        time.sleep(0.2)

    logger.info(f"[上报] 补交完成: 成功 {success_count} 条, 失败 {fail_count} 条")


def flush_pending_reports_async():
    """异步扫描缓存目录补交未上报记录（非阻塞）"""
    def _worker():
        try:
            flush_pending_reports()
        except Exception as e:
            logger.error(f"[上报] 补交异常: {e}")

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
