from nestor_mcp.capabilities.code_agent.models import CodeAgentFile
from nestor_mcp.models.common import StrictBaseModel


class LlmExplainRequest(StrictBaseModel):
    run_id: str
    question: str
    instructions: str
    context: dict
    files: list[CodeAgentFile] = []
    history: list[dict[str, str]] = []


class LlmExplainResult(StrictBaseModel):
    answer: str
    referenced_files: list[str] = []
    referenced_entities: list[str] = []
    follow_up_suggestions: list[str] = []
