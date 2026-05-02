import re
from pathlib import Path
from uuid import uuid4

from nestor_mcp.capabilities.code_agent.capability import CodeAgentCapability
from nestor_mcp.capabilities.code_agent.models import (
    CodeAgentFile,
    CodeAgentRequest,
    CodeAgentResult,
    CodeAgentResultType,
)
from nestor_mcp.capabilities.code_agent.providers import get_code_agent_capability
from nestor_mcp.capabilities.workspace.repo_context import RepoContextCapability
from nestor_mcp.config import get_settings
from nestor_mcp.models.ha_change import (
    HaChangeConfirmationResult,
    HaChangeProposal,
    HaChangeProposalStatus,
    ProposedFileChange,
    ValidationResult,
)
from nestor_mcp.models.home_assistant import HaInventory
from nestor_mcp.security.validators import ensure_editable_ha_path
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
    "vacances": "packages/functions/vacances_scolaires.yaml",
    "scolaire": "packages/functions/vacances_scolaires.yaml",
    "scolaires": "packages/functions/vacances_scolaires.yaml",
    "jour ferie": "packages/functions/vacances_scolaires.yaml",
    "jour férié": "packages/functions/vacances_scolaires.yaml",
    "jours feries": "packages/functions/vacances_scolaires.yaml",
    "jours fériés": "packages/functions/vacances_scolaires.yaml",
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
    "enfants": "packages/routines/children.yaml",
    "ecole": "packages/routines/children.yaml",
    "école": "packages/routines/children.yaml",
    "rappel": "packages/routines/children.yaml",
    "travail": "packages/routines/work.yaml",
}


