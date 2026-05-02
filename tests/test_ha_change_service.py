from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from nestor_mcp.capabilities.code_agent.capability import CodeAgentCapability
from nestor_mcp.capabilities.code_agent.models import (
    CodeAgentExplainRequest,
    CodeAgentExplainResult,
    CodeAgentFile,
    CodeAgentRequest,
    CodeAgentResult,
    CodeAgentResultType,
)
from nestor_mcp.models.ha_change import HaChangeProposalStatus, ProposedFileChange
from nestor_mcp.models.home_assistant import HaEntity, HaInventory, HaService
from nestor_mcp.services.ha_change_service import (
    HaChangeService,
    added_lines_from_diff,
    extract_entity_ids,
)
from nestor_mcp.services.proposal_store import ProposalStore


class FakeGitService:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def ensure_repo_current(self) -> None:
        return None

    def validate_changes(self, changes: list[ProposedFileChange]):
        from nestor_mcp.services.git_service import GitService

        return GitService(repo_path=Path("/tmp")).validate_changes(changes)


class FakeHomeAssistantService:
    async def get_inventory(self) -> HaInventory:
        return HaInventory(
            entities=[
                HaEntity(
                    entity_id="light.salon_lumieres",
                    state="off",
                    attributes={"friendly_name": "Salon lumieres"},
                )
            ],
            services=[HaService(domain="light", services=["turn_off"])],
            config={},
        )


class ClarificationAgent(CodeAgentCapability):
    async def propose_changes(self, request: CodeAgentRequest) -> CodeAgentResult:
        return CodeAgentResult(
            type=CodeAgentResultType.needs_clarification,
            summary="Need details.",
            questions=["Quel changement exact dois-je produire ?"],
        )

    async def explain_config(self, request: CodeAgentExplainRequest) -> CodeAgentExplainResult:
        raise NotImplementedError


class ProposedChangeAgent(CodeAgentCapability):
    async def propose_changes(self, request: CodeAgentRequest) -> CodeAgentResult:
        assert request.files[0].path == "packages/areas/salon.yaml"
        return CodeAgentResult(
            type=CodeAgentResultType.proposed_changes,
            summary="Ajoute une automation salon.",
            files=[
                CodeAgentFile(
                    path="packages/areas/salon.yaml",
                    content=(
                        "automation:\n"
                        "  - id: salon_test\n"
                        "    alias: Salon test\n"
                        "    action:\n"
                        "      - service: light.turn_off\n"
                        "        target:\n"
                        "          entity_id: light.salon_lumieres\n"
                    ),
                )
            ],
        )

    async def explain_config(self, request: CodeAgentExplainRequest) -> CodeAgentExplainResult:
        raise NotImplementedError


class CapturingAgent(ProposedChangeAgent):
    def __init__(self) -> None:
        self.requests: list[CodeAgentRequest] = []

    async def propose_changes(self, request: CodeAgentRequest) -> CodeAgentResult:
        self.requests.append(request)
        return await super().propose_changes(request)


class AnswerAwareAgent(CodeAgentCapability):
    async def propose_changes(self, request: CodeAgentRequest) -> CodeAgentResult:
        if not request.user_answers:
            return CodeAgentResult(
                type=CodeAgentResultType.needs_clarification,
                summary="Need answer.",
                questions=["A quelle heure faut-il éteindre ?"],
            )
        return CodeAgentResult(
            type=CodeAgentResultType.proposed_changes,
            summary="Ajoute l'extinction demandée.",
            files=[
                CodeAgentFile(
                    path="packages/areas/salon.yaml",
                    content=(
                        "automation:\n"
                        "  - id: salon_extinction\n"
                        "    alias: Salon extinction\n"
                        "    action:\n"
                        "      - service: light.turn_off\n"
                        "        target:\n"
                        "          entity_id: light.salon_lumieres\n"
                    ),
                )
            ],
        )

    async def explain_config(self, request: CodeAgentExplainRequest) -> CodeAgentExplainResult:
        raise NotImplementedError


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_draft_infers_area_file_and_waits_for_exact_change(tmp_path: Path) -> None:
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=ProposalStore(tmp_path),
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ClarificationAgent(),
    )

    proposal = await service.draft_change("Eteindre les lumieres du salon a minuit")

    assert proposal.status == HaChangeProposalStatus.needs_clarification
    assert proposal.target_files[0] == "packages/areas/salon.yaml"
    assert proposal.questions
    assert proposal.proposed_changes == []


