"""Development-only synthetic authentication helpers.

This mode skips the external Keycloak redirect but does not skip DeerFlow's
user model. It injects a stable synthetic ``AuthIdentity`` that still flows
through the normal AuthIdentity -> local ``users`` projection used by business
features such as skills, uploads, threads, agents, and memory.
"""

from __future__ import annotations

import os

from ecc_auth.identity import AuthIdentity

_TRUE_VALUES = {"1", "true", "yes", "on"}
_DEV_MODES = {"dev", "development", "local", "test"}
_PROD_MODES = {"prod", "production"}
_SYNTHETIC_AUTH_ENV = "DEER_FLOW_DEV_SYNTHETIC_AUTH"


def _is_truthy(value: str | None) -> bool:
    return value is not None and value.strip().lower() in _TRUE_VALUES


def _server_mode() -> str | None:
    mode = os.getenv("DEER_FLOW_SERVER_MODE") or os.getenv("NODE_ENV")
    if mode is None:
        return None
    return mode.strip().lower()


def is_dev_synthetic_auth_enabled() -> bool:
    """Return whether development synthetic auth is enabled.

    Synthetic auth requires both an explicit opt-in and a development server
    mode. It is not anonymous auth: downstream dependencies still receive a
    concrete local ``User`` produced from the synthetic identity.
    """
    if not _is_truthy(os.getenv(_SYNTHETIC_AUTH_ENV)):
        return False

    mode = _server_mode()
    if mode in _DEV_MODES:
        return True
    if mode in _PROD_MODES:
        raise RuntimeError(f"{_SYNTHETIC_AUTH_ENV} cannot be enabled in production mode")
    raise RuntimeError(f"{_SYNTHETIC_AUTH_ENV} requires DEER_FLOW_SERVER_MODE=dev or NODE_ENV=development")


def get_dev_synthetic_auth_identity() -> AuthIdentity:
    """Build the stable synthetic identity used by development auth."""
    username = os.getenv("DEER_FLOW_DEV_AUTH_USERNAME", "dev")
    display_name = os.getenv("DEER_FLOW_DEV_AUTH_DISPLAY_NAME", "DeerFlow Dev")
    return AuthIdentity(
        external_auth_id=os.getenv("DEER_FLOW_DEV_AUTH_EXTERNAL_ID", "dev-local-user"),
        username=username,
        display_name=display_name,
        email=os.getenv("DEER_FLOW_DEV_AUTH_EMAIL", "dev@localhost"),
        email_verified=True,
    )