class HaChangeService:
    def __init__(
        self,
        git_service: GitService | None = None,
        github_service: GitHubService | None = None,
        proposal_store: ProposalStore | None = None,
        home_assistant_service: HomeAssistantService | None = None,
        code_agent: CodeAgentCapability | None = None,
    ) -> None:
        self.settings = get_settings()
        self.git_service = git_service or GitService()
        self.github_service = github_service or GitHubService()
        self.proposal_store = proposal_store or ProposalStore()
        self.home_assistant_service = home_assistant_service or HomeAssistantService()
        self.code_agent = code_agent or get_code_agent_capability()

    async def draft_change(
        self,
        user_request: str,
        path: str | None = None,
        content: str | None = None,
        commit_message: str | None = None,
        accept_supplied_content: bool = True,
        proposal_id: str | None = None,
        branch_name: str | None = None,
    ) -> HaChangeProposal:
        self.git_service.ensure_repo_current()
        inventory = await self.try_get_inventory()
        target_files = self.resolve_target_files(user_request, path)
        proposal_id = proposal_id or str(uuid4())
        branch_name = branch_name or slugify_branch(f"{user_request}-{proposal_id[:8]}")
        agent_result: CodeAgentResult | None = None
        if path and content and accept_supplied_content:
            changes = [ProposedFileChange(path=path, content=content)]
        elif target_files:
            agent_result = await self.ask_code_agent_for_changes(
                proposal_id=proposal_id,
                user_request=user_request,
                target_files=target_files,
                inventory=inventory,
            )
            changes = self.changes_from_agent_result(agent_result)
        else:
            changes = []
        validation_results = self.validate_proposal(changes, inventory)

        questions = self.build_questions(user_request, target_files, changes, inventory)
        if agent_result and agent_result.type == CodeAgentResultType.needs_clarification:
            questions.extend(agent_result.questions)
        elif agent_result and agent_result.type == CodeAgentResultType.failed:
            questions.append(
                "L'agent de modification n'a pas réussi à produire une proposition. "
                f"Détail : {agent_result.error or agent_result.summary}"
            )
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
            summary=agent_result.summary
            if agent_result and agent_result.summary
            else self.build_summary(user_request, target_files, changes),
            user_answers=[],
            proposed_changes=changes,
            validation_results=validation_results,
        )
        self.proposal_store.save(proposal)
        return proposal

    def start_draft_change(
        self,
        user_request: str,
        commit_message: str | None = None,
    ) -> HaChangeProposal:
        proposal_id = str(uuid4())
        proposal = HaChangeProposal(
            id=proposal_id,
            user_request=user_request,
            status=HaChangeProposalStatus.drafting,
            questions=[],
            target_files=self.resolve_target_files(user_request),
            branch_name=slugify_branch(f"{user_request}-{proposal_id[:8]}"),
            commit_message=commit_message or f"Update Home Assistant config: {user_request[:72]}",
            summary=(
                "Préparation de la proposition GitOps en cours. "
                "Redemande le statut avec cette référence dans quelques secondes."
            ),
            user_answers=[],
            proposed_changes=[],
            validation_results=[],
        )
        self.proposal_store.save(proposal)
        return proposal

    async def complete_draft_change(self, proposal_id: str) -> HaChangeProposal:
        proposal = self.proposal_store.get(proposal_id)
        try:
            return await self.draft_change(
                user_request=proposal.user_request,
                commit_message=proposal.commit_message,
                accept_supplied_content=False,
                proposal_id=proposal.id,
                branch_name=proposal.branch_name,
            )
        except Exception as exc:
            failed = proposal.model_copy(
                update={
                    "status": HaChangeProposalStatus.needs_clarification,
                    "summary": "La génération de la proposition a échoué.",
                    "questions": [
                        "La génération automatique a échoué. Peux-tu reformuler ou préciser "
                        f"la demande ? Détail technique : {exc}"
                    ],
                }
            )
            self.proposal_store.save(failed)
            return failed

    def resolve_target_files(self, user_request: str, path: str | None = None) -> list[str]:
        inferred = self.infer_target_files(user_request)
        if path and path not in inferred:
            try:
                safe_path = ensure_editable_ha_path(path).as_posix()
            except ValueError:
                safe_path = ""
            if safe_path and (Path(self.git_service.repo_path) / safe_path).exists():
                inferred.insert(0, safe_path)
        return inferred[:4]

    async def ask_code_agent_for_changes(
        self,
        proposal_id: str,
        user_request: str,
        target_files: list[str],
        inventory: HaInventory | None,
        user_answers: list[str] | None = None,
    ) -> CodeAgentResult:
        files = self.read_target_files(target_files)
        request = CodeAgentRequest(
            run_id=proposal_id,
            user_request=user_request,
            instructions=HA_GITOPS_CHANGE_INSTRUCTIONS,
            context={
                "target_files": target_files,
                "ha_entities": [entity.model_dump() for entity in inventory.entities[:200]]
                if inventory
                else [],
                "ha_services": [service.model_dump() for service in inventory.services]
                if inventory
                else [],
                "rules": {
                    "base_branch": self.settings.gitops_default_branch,
                    "protected_paths": ["secrets.yaml", ".storage/"],
                    "output": "full_file_content",
                },
            },
            files=files,
            user_answers=user_answers or [],
        )
        try:
            return await self.code_agent.propose_changes(request)
        except (OSError, RuntimeError) as exc:
            return CodeAgentResult(
                type=CodeAgentResultType.failed,
                summary="Code agent failed while proposing Home Assistant changes.",
                error=str(exc),
            )

    def read_target_files(self, target_files: list[str]) -> list[CodeAgentFile]:
        files: list[CodeAgentFile] = []
        repo_path = Path(self.git_service.repo_path)
        for path in target_files:
            safe_path = ensure_editable_ha_path(path)
            target = repo_path / safe_path
            content = target.read_text(encoding="utf-8") if target.exists() else ""
            files.append(CodeAgentFile(path=safe_path.as_posix(), content=content))
        return files

    def changes_from_agent_result(self, result: CodeAgentResult) -> list[ProposedFileChange]:
        if result.type != CodeAgentResultType.proposed_changes:
            return []
        return [
            ProposedFileChange(path=file.path, content=file.content)
            for file in result.files
        ]

    async def answer_clarification(self, proposal_id: str, answer: str) -> HaChangeProposal:
        proposal = self.proposal_store.get(proposal_id)
        if proposal.status == HaChangeProposalStatus.pr_created:
            raise RuntimeError("Proposal already has a pull request")

        self.git_service.ensure_repo_current()
        inventory = await self.try_get_inventory()
        target_files = proposal.target_files or self.infer_target_files(proposal.user_request)
        user_answers = [*proposal.user_answers, answer]
        agent_result = await self.ask_code_agent_for_changes(
            proposal_id=proposal.id,
            user_request=proposal.user_request,
            target_files=target_files,
            inventory=inventory,
            user_answers=user_answers,
        )
        changes = self.changes_from_agent_result(agent_result)
        validation_results = self.validate_proposal(changes, inventory)
        questions = self.build_questions(proposal.user_request, target_files, changes, inventory)
        if agent_result.type == CodeAgentResultType.needs_clarification:
            questions.extend(agent_result.questions)
        elif agent_result.type == CodeAgentResultType.failed:
            questions.append(
                "L'agent de modification n'a pas réussi à produire une proposition. "
                f"Détail : {agent_result.error or agent_result.summary}"
            )

        status = (
            HaChangeProposalStatus.awaiting_confirmation
            if changes and all(result.ok for result in validation_results) and not questions
            else HaChangeProposalStatus.needs_clarification
        )
        updated = proposal.model_copy(
            update={
                "status": status,
                "questions": questions,
                "target_files": target_files,
                "summary": agent_result.summary or proposal.summary,
                "user_answers": user_answers,
                "proposed_changes": changes,
                "validation_results": validation_results,
            }
        )
        self.proposal_store.save(updated)
        return updated

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
        repo_path = Path(self.git_service.repo_path)
        if repo_path.exists():
            repo_matches = RepoContextCapability(repo_path).find_ha_package_candidates(
                user_request
            )
            if repo_matches:
                return repo_matches[:4]

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


HA_GITOPS_CHANGE_INSTRUCTIONS = """
Tu prépares une modification Home Assistant GitOps.

Règles obligatoires :
- Ne jamais modifier secrets.yaml, .storage ou un fichier contenant des secrets.
- Respecter l'organisation packages/areas, packages/functions, packages/routines,
  packages/integrations, packages/devices, packages/system.
- Utiliser uniquement des entités et services présents dans le contexte Home Assistant,
  sauf si l'utilisateur les a explicitement fournis.
- Si la demande est ambiguë ou risquée, retourner needs_clarification avec des questions courtes.
- Si tu proposes une modification, retourner le contenu complet des fichiers modifiés.
- Ne pas créer de branche, commit, push ou PR. Nestor s'en chargera après confirmation utilisateur.
""".strip()
