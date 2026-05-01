from enum import StrEnum

from nestor_mcp.models.common import StrictBaseModel


class CodeAgentResultType(StrEnum):
    needs_clarification = "needs_clarification"
    proposed_changes = "proposed_changes"
    failed = "failed"


class CodeAgentFile(StrictBaseModel):
    path: str
    content: str


class CodeAgentRequest(StrictBaseModel):
    run_id: str
    user_request: str
    instructions: str
    context: dict
    files: list[CodeAgentFile] = []
    user_answers: list[str] = []


class CodeAgentResult(StrictBaseModel):
    type: CodeAgentResultType
    summary: str
    questions: list[str] = []
    files: list[CodeAgentFile] = []
    error: str | None = None


class CodeAgentExplainRequest(StrictBaseModel):
    run_id: str
    question: str
    instructions: str
    context: dict
    files: list[CodeAgentFile] = []
    history: list[dict[str, str]] = []


class CodeAgentExplainResult(StrictBaseModel):
    answer: str
    referenced_files: list[str] = []
    referenced_entities: list[str] = []
    follow_up_suggestions: list[str] = []
