import re
from uuid import uuid4

from nestor_mcp.config import get_settings
from nestor_mcp.models.ha_change import (
    HaChangeConfirmationResult,
    HaChangeProposal,
    HaChangeProposalStatus,
    ProposedFileChange,
    ValidationResult,
)
from nestor_mcp.models.home_assistant import HaInventory
from nestor_mcp.services.git_service import GitService, slugify_branch
from nestor_mcp.services.github_service import GitHubService
from nestor_mcp.services.home_assistant import HomeAssistantService
from nestor_mcp.services.proposal_store import ProposalStore

AREA_FILE_HINTS = {
    "salon": "packages/areas/salon.yaml",
    "cuisine": "packages/areas/cuisine.yaml",
    "bureau": "packages/areas/bureau.yaml",
    "garage": "packages/areas/garage.yaml",
    "jardin": "packages/areas/jardin.yaml",
    "piscine": "packages/areas/piscine.yaml",
    "buanderie": "packages/areas/buanderie.yaml",
    "salle a manger": "packages/areas/salle_a_manger.yaml",
    "salle à manger": "packages/areas/salle_a_manger.yaml",
    "chambre parent": "packages/areas/chambre_parent.yaml",
    "chambre timothee": "packages/areas/chambre_timothee.yaml",
    "chambre timothée": "packages/areas/chambre_timothee.yaml",
    "chambre emilie": "packages/areas/chambre_emilie.yaml",
    "chambre émilie": "packages/areas/chambre_emilie.yaml",
}

FUNCTION_FILE_HINTS = {
    "lumiere": "packages/functions/lights.yaml",
    "lumière": "packages/functions/lights.yaml",
    "chauffage": "packages/functions/heating.yaml",
    "presence": "packages/functions/presence.yaml",
    "présence": "packages/functions/presence.yaml",
    "notification": "packages/functions/notification.yaml",
    "securite": "packages/functions/securtity_system.yaml",
    "sécurité": "packages/functions/securtity_system.yaml",
    "energie": "packages/functions/energy_monitor.yaml",
    "énergie": "packages/functions/energy_monitor.yaml",
    "tv": "packages/functions/tv.yaml",
}

ROUTINE_FILE_HINTS = {
    "routine": "packages/routines/day.yaml",
    "matin": "packages/routines/day.yaml",
    "soir": "packages/routines/day.yaml",
    "nuit": "packages/routines/day.yaml",
    "absence": "packages/routines/away.yaml",
    "enfant": "packages/routines/children.yaml",
    "travail": "packages/routines/work.yaml",
}


