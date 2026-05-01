from __future__ import annotations

import argparse
import asyncio
from collections.abc import Sequence
from pathlib import Path

from nestor_mcp.capabilities.code_agent.capability import CodeAgentCapability
from nestor_mcp.capabilities.code_agent.models import (
    CodeAgentExplainRequest,
    CodeAgentExplainResult,
    CodeAgentFile,
    CodeAgentRequest,
    CodeAgentResult,
    CodeAgentResultType,
)
from nestor_mcp.models.ha_change import HaChangeProposal
from nestor_mcp.models.home_assistant import HaEntity, HaInventory, HaService
from nestor_mcp.services.ha_change_service import HaChangeService
from nestor_mcp.services.proposal_store import ProposalStore


class NoopGitService:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def ensure_repo_current(self) -> None:
        return None

    def validate_changes(self, changes):
        from nestor_mcp.services.git_service import GitService

        return GitService(repo_path=self.repo_path).validate_changes(changes)


class FakeHomeAssistantService:
    async def get_inventory(self) -> HaInventory:
        return HaInventory(
            entities=[
                HaEntity(
                    entity_id="light.salon_lumieres",
                    state="off",
                    attributes={"friendly_name": "Salon lumières"},
                ),
            ],
            services=[HaService(domain="light", services=["turn_off", "turn_on"])],
            config={},
        )


class FakeHaGitOpsAgent(CodeAgentCapability):
    def __init__(self, clarify_first: bool = False) -> None:
        self.clarify_first = clarify_first

    async def propose_changes(self, request: CodeAgentRequest) -> CodeAgentResult:
        if self.clarify_first and not request.user_answers:
            return CodeAgentResult(
                type=CodeAgentResultType.needs_clarification,
                summary="Il manque l'heure d'extinction.",
                questions=["À quelle heure faut-il éteindre les lumières du salon ?"],
            )

        return CodeAgentResult(
            type=CodeAgentResultType.proposed_changes,
            summary="Ajoute une automation fictive pour éteindre les lumières du salon.",
            files=[
                CodeAgentFile(
                    path="packages/areas/salon.yaml",
                    content=(
                        "automation:\n"
                        "  - id: salon_lumieres_extinction_fictive\n"
                        "    alias: Salon - Extinction fictive des lumières\n"
                        "    trigger:\n"
                        "      - platform: time\n"
                        "        at: '23:00:00'\n"
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Draft a fake HA GitOps change proposal.")
    parser.add_argument(
        "request",
        nargs="?",
        default="Éteins les lumières du salon à 23h",
        help="User change request to simulate",
    )
    parser.add_argument(
        "--repo-path",
        default="/tmp/nestor-mcp-dev-ha-config",
        help="Temporary fake Home Assistant config repository path",
    )
    parser.add_argument(
        "--proposal-path",
        default="/tmp/nestor-mcp-dev-proposals",
        help="Temporary proposal store path",
    )
    parser.add_argument(
        "--clarify-first",
        action="store_true",
        help="Simulate a clarification question before producing changes",
    )
    parser.add_argument(
        "--answer",
        default="À 23h",
        help="Answer used when --clarify-first is enabled",
    )
    parser.add_argument("--json", action="store_true", help="Print raw proposal JSON")
    return parser


def prepare_fake_repo(path: Path) -> None:
    target = path / "packages/areas/salon.yaml"
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text("automation: []\n", encoding="utf-8")


async def run_draft(
    user_request: str,
    repo_path: Path,
    proposal_path: Path,
    clarify_first: bool = False,
    answer: str = "À 23h",
) -> HaChangeProposal:
    prepare_fake_repo(repo_path)
    service = HaChangeService(
        git_service=NoopGitService(repo_path),  # type: ignore[arg-type]
        proposal_store=ProposalStore(proposal_path),
        home_assistant_service=FakeHomeAssistantService(),  # type: ignore[arg-type]
        code_agent=FakeHaGitOpsAgent(clarify_first=clarify_first),
    )
    proposal = await service.draft_change(user_request)
    if clarify_first and proposal.questions:
        proposal = await service.answer_clarification(proposal.id, answer)
    return proposal


def format_proposal(proposal: HaChangeProposal) -> str:
    parts = [
        f"proposal_id: {proposal.id}",
        f"status: {proposal.status}",
        f"branch_name: {proposal.branch_name}",
        "",
        proposal.summary,
    ]
    if proposal.questions:
        parts.extend(["", "questions:", *[f"- {question}" for question in proposal.questions]])
    if proposal.proposed_changes:
        parts.append("")
        parts.append("proposed_changes:")
        for change in proposal.proposed_changes:
            parts.append(f"- {change.path}")
            parts.append("  content:")
            parts.extend(f"    {line}" for line in change.content.splitlines())
    if proposal.validation_results:
        parts.extend(
            [
                "",
                "validation:",
                *[
                    f"- {'OK' if result.ok else 'FAIL'}: {result.message}"
                    for result in proposal.validation_results
                ],
            ]
        )
    return "\n".join(parts)


async def async_main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    proposal = await run_draft(
        user_request=args.request,
        repo_path=Path(args.repo_path),
        proposal_path=Path(args.proposal_path),
        clarify_first=args.clarify_first,
        answer=args.answer,
    )
    if args.json:
        print(proposal.model_dump_json(indent=2))
    else:
        print(format_proposal(proposal))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
