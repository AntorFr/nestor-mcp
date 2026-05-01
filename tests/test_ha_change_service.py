from pathlib import Path

import pytest

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


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_draft_infers_area_file_and_waits_for_exact_change(tmp_path: Path) -> None:
    service = HaChangeService(
        git_service=FakeGitService(tmp_path),  # type: ignore[arg-type]
        proposal_store=ProposalStore(tmp_path),
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
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
    )

    proposal = await service.draft_change(
        user_request="Mettre a jour salon",
        path="packages/areas/salon.yaml",
        content="automation:\n  - id: salon_test\n    action: []\n",
    )

    assert proposal.status == HaChangeProposalStatus.awaiting_confirmation


def test_extract_entity_ids_ignores_icons() -> None:
    assert extract_entity_ids("entity_id: light.salon\nicon: mdi:lightbulb") == {"light.salon"}


def test_added_lines_from_diff_ignores_headers() -> None:
    diff = "--- a/file.yaml\n+++ b/file.yaml\n@@ -1 +1 @@\n-old\n+entity_id: light.salon\n"

    assert added_lines_from_diff(diff) == "entity_id: light.salon"
