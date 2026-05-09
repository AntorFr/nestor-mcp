import asyncio
from pathlib import Path

from nestor_mcp.capabilities.code_agent.models import CodeAgentFile
from nestor_mcp.capabilities.workspace.repo_context import RepoContextCapability
from nestor_mcp.models.home_assistant import HaEntity
from nestor_mcp.services.git_service import GitService
from nestor_mcp.services.home_assistant import HomeAssistantService


class HaExplainContextCollector:
    def __init__(
        self,
        git_service: GitService | None = None,
        home_assistant_service: HomeAssistantService | None = None,
    ) -> None:
        self.git_service = git_service or GitService()
        self.home_assistant_service = home_assistant_service or HomeAssistantService()

    async def collect(
        self,
        question: str,
        previous_files: list[str] | None = None,
    ) -> tuple[list[CodeAgentFile], list[dict]]:
        repo = self.git_service.ensure_repo_available()
        if repo.working_tree_dir is None:
            raise RuntimeError("Git repository has no working tree")
        repo_context = RepoContextCapability(Path(repo.working_tree_dir))
        candidate_paths, entities = await asyncio.gather(
            repo_context.find_ha_package_candidates(question, previous_files),
            self.try_collect_entities(question),
        )
        files = repo_context.read_files(candidate_paths)
        return files, entities

    async def try_collect_entities(self, question: str) -> list[dict]:
        try:
            states = await self.home_assistant_service.get_states()
        except RuntimeError:
            return []
        return [entity.model_dump() for entity in filter_entities(question, states)]


def filter_entities(question: str, entities: list[HaEntity]) -> list[HaEntity]:
    normalized = question.lower()
    matches = []
    for entity in entities:
        friendly_name = str(entity.attributes.get("friendly_name", "")).lower()
        if entity.entity_id.lower() in normalized or (
            friendly_name and friendly_name in normalized
        ):
            matches.append(entity)
    return matches[:30]
