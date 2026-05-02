import json
from datetime import UTC, datetime
from pathlib import Path

from nestor_mcp.config import get_settings
from nestor_mcp.models.ha_change import HaChangeProposal


class ProposalStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path or get_settings().proposals_path)

    def save(self, proposal: HaChangeProposal) -> None:
        self.path.mkdir(parents=True, exist_ok=True)
        proposal_path = self.path / f"{proposal.id}.json"
        proposal = proposal.model_copy(update={"updated_at": datetime.now(UTC)})
        proposal_path.write_text(proposal.model_dump_json(indent=2), encoding="utf-8")

    def get(self, proposal_id: str) -> HaChangeProposal:
        proposal_path = self.path / f"{proposal_id}.json"
        if not proposal_path.exists():
            raise FileNotFoundError(f"Proposal not found: {proposal_id}")
        return HaChangeProposal.model_validate_json(proposal_path.read_text(encoding="utf-8"))

    def list(self) -> list[HaChangeProposal]:
        if not self.path.exists():
            return []
        proposals = []
        for proposal_path in sorted(self.path.glob("*.json")):
            data = json.loads(proposal_path.read_text(encoding="utf-8"))
            proposals.append(HaChangeProposal.model_validate(data))
        return proposals
