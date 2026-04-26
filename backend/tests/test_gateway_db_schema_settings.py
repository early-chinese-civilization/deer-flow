from __future__ import annotations

from unittest.mock import patch

from app.gateway.db.schema_settings import format_search_path, get_gateway_db_connect_args


def test_format_search_path_quotes_hyphenated_schema() -> None:
    assert format_search_path("deer-flow") == '"deer-flow"'


def test_connect_args_pin_search_path_to_schema() -> None:
    with patch("app.gateway.db.schema_settings.get_gateway_db_schema", return_value="deer-flow"):
        assert get_gateway_db_connect_args() == {"server_settings": {"search_path": '"deer-flow"'}}