@pytest.mark.anyio
async def test_draft_with_content_can_wait_for_confirmation(tmp_path: Path) -> None:
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=ProposalStore(tmp_path),
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ClarificationAgent(),
    )

    proposal = await service.draft_change(
        user_request="Mettre a jour salon",
        path="packages/areas/salon.yaml",
        content="automation:\n  - id: salon_test\n    action: []\n",
    )

    assert proposal.status == HaChangeProposalStatus.awaiting_confirmation


@pytest.mark.anyio
async def test_draft_can_ignore_content_supplied_by_conversation_llm(tmp_path: Path) -> None:
    target = tmp_path / "packages/areas/salon.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("automation: []\n", encoding="utf-8")
    agent = CapturingAgent()
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=ProposalStore(tmp_path),
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=agent,
    )

    proposal = await service.draft_change(
        user_request="Mettre a jour salon",
        path="packages/areas/salon.yaml",
        content="automation:\n  - id: invented_by_conversation_llm\n",
        accept_supplied_content=False,
    )

    assert proposal.status == HaChangeProposalStatus.awaiting_confirmation
    assert "invented_by_conversation_llm" not in proposal.proposed_changes[0].content
    assert agent.requests


@pytest.mark.anyio
async def test_draft_uses_code_agent_to_prepare_change(tmp_path: Path) -> None:
    target = tmp_path / "packages/areas/salon.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("automation: []\n", encoding="utf-8")
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=ProposalStore(tmp_path),
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ProposedChangeAgent(),
    )

    proposal = await service.draft_change("Ajoute une automation salon")

    assert proposal.status == HaChangeProposalStatus.awaiting_confirmation
    assert proposal.summary == "Ajoute une automation salon."
    assert proposal.proposed_changes[0].path == "packages/areas/salon.yaml"


@pytest.mark.anyio
async def test_start_and_complete_draft_change(tmp_path: Path) -> None:
    target = tmp_path / "packages/areas/salon.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("automation: []\n", encoding="utf-8")
    store = ProposalStore(tmp_path)
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=store,
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ProposedChangeAgent(),
    )

    proposal = service.start_draft_change("Ajoute une automation salon")
    completed = await service.complete_draft_change(proposal.id)

    assert proposal.status == HaChangeProposalStatus.drafting
    assert completed.id == proposal.id
    assert completed.status == HaChangeProposalStatus.awaiting_confirmation
    assert completed.proposed_changes[0].path == "packages/areas/salon.yaml"
    assert store.get(proposal.id).status == HaChangeProposalStatus.awaiting_confirmation


@pytest.mark.anyio
async def test_start_draft_reuses_similar_active_proposal(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=store,
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ProposedChangeAgent(),
    )

    first = service.start_draft_change("Ajoute une automatisation dans le salon")
    second = service.start_draft_change("Ajoute une automation salon")

    assert second.id == first.id
    assert len(store.list()) == 1


@pytest.mark.anyio
async def test_start_draft_reuses_confirmed_proposal(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=store,
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ProposedChangeAgent(),
    )
    first = service.start_draft_change("Ajoute une automatisation dans le salon")
    store.save(first.model_copy(update={"status": HaChangeProposalStatus.pr_created}))

    second = service.start_draft_change("Ajoute une automation salon")

    assert second.id == first.id
    assert second.status == HaChangeProposalStatus.pr_created


