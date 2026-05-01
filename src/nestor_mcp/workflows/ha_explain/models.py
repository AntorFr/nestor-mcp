from nestor_mcp.models.common import StrictBaseModel
from nestor_mcp.orchestration.state import WorkflowStatus


class HaExplainRequest(StrictBaseModel):
    question: str
    run_id: str | None = None


class HaExplainResponse(StrictBaseModel):
    run_id: str
    status: WorkflowStatus
    answer: str
    referenced_files: list[str] = []
    referenced_entities: list[str] = []
    follow_up_suggestions: list[str] = []

