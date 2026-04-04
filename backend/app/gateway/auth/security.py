"""安全工具。

提供 PKCE、CSRF 等安全相关功能。
"""
import base64
import hashlib
import secrets


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
