import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.gateway.routers import suggestions


async def _db_dependency():
    yield SimpleNamespace()


def test_strip_markdown_code_fence_removes_wrapping():
    text = '```json\n["a"]\n```'
    assert suggestions._strip_markdown_code_fence(text) == '["a"]'


def test_strip_markdown_code_fence_no_fence_keeps_content():
    text = '  ["a"]  '
    assert suggestions._strip_markdown_code_fence(text) == '["a"]'


def test_parse_json_string_list_filters_invalid_items():
    text = '```json\n["a", " ", 1, "b"]\n```'
    assert suggestions._parse_json_string_list(text) == ["a", "b"]


def test_parse_json_string_list_rejects_non_list():
    text = '{"a": 1}'
    assert suggestions._parse_json_string_list(text) is None


def test_format_conversation_formats_roles():
    messages = [
        suggestions.SuggestionMessage(role="User", content="Hi"),
        suggestions.SuggestionMessage(role="assistant", content="Hello"),
        suggestions.SuggestionMessage(role="system", content="note"),
    ]
    assert suggestions._format_conversation(messages) == "User: Hi\nAssistant: Hello\nsystem: note"


def test_generate_suggestions_parses_and_limits(monkeypatch):
    req = suggestions.SuggestionsRequest(
        messages=[
            suggestions.SuggestionMessage(role="user", content="Hi"),
            suggestions.SuggestionMessage(role="assistant", content="Hello"),
        ],
        n=3,
        model_name=None,
    )
    fake_model = MagicMock()
    fake_model.invoke.return_value = MagicMock(content='```json\n["Q1", "Q2", "Q3", "Q4"]\n```')
    monkeypatch.setattr(suggestions, "create_chat_model", lambda **kwargs: fake_model)

    with patch("app.gateway.routers.suggestions.require_thread_access", AsyncMock(return_value=object())):
        result = asyncio.run(
            suggestions.generate_suggestions(
                "t1",
                req,
                http_request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace()))),
                current_user=SimpleNamespace(id=7),
                db=object(),
            )
        )

    assert result.suggestions == ["Q1", "Q2", "Q3"]


def test_generate_suggestions_parses_list_block_content(monkeypatch):
    req = suggestions.SuggestionsRequest(
        messages=[
            suggestions.SuggestionMessage(role="user", content="Hi"),
            suggestions.SuggestionMessage(role="assistant", content="Hello"),
        ],
        n=2,
        model_name=None,
    )
    fake_model = MagicMock()
    fake_model.invoke.return_value = MagicMock(content=[{"type": "text", "text": '```json\n["Q1", "Q2"]\n```'}])
    monkeypatch.setattr(suggestions, "create_chat_model", lambda **kwargs: fake_model)

    with patch("app.gateway.routers.suggestions.require_thread_access", AsyncMock(return_value=object())):
        result = asyncio.run(
            suggestions.generate_suggestions(
                "t1",
                req,
                http_request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace()))),
                current_user=SimpleNamespace(id=7),
                db=object(),
            )
        )

    assert result.suggestions == ["Q1", "Q2"]


def test_generate_suggestions_parses_output_text_block_content(monkeypatch):
    req = suggestions.SuggestionsRequest(
        messages=[
            suggestions.SuggestionMessage(role="user", content="Hi"),
            suggestions.SuggestionMessage(role="assistant", content="Hello"),
        ],
        n=2,
        model_name=None,
    )
    fake_model = MagicMock()
    fake_model.invoke.return_value = MagicMock(content=[{"type": "output_text", "text": '```json\n["Q1", "Q2"]\n```'}])
    monkeypatch.setattr(suggestions, "create_chat_model", lambda **kwargs: fake_model)

    with patch("app.gateway.routers.suggestions.require_thread_access", AsyncMock(return_value=object())):
        result = asyncio.run(
            suggestions.generate_suggestions(
                "t1",
                req,
                http_request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace()))),
                current_user=SimpleNamespace(id=7),
                db=object(),
            )
        )

    assert result.suggestions == ["Q1", "Q2"]


def test_generate_suggestions_returns_empty_on_model_error(monkeypatch):
    req = suggestions.SuggestionsRequest(
        messages=[suggestions.SuggestionMessage(role="user", content="Hi")],
        n=2,
        model_name=None,
    )
    fake_model = MagicMock()
    fake_model.invoke.side_effect = RuntimeError("boom")
    monkeypatch.setattr(suggestions, "create_chat_model", lambda **kwargs: fake_model)

    with patch("app.gateway.routers.suggestions.require_thread_access", AsyncMock(return_value=object())):
        result = asyncio.run(
            suggestions.generate_suggestions(
                "t1",
                req,
                http_request=SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(store=SimpleNamespace()))),
                current_user=SimpleNamespace(id=7),
                db=object(),
            )
        )

    assert result.suggestions == []


def test_generate_suggestions_requires_owned_thread() -> None:
    app = FastAPI()
    app.include_router(suggestions.router)
    app.state.store = SimpleNamespace()
    app.dependency_overrides[suggestions.get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[suggestions.get_db] = _db_dependency

    with (
        patch(
            "app.gateway.routers.suggestions.require_thread_access",
            AsyncMock(side_effect=HTTPException(status_code=403, detail="forbidden")),
        ),
        TestClient(app) as client,
    ):
        response = client.post(
            "/api/threads/t1/suggestions",
            json={"messages": [{"role": "user", "content": "Hi"}]},
        )

    assert response.status_code == 403
