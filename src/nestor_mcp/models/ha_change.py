from enum import StrEnum

from nestor_mcp.models.common import StrictBaseModel


class HomeAssistantChangeRequest(StrictBaseModel):
    path: str
    content: str
    message: str


class HomeAssistantChangeResult(StrictBaseModel):
    branch_name: str
    changed_path: str
    message: str
    dry_run: bool
    summary: str


class HaChangeProposalStatus(StrEnum):
    drafting = "drafting"
    needs_clarification = "needs_clarification"
    awaiting_confirmation = "awaiting_confirmation"
    pr_created = "pr_created"
    rejected = "rejected"


class ProposedFileChange(StrictBaseModel):
    path: str
    content: str
    diff: str | None = None


class ValidationResult(StrictBaseModel):
    ok: bool
    message: str


class HaChangeProposal(StrictBaseModel):
    id: str
    user_request: str
    status: HaChangeProposalStatus
    questions: list[str] = []
    target_files: list[str] = []
    branch_name: str | None = None
    commit_message: str
    summary: str
    user_answers: list[str] = []
    proposed_changes: list[ProposedFileChange] = []
    validation_results: list[ValidationResult] = []
    pr_url: str | None = None


class HaChangeConfirmationResult(StrictBaseModel):
    proposal_id: str
    branch_name: str
    commit_sha: str
    pr_url: str
