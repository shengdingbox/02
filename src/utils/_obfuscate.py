"""字符串混淆工具 — 编译期 XOR 加密，运行时按需解密

用途：防止敏感字符串（密钥、URL、签名密钥等）以明文形式存在于编译后的二进制中。
原理：构建时用 XOR 把明文转成字节序列，运行时通过 _reveal() 还原。
效果：strings 命令只能看到乱码，无法直接提取密钥/URL。
"""


def _derive_key(data_len: int, salt: int) -> int:
    """从数据长度和盐值派生单字节 key"""
    return ((data_len * 31 + salt * 7 + 0x5A) & 0xFF)


def _xor(data: bytes, key: int) -> bytes:
    """XOR 加密/解密（对称操作）"""
    return bytes(b ^ key for b in data)


def _reveal_str(obfuscated: bytes, salt: int) -> str:
    """运行时还原字符串"""
    key = _derive_key(len(obfuscated), salt)
    return _xor(obfuscated, key).decode("utf-8")


def _reveal_bytes(obfuscated: bytes, salt: int) -> bytes:
    """运行时还原字节串"""
    key = _derive_key(len(obfuscated), salt)
    return _xor(obfuscated, key)


# ─── 预计算的加密数据（构建时生成，每个 salt 不同）───

_OBF_DATA = {
    "SERVER_BASE": (
        b'\x92\x8e\x8e\x8a\x89\xc0\xd5\xd5\x98\x8f\x9e\x9e\x83\xd4\x89\x92'
        b'\x9f\x94\x9d\x9e\x93\x94\x9d\x93\x8e\xd4\x99\x95\x97\xd5\x9b\x8a'
        b'\x93',
        0x17,
    ),
    "AES_KEY_HEX": (
        b'\x8d\x86\x8b\x8e\x8c\x8d\x8b\x8e\x8a\x8e\x86\xd8\x86\xda\x8b\x8e'
        b'\x8f\x8f\x88\x8e\x88\xd8\xdd\x8f\x86\x88\xda\xdf\xdf\x88\x8c\x88'
        b'\x8f\x87\x88\xdc\xdb\xdf\xdd\x88\xdf\x8b\x8c\x87\xda\x89\xdc\x89'
        b'\x87\xdc\x8d\x8e\xdb\x89\x8f\x8d\xdf\x8e\xdd\x88\xd8\x8c\xd8\x8e',
        0x3C,
    ),
    "API_KEY": (
        b'\x8b\x9c\x8d\x8d\x90\xb6\xde\xd9\xde\x8d\xdb\xda\x8a\x8b\xd9\xd1'
        b'\xda\xdb\x8f\x8b\xd9\x8f\xd9\x8f\x8a\xdd\x88\xda\x8d\xde',
        0x6B,
    ),
    "HMAC_KEY": (
        b'\x43\x45\x16\x46\x1e\x17\x11\x43\x1f\x17\x42\x45\x10\x14\x46\x1f'
        b'\x15\x43\x14\x43\x42\x43\x13\x15\x41\x41\x45\x11\x13\x45\x42\x12',
        0x6B,
    ),
    "XXTEA_KEY": (
        b'\xa8\xbd\xc4\xb1\xbd\xac\xa8\xc4\xdb\xd9\xdb\xdf',
        0x4D,
    ),
    "SERVER_SPKI_HASH": (
        b'\x08\x0f\x5a\x0b\x01\x5b\x0f\x5a\x00\x01\x08\x5c\x0d\x0b\x0b\x00'
        b'\x00\x09\x01\x0a\x0c\x5d\x5b\x09\x0f\x09\x0b\x0d\x5f\x0f\x5c\x0a'
        b'\x0f\x00\x5f\x0f\x5f\x0b\x5a\x01\x09\x0a\x0f\x0d\x0b\x5a\x0d\x0c'
        b'\x0a\x0d\x01\x5c\x08\x5a\x5b\x0d\x5b\x5b\x0b\x0d\x5a\x0b\x5b\x58',
        0x29,
    ),
}


def get(name: str) -> str:
    """获取还原后的字符串"""
    data, salt = _OBF_DATA[name]
    return _reveal_str(data, salt)


def get_bytes(name: str) -> bytes:
    """获取还原后的字节串"""
    data, salt = _OBF_DATA[name]
    return _reveal_bytes(data, salt)
