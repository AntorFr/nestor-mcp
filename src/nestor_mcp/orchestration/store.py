import json
from pathlib import Path

from nestor_mcp.config import get_settings
from nestor_mcp.orchestration.state import WorkflowRun


class WorkflowStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or get_settings().workflow_runs_path)

    def save(self, run: WorkflowRun) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        run_path = self.path / f"{run.id}.json"
        run_path.write_text(run.model_dump_json(indent=2), encoding="utf-8")

    def get(self, run_id: str) -> WorkflowRun:
        run_path = self.path / f"{run_id}.json"
        if not run_path.exists():
            raise FileNotFoundError(f"Workflow run not found: {run_id}")
        return WorkflowRun.model_validate_json(run_path.read_text(encoding="utf-8"))

    def list(self, workflow_name: str | None = None) -> list[WorkflowRun]:
        if not self.path.exists():
            return []
        runs = []
        for run_path in sorted(self.path.glob("*.json")):
            data = json.loads(run_path.read_text(encoding="utf-8"))
            run = WorkflowRun.model_validate(data)
            if workflow_name is None or run.workflow_name == workflow_name:
                runs.append(run)
        return runs

