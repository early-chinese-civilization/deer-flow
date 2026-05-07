from deerflow.agents.thread_state import merge_artifacts


def test_merge_artifacts_normalizes_legacy_list_state():
    existing = ["/mnt/user-data/outputs/legacy.txt"]
    new = {"/mnt/user-data/outputs/chart.png": "oss://bucket/workspaces/ws-1/outputs/chart.png"}

    merged = merge_artifacts(existing, new)

    assert merged["/mnt/user-data/outputs/legacy.txt"] == "/mnt/user-data/outputs/legacy.txt"
    assert merged["/mnt/user-data/outputs/chart.png"] == "oss://bucket/workspaces/ws-1/outputs/chart.png"
