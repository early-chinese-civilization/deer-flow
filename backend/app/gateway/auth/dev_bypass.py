"""Development-only authentication bypass helpers."""

from __future__ import annotations

import os

from ecc_auth.identity import AuthIdentity

_TRUE_VALUES = {"1", "true", "yes", "on"}
_DEV_MODES = {"dev", "development", "local", "test"}
_PROD_MODES = {"prod", "production"}


def _is_truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in _TRUE_VALUES


def _server_mode() -> str | None:
    mode = os.getenv("DEER_FLOW_SERVER_MODE") or os.getenv("NODE_ENV")
    if mode is None:
        return None
    return mode.strip().lower()


def is_dev_auth_bypass_enabled() -> bool:
    """Return whether the explicit dev auth bypass is enabled.

    The bypass requires both an explicit opt-in and a development server mode.
    This keeps accidentally-exported environment variables from enabling auth
    bypass in production starts.
    """
    if not _is_truthy(os.getenv("DEER_FLOW_DEV_AUTH_BYPASS")):
        return False

    mode = _server_mode()
    if mode in _DEV_MODES:
        return True
    if mode in _PROD_MODES:
        raise RuntimeError("DEER_FLOW_DEV_AUTH_BYPASS cannot be enabled in production mode")
    raise RuntimeError(
        "DEER_FLOW_DEV_AUTH_BYPASS requires DEER_FLOW_SERVER_MODE=dev or NODE_ENV=development"
    )


def get_dev_auth_identity() -> AuthIdentity:
    """Build the synthetic local identity used by the dev bypass."""
    username = os.getenv("DEER_FLOW_DEV_AUTH_USERNAME", "dev")
    display_name = os.getenv("DEER_FLOW_DEV_AUTH_DISPLAY_NAME", "DeerFlow Dev")
    return AuthIdentity(
        external_auth_id=os.getenv("DEER_FLOW_DEV_AUTH_EXTERNAL_ID", "dev-local-user"),
        username=username,
        display_name=display_name,
        email=os.getenv("DEER_FLOW_DEV_AUTH_EMAIL", "dev@localhost"),
        email_verified=True,
    )
