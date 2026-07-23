"""证书固定（Certificate Pinning）— 防止中间人抓包

实现方式：自定义 requests HTTPAdapter，替换默认的连接池为使用
_PinnedHTTPSConnection 的连接池。该连接在 TLS 握手完成后
额外验证服务端证书的 SPKI（Subject Public Key Info）SHA-256 指纹。

效果：即使攻击者安装了自签名 CA 证书（Fiddler/Charles），也无法解密通信，
因为公钥指纹不匹配会导致连接被拒绝。
"""

import ssl
import hashlib
import logging

import urllib3
from urllib3.poolmanager import PoolManager
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)

from ._obfuscate import get as _obf_get

_PINNED_SPKI_HASH = _obf_get("SERVER_SPKI_HASH")

# 需要启用 pinning 的域名
_PINNED_HOSTS = {"buddy.shengdingit.com"}


def _verify_spki(cert_der: bytes) -> bool:
    """验证证书的 SPKI SHA-256 指纹是否匹配"""
    try:
        from cryptography import x509
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

        cert = x509.load_der_x509_certificate(cert_der)
        pub_key = cert.public_key()
        pub_der = pub_key.public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
        actual_hash = hashlib.sha256(pub_der).hexdigest()
        return actual_hash == _PINNED_SPKI_HASH
    except Exception as e:
        logger.error(f"[SSL Pinning] SPKI 验证异常: {e}")
        return False


class _PinnedHTTPSConnection(urllib3.connection.HTTPSConnection):
    """自定义 HTTPS 连接，握手后验证 SPKI 指纹"""

    def connect(self):
        super().connect()
        try:
            der_cert = self.sock.getpeercert(binary_form=True)
            if not der_cert:
                raise ssl.SSLError("[SSL Pinning] 无法获取服务端证书")
            if not _verify_spki(der_cert):
                raise ssl.SSLError(
                    "[SSL Pinning] 证书公钥指纹不匹配，疑似中间人攻击。"
                    "如使用了代理抓包工具（Fiddler/Charles），请关闭后重试。"
                )
            logger.debug("[SSL Pinning] 证书验证通过")
        except ssl.SSLError:
            raise
        except Exception as e:
            raise ssl.SSLError(f"[SSL Pinning] 证书验证失败: {e}")


class _PinnedPoolManager(PoolManager):
    """对所有 HTTPS 连接使用 _PinnedHTTPSConnection"""

    def _new_pool(self, scheme, host, port, request_context=None):
        if scheme == "https":
            pool = super()._new_pool(scheme, host, port, request_context)
            # 替换连接类
            pool.ConnectionCls = _PinnedHTTPSConnection
            return pool
        return super()._new_pool(scheme, host, port, request_context)


class PinnedHTTPAdapter(HTTPAdapter):
    """requests 适配器：对 pinned 域名启用证书固定"""

    def init_poolmanager(self, *args, **kwargs):
        self.poolmanager = _PinnedPoolManager(*args, **kwargs)


def install_pinning(session):
    """为 requests.Session 安装证书固定

    对 buddy.shengdingit.com 域名的 HTTPS 请求启用 SPKI 验证。
    """
    adapter = PinnedHTTPAdapter()
    session.mount("https://buddy.shengdingit.com", adapter)
    logger.debug("[SSL Pinning] 已为 buddy.shengdingit.com 启用证书固定")
