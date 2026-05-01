from pathlib import Path

import pytest

from nestor_mcp.devtools.draft_ha_change import format_proposal, run_draft
from nestor_mcp.models.ha_change import HaChangeProposalStatus


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_run_draft_returns_fake_valid_proposal(tmp_path: Path) -> None:
    proposal = await run_draft(
        user_request="Éteins les lumières du salon à 23h",
        repo_path=tmp_path / "repo",
        proposal_path=tmp_path / "proposals",
    )

    assert proposal.status == HaChangeProposalStatus.awaiting_confirmation
    assert proposal.proposed_changes[0].path == "packages/areas/salon.yaml"


@pytest.mark.anyio
async def test_run_draft_can_simulate_clarification(tmp_path: Path) -> None:
    proposal = await run_draft(
        user_request="Éteins les lumières du salon",
        repo_path=tmp_path / "repo",
        proposal_path=tmp_path / "proposals",
        clarify_first=True,
        answer="À 23h",
    )

    assert proposal.status == HaChangeProposalStatus.awaiting_confirmation
    assert proposal.user_answers == ["À 23h"]


@pytest.mark.anyio
async def test_format_proposal_shows_change_content(tmp_path: Path) -> None:
    proposal = await run_draft(
        user_request="Éteins les lumières du salon à 23h",
        repo_path=tmp_path / "repo",
        proposal_path=tmp_path / "proposals",
    )

    text = format_proposal(proposal)

    assert "proposal_id:" in text
    assert "packages/areas/salon.yaml" in text
