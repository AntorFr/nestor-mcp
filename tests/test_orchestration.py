from pathlib import Path

from nestor_mcp.orchestration.state import WorkflowRun, WorkflowStatus
from nestor_mcp.orchestration.store import WorkflowStore


def test_workflow_store_roundtrip(tmp_path: Path) -> None:
    store = WorkflowStore(tmp_path)
    run = WorkflowRun(
        id="run-1",
        workflow_name="ha_gitops",
        status=WorkflowStatus.needs_user_input,
        input={"request": "change HA"},
    )

    store.save(run)
    loaded = store.get("run-1")

    assert loaded == run
    assert store.list("ha_gitops") == [run]
