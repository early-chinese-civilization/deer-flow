from types import SimpleNamespace

from langchain_core.messages import AIMessage

from deerflow.agents.middlewares.file_reference_middleware import FileReferenceMiddleware


def test_after_model_rewrites_virtual_paths_to_oss_uris():
    middleware = FileReferenceMiddleware()

    state = {
        "messages": [
            AIMessage(
                content="![trend](/mnt/user-data/outputs/monthly_visits_chart.png)",
            )
        ],
        "artifacts": {
            "/mnt/user-data/outputs/monthly_visits_chart.png": "oss://bucket/workspaces/ws-1/outputs/monthly_visits_chart.png",
        },
    }

    result = middleware.after_model(state, SimpleNamespace())

    assert result is not None
    rewritten = result["messages"][0]
    assert "oss://bucket/workspaces/ws-1/outputs/monthly_visits_chart.png" in str(rewritten.content)
    assert "/mnt/user-data/outputs/monthly_visits_chart.png" not in str(rewritten.content)
