from enum import StrEnum
from typing import Any

from nestor_mcp.models.common import StrictBaseModel


class WorkflowStatus(StrEnum):
    running = "running"
    needs_user_input = "needs_user_input"
    awaiting_confirmation = "awaiting_confirmation"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


class WorkflowQuestion(StrictBaseModel):
    id: str
    question: str
    reason: str | None = None


class WorkflowRun(StrictBaseModel):
    id: str
    workflow_name: str
    status: WorkflowStatus
    input: dict[str, Any]
    context: dict[str, Any] = {}
    questions: list[WorkflowQuestion] = []
    proposed_actions: list[dict[str, Any]] = []
    validation_results: list[dict[str, Any]] = []
    result: dict[str, Any] | None = None
    error: str | None = None