def test_expired_draft_is_marked_for_clarification(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=store,
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ProposedChangeAgent(),
    )
    proposal = service.start_draft_change("Ajoute une automation salon")
    stale_time = datetime.now(UTC) - timedelta(
        seconds=service.settings.ha_gitops_draft_expire_seconds + 1
    )
    expired = proposal.model_copy(update={"updated_at": stale_time})
    (tmp_path / f"{proposal.id}.json").write_text(
        expired.model_dump_json(indent=2),
        encoding="utf-8",
    )

    status = service.get_change_status(proposal.id)

    assert status.status == HaChangeProposalStatus.needs_clarification
    assert status.questions


def test_current_status_returns_latest_reusable_proposal(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=store,
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ProposedChangeAgent(),
    )
    first = service.start_draft_change("Ajoute une automation salon")

    status = service.get_change_status("current")

    assert status.id == first.id


def test_open_status_alias_returns_latest_reusable_proposal(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=store,
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ProposedChangeAgent(),
    )
    first = service.start_draft_change("Ajoute une automation salon")

    status = service.get_change_status("open")

    assert status.id == first.id


def test_cancel_change_marks_pending_proposal_rejected(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=store,
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ProposedChangeAgent(),
    )
    proposal = service.start_draft_change("Ajoute une automation salon")

    cancelled = service.cancel_change(proposal.id)

    assert cancelled.status == HaChangeProposalStatus.rejected
    assert store.get(proposal.id).status == HaChangeProposalStatus.rejected
    assert service.list_reusable_proposals() == []


def test_cancel_change_refuses_pr_created_proposal(tmp_path: Path) -> None:
    store = ProposalStore(tmp_path)
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=store,
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ProposedChangeAgent(),
    )
    proposal = service.start_draft_change("Ajoute une automation salon")
    store.save(proposal.model_copy(update={"status": HaChangeProposalStatus.pr_created}))

    with pytest.raises(RuntimeError, match="déjà une PR"):
        service.cancel_change(proposal.id)


@pytest.mark.anyio
async def test_draft_infers_school_routine_files(tmp_path: Path) -> None:
    children = tmp_path / "packages/routines/children.yaml"
    holidays = tmp_path / "packages/functions/vacances_scolaires.yaml"
    children.parent.mkdir(parents=True)
    holidays.parent.mkdir(parents=True)
    children.write_text("automation: []\n", encoding="utf-8")
    holidays.write_text("template: []\n", encoding="utf-8")
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=ProposalStore(tmp_path),
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=ClarificationAgent(),
    )

    proposal = await service.draft_change(
        "Ajouter une condition aux rappels d'école pendant les vacances scolaires"
    )

    assert "packages/routines/children.yaml" in proposal.target_files
    assert "packages/functions/vacances_scolaires.yaml" in proposal.target_files


@pytest.mark.anyio
async def test_answer_clarification_updates_existing_proposal(tmp_path: Path) -> None:
    target = tmp_path / "packages/areas/salon.yaml"
    target.parent.mkdir(parents=True)
    target.write_text("automation: []\n", encoding="utf-8")
    store = ProposalStore(tmp_path)
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=store,
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=AnswerAwareAgent(),
    )
    proposal = await service.draft_change("Eteindre les lumieres du salon")

    updated = await service.answer_clarification(proposal.id, "A 23h")

    assert updated.id == proposal.id
    assert updated.status == HaChangeProposalStatus.awaiting_confirmation
    assert updated.user_answers == ["A 23h"]
    assert updated.proposed_changes[0].path == "packages/areas/salon.yaml"


def test_extract_entity_ids_ignores_icons() -> None:
    assert extract_entity_ids("entity_id: light.salon\nicon: mdi:lightbulb") == {"light.salon"}


def test_added_lines_from_diff_ignores_headers() -> None:
    diff = "--- a/file.yaml\n+++ b/file.yaml\n@@ -1 +1 @@\n-old\n+entity_id: light.salon\n"

    assert added_lines_from_diff(diff) == "entity_id: light.salon"