class HaChangeService:
    def __init__(
        self,
        git_service: GitService | None = None,
        github_service: GitHubService | None = None,
        proposal_store: ProposalStore | None = None,
        home_assistant_service: HomeAssistantService | None = None,
    ) -> None:
        self.settings = get_settings()
        self.git_service = git_service or GitService()
        self.github_service = github_service or GitHubService()
        self.proposal_store = proposal_store or ProposalStore()
        self.home_assistant_service = home_assistant_service or HomeAssistantService()

    async def draft_change(
        self,
        user_request: str,
        path: str | None = None,
        content: str | None = None,
        commit_message: str | None = None,
    ) -> HaChangeProposal:
        self.git_service.ensure_repo_current()
        inventory = await self.try_get_inventory()
        target_files = [path] if path else self.infer_target_files(user_request)
        proposal_id = str(uuid4())
        branch_name = slugify_branch(f"{user_request}-{proposal_id[:8]}")
        changes = [ProposedFileChange(path=path, content=content)] if path and content else []
        validation_results = self.validate_proposal(changes, inventory)

        questions = self.build_questions(user_request, target_files, changes, inventory)
        status = (
            HaChangeProposalStatus.awaiting_confirmation
            if changes and all(result.ok for result in validation_results) and not questions
            else HaChangeProposalStatus.needs_clarification
        )

        proposal = HaChangeProposal(
            id=proposal_id,
            user_request=user_request,
            status=status,
            questions=questions,
            target_files=target_files,
            branch_name=branch_name,
            commit_message=commit_message or f"Update Home Assistant config: {user_request[:72]}",
            summary=self.build_summary(user_request, target_files, changes),
            proposed_changes=changes,
            validation_results=validation_results,
        )
        self.proposal_store.save(proposal)
        return proposal

    def confirm_change(self, proposal_id: str) -> HaChangeConfirmationResult:
        proposal = self.proposal_store.get(proposal_id)
        if proposal.status != HaChangeProposalStatus.awaiting_confirmation:
            raise RuntimeError(f"Proposal is not ready for confirmation: {proposal.status}")
        if not proposal.branch_name:
            raise RuntimeError("Proposal has no branch name")

        validation_results = self.git_service.validate_changes(proposal.proposed_changes)
        if not all(result.ok for result in validation_results):
            raise RuntimeError("Proposal validation failed")

        commit_sha = self.git_service.create_branch_commit_and_push(
            proposal.branch_name,
            proposal.proposed_changes,
            proposal.commit_message,
        )
        pr_url = self.github_service.create_pull_request(
            branch_name=proposal.branch_name,
            title=proposal.commit_message,
            body=self.pull_request_body(proposal),
        )

        updated = proposal.model_copy(
            update={
                "status": HaChangeProposalStatus.pr_created,
                "validation_results": validation_results,
                "pr_url": pr_url,
            }
        )
        self.proposal_store.save(updated)

        return HaChangeConfirmationResult(
            proposal_id=proposal.id,
            branch_name=proposal.branch_name,
            commit_sha=commit_sha,
            pr_url=pr_url,
        )

    async def try_get_inventory(self) -> HaInventory | None:
        try:
            return await self.home_assistant_service.get_inventory()
        except RuntimeError:
            return None

    def infer_target_files(self, user_request: str) -> list[str]:
        normalized = user_request.lower()
        matches: list[str] = []
        for hints in (AREA_FILE_HINTS, ROUTINE_FILE_HINTS, FUNCTION_FILE_HINTS):
            for keyword, path in hints.items():
                if keyword in normalized and path not in matches:
                    matches.append(path)
        return matches[:3]

    def build_questions(
        self,
        user_request: str,
        target_files: list[str],
        changes: list[ProposedFileChange],
        inventory: HaInventory | None,
    ) -> list[str]:
        questions: list[str] = []
        if not target_files:
            questions.append(
                "Dans quel domaine faut-il classer ce changement : area, function, routine, "
                "integration, device ou system ?"
            )
        if not changes:
            questions.append(
                "Quel comportement exact veux-tu ajouter ou modifier, et peux-tu confirmer les "
                "entités concernées ?"
            )
        if inventory is None:
            questions.append(
                "Je n'ai pas accès à Home Assistant pour vérifier les entités. "
                "Configure HOME_ASSISTANT_URL et HOME_ASSISTANT_TOKEN pour une analyse complète."
            )
        elif not changes and not self.find_likely_entities(user_request, inventory):
            questions.append(
                "Je n'ai pas trouvé d'entité évidente dans Home Assistant pour cette demande. "
                "Quelle entity_id dois-je utiliser ?"
            )
        return questions

    def validate_proposal(
        self,
        changes: list[ProposedFileChange],
        inventory: HaInventory | None,
    ) -> list[ValidationResult]:
        results = self.git_service.validate_changes(changes)
        if inventory is not None:
            known_entities = {entity.entity_id for entity in inventory.entities}
            known_services = {
                f"{service.domain}.{service_name}"
                for service in inventory.services
                for service_name in service.services
            }
            for change in changes:
                references_content = (
                    added_lines_from_diff(change.diff) if change.diff else change.content
                )
                for reference in extract_entity_ids(references_content):
                    if reference in known_entities or reference in known_services:
                        continue
                    domain = reference.split(".", 1)[0]
                    if domain in {"trigger", "condition", "action"}:
                        continue
                    if reference not in known_entities:
                        results.append(
                            ValidationResult(
                                ok=False,
                                message=(
                                    f"{change.path}: unknown Home Assistant reference {reference}"
                                ),
                            )
                        )
        return results

    def build_summary(
        self,
        user_request: str,
        target_files: list[str],
        changes: list[ProposedFileChange],
    ) -> str:
        if changes:
            return f"Prepared {len(changes)} file change(s) for: {user_request}"
        if target_files:
            files = ", ".join(target_files)
            return f"Need clarification before editing likely target file(s): {files}"
        return "Need clarification before choosing a Home Assistant package file"

    def find_likely_entities(self, user_request: str, inventory: HaInventory) -> list[str]:
        normalized_request = user_request.lower()
        matches = []
        for entity in inventory.entities:
            friendly_name = str(entity.attributes.get("friendly_name", "")).lower()
            if entity.entity_id.lower() in normalized_request or (
                friendly_name and friendly_name in normalized_request
            ):
                matches.append(entity.entity_id)
        return matches

    def pull_request_body(self, proposal: HaChangeProposal) -> str:
        files = "\n".join(f"- `{change.path}`" for change in proposal.proposed_changes)
        validations = "\n".join(
            f"- {'OK' if result.ok else 'FAIL'}: {result.message}"
            for result in proposal.validation_results
        )
        return (
            "Created by Nestor MCP after explicit Assist confirmation.\n\n"
            f"Request:\n{proposal.user_request}\n\n"
            f"Files:\n{files}\n\n"
            f"Validation:\n{validations}\n"
        )


def extract_entity_ids(content: str) -> set[str]:
    pattern = r"\b[a-zA-Z_]+(?:\.[a-zA-Z0-9_]+)\b"
    excluded_domains = {"mdi", "http", "https"}
    return {
        match
        for match in re.findall(pattern, content)
        if match.split(".", 1)[0] not in excluded_domains
    }



def added_lines_from_diff(diff: str | None) -> str:
    if not diff:
        return ""
    lines = []
    for line in diff.splitlines():
        if line.startswith("+++") or not line.startswith("+"):
            continue
        lines.append(line[1:])
    return "\n".join(lines)
