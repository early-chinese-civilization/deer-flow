"""安全工具

提供加密、PKCE、CSRF 等安全相关功能。
"""
import base64
import hashlib
import os
import secrets

from cryptography.fernet import Fernet


def get_encryption_key() -> bytes:
    """获取加密密钥

    从环境变量 SESSION_SECRET_KEY 派生 Fernet 密钥。

    Returns:
        Fernet 格式的加密密钥

    Raises:
        ValueError: 如果 SESSION_SECRET_KEY 环境变量未设置
    """
    key_str = os.getenv("SESSION_SECRET_KEY")
    if not key_str:
        raise ValueError("SESSION_SECRET_KEY environment variable is required")

    # 将密钥转换为 Fernet 格式（使用 SHA256 哈希）
    key_hash = hashlib.sha256(key_str.encode()).digest()
    return base64.urlsafe_b64encode(key_hash)


def encrypt_token(token: str) -> str:
    """加密 token（用于 refresh_token）

    Args:
        token: 明文 token

    Returns:
        加密后的 token（Base64 编码）
    """
    f = Fernet(get_encryption_key())
    return f.encrypt(token.encode()).decode()


def decrypt_token(encrypted_token: str) -> str:
    """解密 token

    Args:
        encrypted_token: 加密的 token

    Returns:
        明文 token

    Raises:
        cryptography.fernet.InvalidToken: 如果解密失败
    """
    f = Fernet(get_encryption_key())
    return f.decrypt(encrypted_token.encode()).decode()


def generate_pkce_pair() -> tuple[str, str]:
    """生成 PKCE code_verifier 和 code_challenge

    使用 S256 方法（SHA256）。

    Returns:
        (code_verifier, code_challenge) 元组
    """
    # 生成 code_verifier（43-128 字符）
    code_verifier = base64.urlsafe_b64encode(
        secrets.token_bytes(32)
    ).decode('utf-8').rstrip('=')

    # 生成 code_challenge（SHA256 哈希）
    code_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(code_verifier.encode()).digest()
    ).decode('utf-8').rstrip('=')

    return code_verifier, code_challenge


def generate_state_nonce() -> tuple[str, str]:
    """生成 state 和 nonce（用于 CSRF 保护）

    Returns:
        (state, nonce) 元组
    """
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    return state, nonce


def generate_session_id() -> str:
    """生成会话 ID

    Returns:
        随机会话 ID（URL 安全的 Base64 编码）
    """
    return secrets.token_urlsafe(48)
