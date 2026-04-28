from types import SimpleNamespace

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from deerflow.agents.middlewares.view_image_middleware import ViewImageMiddleware
from deerflow.tools.builtins.view_image_tool import _resolve_uploaded_image_entry


def test_resolve_uploaded_image_entry_prefers_oss_uri() -> None:
    runtime = SimpleNamespace(
        state={
            "uploaded_files": [
                {
                    "virtual_path": "/mnt/user-data/uploads/photo.png",
                    "http_uri": "/api/threads/ws-1/artifacts/mnt/user-data/uploads/photo.png",
                    "oss_uri": "oss://demo-bucket/workspaces/ws-1/uploads/photo.png",
                    "object_key": "workspaces/ws-1/uploads/photo.png",
                }
            ]
        }
    )

    result = _resolve_uploaded_image_entry(
        runtime,
        "/mnt/user-data/uploads/photo.png",
        "/tmp/threads/t1/user-data/uploads/photo.png",
    )

    assert result == {
        "virtual_path": "/mnt/user-data/uploads/photo.png",
        "http_uri": "/api/threads/ws-1/artifacts/mnt/user-data/uploads/photo.png",
        "oss_uri": "oss://demo-bucket/workspaces/ws-1/uploads/photo.png",
        "object_key": "workspaces/ws-1/uploads/photo.png",
    }


def test_view_image_middleware_prefers_oss_uri_in_injected_message() -> None:
    middleware = ViewImageMiddleware()

    state = {
        "messages": [
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "view_image",
                        "id": "tool-call-1",
                        "args": {"image_path": "/mnt/user-data/uploads/photo.png"},
                    }
                ],
            ),
            ToolMessage(content="Successfully read image", tool_call_id="tool-call-1"),
        ],
        "viewed_images": {
            "oss://demo-bucket/workspaces/ws-1/uploads/photo.png": {
                "base64": "ZmFrZS1kYXRh",
                "mime_type": "image/png",
                "virtual_path": "/mnt/user-data/uploads/photo.png",
                "http_uri": "/api/threads/ws-1/artifacts/mnt/user-data/uploads/photo.png",
                "oss_uri": "oss://demo-bucket/workspaces/ws-1/uploads/photo.png",
                "object_key": "workspaces/ws-1/uploads/photo.png",
            }
        }
    }

    result = middleware.before_model(state, SimpleNamespace())

    assert result is not None
    assert len(result["messages"]) == 1
    message = result["messages"][0]
    assert isinstance(message, HumanMessage)
    assert "/api/threads/ws-1/artifacts/mnt/user-data/uploads/photo.png" in str(message.content)
    assert "oss://demo-bucket/workspaces/ws-1/uploads/photo.png" in str(message.content)
    assert "virtual_path: /mnt/user-data/uploads/photo.png" in str(message.content)
