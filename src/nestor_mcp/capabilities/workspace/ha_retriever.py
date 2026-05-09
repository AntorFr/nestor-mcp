from __future__ import annotations

import asyncio
import logging
import re
import subprocess
from pathlib import Path

from nestor_mcp.capabilities.workspace.embedding_ranker import EmbeddingRanker
from nestor_mcp.capabilities.workspace.file_selector import (
    FileCandidate,
    FileSelector,
    HeadFileSelector,
)
from nestor_mcp.capabilities.workspace.ha_doc_index import HaDocIndex
from nestor_mcp.capabilities.workspace.ha_id_index import HaIdIndex

logger = logging.getLogger(__name__)

MAX_FILES = 8
RIPGREP_MIN_LEN = 4
EMBEDDING_TOP_K = 5
SUMMARY_BODY_CHARS = 220
SUMMARY_MAX_SECTIONS = 12
_SECTION_HEADER_RE = re.compile(r"(?m)^(#{2,4})\s+(.+?)\s*$")
RIPGREP_TIMEOUT_S = 2


class HaRetriever:
    """Two-stage HA file retrieval: broad recall, then LLM selection.

    Recall sources (run in parallel):
      - explicit ID matches in the question (cheap, exact)
      - ripgrep literal hits across packages/docs/custom_templates
      - optional embedding top-k over docs (semantic insurance)

    The combined candidate list (deduped) is handed to a FileSelector.
    The selector returns the paths actually needed, then we expand
    <!-- source: type:id --> tags for any selected .md so the LLM that
    eventually answers the question gets both the prose and the YAML.
    """

    def __init__(
        self,
        repo_path: Path,
        embedding_ranker: EmbeddingRanker | None = None,
        file_selector: FileSelector | None = None,
        max_candidates: int = 40,
        selector_deadline_s: float = 3.5,
    ) -> None:
        self.repo_path = repo_path
        self.embedding_ranker = embedding_ranker
        self.file_selector = file_selector or HeadFileSelector()
        self.max_candidates = max_candidates
        self.selector_deadline_s = selector_deadline_s
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

    async def retrieve(
        self,
        question: str,
        previous_files: list[str] | None = None,
    ) -> list[str]:
        # Touch indexes once before fanning out so background tasks see warm caches.
        _ = self.docs
        _ = self.ids

        ripgrep_task = asyncio.create_task(asyncio.to_thread(self._ripgrep, question))
        embedding_task = asyncio.create_task(
            asyncio.to_thread(self._embedding_paths, question)
        )
        id_paths = self.ids.find(question)
        ripgrep_paths, embedding_paths = await asyncio.gather(
            ripgrep_task, embedding_task
        )

        ordered = self._merge_recall(id_paths, embedding_paths, ripgrep_paths)
        if not ordered:
            return list(previous_files or [])[:MAX_FILES]

        candidates = [FileCandidate(path=p, summary=self._summarize(p)) for p in ordered]
        try:
            selected = await asyncio.wait_for(
                self.file_selector.select(question, candidates, MAX_FILES),
                timeout=self.selector_deadline_s,
            )
        except TimeoutError:
            logger.warning(
                "file selector exceeded deadline %.1fs, falling back to head",
                self.selector_deadline_s,
            )
            selected = []
        except Exception as exc:  # noqa: BLE001 - selector must never fail the call
            logger.warning("file selector raised, falling back: %s", exc)
            selected = []

        return self._finalize(selected or ordered[:MAX_FILES])

    def retrieve_sync(
        self,
        question: str,
        previous_files: list[str] | None = None,
    ) -> list[str]:
        """Synchronous variant for non-async callers.

        Skips the LLM selector entirely (head-of-list) so we never have to
        run an event loop from a sync context. Recall still benefits from
        ID-match + ripgrep + embeddings.
        """
        _ = self.docs
        _ = self.ids
        id_paths = self.ids.find(question)
        ripgrep_paths = self._ripgrep(question)
        embedding_paths = self._embedding_paths(question)
        ordered = self._merge_recall(id_paths, embedding_paths, ripgrep_paths)
        if not ordered:
            return list(previous_files or [])[:MAX_FILES]
        return self._finalize(ordered[:MAX_FILES])

    # --- internal pipeline helpers -------------------------------------

    def _merge_recall(
        self,
        id_paths: list[str],
        embedding_paths: list[str],
        ripgrep_paths: list[str],
    ) -> list[str]:
        ordered: list[str] = []
        seen: set[str] = set()

        def add(path: str) -> None:
            if path in seen or not (self.repo_path / path).exists():
                return
            seen.add(path)
            ordered.append(path)

        for p in id_paths:
            add(p)
        for p in embedding_paths:
            add(p)
        for p in ripgrep_paths:
            add(p)
            if len(ordered) >= self.max_candidates:
                break
        return ordered[: self.max_candidates]

    def _finalize(self, selected: list[str]) -> list[str]:
        results: list[str] = []
        seen: set[str] = set()

        def emit(path: str) -> None:
            if path in seen or not (self.repo_path / path).exists():
                return
            seen.add(path)
            results.append(path)

        for path in selected:
            emit(path)
            doc = self.docs.by_path.get(path)
            if doc is None:
                continue
            for _, ref_id in doc.sources:
                target = self.ids.by_id.get(ref_id.lower())
                if target:
                    emit(target)
        return results[:MAX_FILES]

    # --- recall helpers -------------------------------------------------

    def _ripgrep(self, question: str) -> list[str]:
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
                timeout=RIPGREP_TIMEOUT_S,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return []
        if proc.returncode not in (0, 1):
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def _embedding_paths(self, question: str) -> list[str]:
        if self.embedding_ranker is None or not self.docs.docs:
            return []
        return [
            m.doc.path
            for m in self.embedding_ranker.rank(question, self.docs.docs, top_k=EMBEDDING_TOP_K)
        ]

    def _summarize(self, path: str) -> str:
        doc = self.docs.by_path.get(path)
        if doc is not None:
            sections = _section_headers(doc.body, SUMMARY_MAX_SECTIONS)
            section_part = (
                f" — sections: {' / '.join(sections)}" if sections else ""
            )
            head = re.sub(r"\s+", " ", doc.body[:SUMMARY_BODY_CHARS]).strip()
            if doc.aliases:
                return (
                    f"{doc.title} (alias: {', '.join(doc.aliases)}){section_part} — {head}"
                )
            return f"{doc.title}{section_part} — {head}"
        # Non-doc files: return a hint based on the path itself; reading the
        # file just for a summary would dominate latency on large YAMLs.
        stem = Path(path).stem.replace("_", " ").replace("-", " ")
        if path.endswith(".yaml") or path.endswith(".yml"):
            return f"YAML config: {stem}"
        if path.endswith(".jinja") or path.endswith(".j2"):
            return f"Template: {stem}"
        return stem


def _section_headers(body: str, limit: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for match in _SECTION_HEADER_RE.finditer(body):
        title = match.group(2).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        out.append(title)
        if len(out) >= limit:
            break
    return out


