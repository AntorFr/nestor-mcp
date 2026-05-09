import asyncio
import logging
import re
from pathlib import Path

from nestor_mcp.capabilities.code_agent.models import CodeAgentFile
from nestor_mcp.capabilities.workspace.repo_context import RepoContextCapability
from nestor_mcp.models.home_assistant import HaEntity
from nestor_mcp.services.git_service import GitService
from nestor_mcp.services.home_assistant import HomeAssistantService

logger = logging.getLogger(__name__)

# Looks like a HA entity id ("light.salon", "binary_sensor.foo_bar"):
# at least one dot between two snake-cased atoms.
_ENTITY_ID_RE = re.compile(r"\b[a-z_]{3,}\.[a-z0-9_]{2,}\b")
_GET_STATES_TIMEOUT_S = 1.5


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
        # filter_entities only keeps states whose entity_id or friendly_name
        # appears literally in the question. If neither pattern can possibly
        # match, the /api/states fetch (which can be hundreds of KB) is pure
        # latency tax — skip it.
        if not _question_might_reference_entity(question):
            return []
        try:
            states = await asyncio.wait_for(
                self.home_assistant_service.get_states(),
                timeout=_GET_STATES_TIMEOUT_S,
            )
        except (RuntimeError, TimeoutError) as exc:
            logger.debug("get_states skipped: %s", exc)
            return []
        return [entity.model_dump() for entity in filter_entities(question, states)]


def _question_might_reference_entity(question: str) -> bool:
    """Cheap pre-filter to decide whether fetching /api/states is worth it.

    filter_entities only keeps states whose entity_id appears in the
    question, or whose friendly_name appears literally. Without an entity
    id pattern AND without any token long enough to plausibly be a
    friendly_name fragment, the fetch is wasted. We keep the bar low so we
    only skip clearly-conceptual questions ("comment", "pourquoi", etc.).
    """
    normalized = question.lower()
    if _ENTITY_ID_RE.search(normalized):
        return True
    # If the question has any 6+ char word that isn't a common French
    # interrogative/connector, it might be a friendly_name fragment.
    tokens = re.findall(r"[a-zA-Zàâäéèêëïîôöùûüç]{6,}", normalized)
    if not tokens:
        return False
    discardable = {
        "comment", "pourquoi", "quelles", "quelle", "quels", "lorsque",
        "pendant", "configuration", "automatisation", "automatisations",
        "fonctionnement", "comportement", "expliquer", "explique",
    }
    return any(t not in discardable for t in tokens)


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
