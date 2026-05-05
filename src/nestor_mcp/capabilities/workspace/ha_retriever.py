from __future__ import annotations

import re
import subprocess
from pathlib import Path

from nestor_mcp.capabilities.workspace.embedding_ranker import EmbeddingRanker
from nestor_mcp.capabilities.workspace.ha_doc_index import HaDocIndex
from nestor_mcp.capabilities.workspace.ha_id_index import HaIdIndex

MAX_FILES = 8
RIPGREP_MIN_LEN = 4
SEMANTIC_TOP_K = 3


class HaRetriever:
    """Routes a HA question to a small set of relevant repo files.

    Order: explicit ID match -> doc lexical search (with source tag resolution)
    -> ripgrep fallback on the whole repo -> previous_files carryover.
    """

    def __init__(
        self,
        repo_path: Path,
        embedding_ranker: EmbeddingRanker | None = None,
        lexical_threshold: float = 5.0,
    ) -> None:
        self.repo_path = repo_path
        self.embedding_ranker = embedding_ranker
        self.lexical_threshold = lexical_threshold
        self._docs: HaDocIndex | None = None
        self._ids: HaIdIndex | None = None

    @property
    def docs(self) -> HaDocIndex:
        if self._docs is None:
            self._docs = HaDocIndex.from_repo(self.repo_path)
        return self._docs

    @property
    def ids(self) -> HaIdIndex:
        if self._ids is None:
            self._ids = HaIdIndex.from_repo(self.repo_path)
        return self._ids

    def retrieve(
        self,
        question: str,
        previous_files: list[str] | None = None,
    ) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()

        def add(path: str) -> None:
            if path not in seen and (self.repo_path / path).exists():
                seen.add(path)
                results.append(path)

        for path in self.ids.find(question):
            add(path)

        lexical = self.docs.search(question)
        for match in lexical:
            add(match.doc.path)
            for _, ref_id in match.doc.sources:
                target = self.ids.by_id.get(ref_id.lower())
                if target:
                    add(target)

        weak_lexical = not lexical or lexical[0].score < self.lexical_threshold
        if weak_lexical and self.embedding_ranker is not None and self.docs.docs:
            for match in self.embedding_ranker.rank(
                question, self.docs.docs, top_k=SEMANTIC_TOP_K
            ):
                add(match.doc.path)
                for _, ref_id in match.doc.sources:
                    target = self.ids.by_id.get(ref_id.lower())
                    if target:
                        add(target)

        if not results:
            for path in self._ripgrep_fallback(question):
                add(path)

        if not results and previous_files:
            for path in previous_files:
                add(path)

        return results[:MAX_FILES]

    def _ripgrep_fallback(self, question: str) -> list[str]:
        terms = [
            t
            for t in re.findall(r"[a-zA-Z0-9_]+", question.lower())
            if len(t) >= RIPGREP_MIN_LEN
        ]
        if not terms:
            return []
        pattern = "|".join(re.escape(t) for t in terms)
        try:
            proc = subprocess.run(
                ["rg", "-l", "-i", "-S", pattern, "packages", "custom_templates", "docs"],
                cwd=self.repo_path,
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if proc.returncode not in (0, 1):
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]
