from functools import lru_cache
from pathlib import Path

from nestor_mcp.capabilities.code_agent.models import CodeAgentFile
from nestor_mcp.capabilities.workspace.embedding_ranker import (
    EmbeddingRanker,
    FastembedRanker,
)
from nestor_mcp.capabilities.workspace.file_selector import FileSelector, get_file_selector
from nestor_mcp.capabilities.workspace.ha_retriever import HaRetriever
from nestor_mcp.config import get_settings


@lru_cache(maxsize=1)
def _shared_ranker() -> EmbeddingRanker | None:
    settings = get_settings()
    if not settings.ha_retrieval_embeddings_enabled:
        return None
    return FastembedRanker(model_name=settings.ha_retrieval_embedding_model)


class RepoContextCapability:
    def __init__(
        self,
        repo_path: Path,
        embedding_ranker: EmbeddingRanker | None | object = ...,
        file_selector: FileSelector | None = None,
    ) -> None:
        self.repo_path = repo_path
        settings = get_settings()
        ranker = embedding_ranker if embedding_ranker is not ... else _shared_ranker()
        self.retriever = HaRetriever(
            repo_path,
            embedding_ranker=ranker,  # type: ignore[arg-type]
            file_selector=file_selector or get_file_selector(),
            max_candidates=settings.ha_selector_max_candidates,
            selector_deadline_s=settings.ha_selector_deadline_seconds,
        )

    async def find_ha_package_candidates(
        self,
        question: str,
        previous_files: list[str] | None = None,
    ) -> list[str]:
        return await self.retriever.retrieve(question, previous_files)

    def find_ha_package_candidates_sync(
        self,
        question: str,
        previous_files: list[str] | None = None,
    ) -> list[str]:
        return self.retriever.retrieve_sync(question, previous_files)

    def read_files(self, paths: list[str], max_chars_per_file: int = 45000) -> list[CodeAgentFile]:
        files = []
        for path in paths:
            target = self.repo_path / path
            if not target.exists() or not target.is_file():
                continue
            content = target.read_text(encoding="utf-8")[:max_chars_per_file]
            files.append(CodeAgentFile(path=path, content=content))
        return files
