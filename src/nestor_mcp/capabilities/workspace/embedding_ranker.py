"""Optional semantic ranker for HA docs.

Uses fastembed (ONNX) to embed the question and pre-computed doc embeddings,
then ranks by cosine similarity. Imported lazily so the dep is optional.
"""

from __future__ import annotations

import logging
import math
from typing import Protocol

from nestor_mcp.capabilities.workspace.ha_doc_index import DocMatch, HaDoc

logger = logging.getLogger(__name__)


class EmbeddingRanker(Protocol):
    def rank(self, question: str, docs: list[HaDoc], top_k: int) -> list[DocMatch]: ...


class FastembedRanker:
    def __init__(
        self,
        model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    ) -> None:
        self.model_name = model_name
        self._model = None
        self._doc_vectors: dict[str, list[float]] = {}
        self._docs_signature: tuple[str, ...] = ()

    def _load(self):
        if self._model is None:
            from fastembed import TextEmbedding  # type: ignore[import-not-found]

            self._model = TextEmbedding(model_name=self.model_name)
        return self._model

    def warmup(self) -> bool:
        """Load the model and run a tiny embed to prime caches. Returns False on failure."""
        try:
            model = self._load()
            list(model.embed(["warmup"]))
            return True
        except Exception as exc:  # noqa: BLE001
            logger.warning("FastembedRanker warmup failed: %s", exc)
            return False

    def _ensure_doc_vectors(self, docs: list[HaDoc]) -> None:
        signature = tuple(doc.path for doc in docs)
        if signature == self._docs_signature and self._doc_vectors:
            return
        model = self._load()
        passages = [_doc_passage(doc) for doc in docs]
        vectors = list(model.embed(passages))
        self._doc_vectors = {
            doc.path: list(vec) for doc, vec in zip(docs, vectors, strict=True)
        }
        self._docs_signature = signature

    def rank(self, question: str, docs: list[HaDoc], top_k: int = 4) -> list[DocMatch]:
        if not docs:
            return []
        try:
            self._ensure_doc_vectors(docs)
            model = self._load()
            query_vec = list(next(model.embed([question])))
        except Exception as exc:  # noqa: BLE001 - dep may be missing or model fetch failed
            logger.warning("FastembedRanker unavailable: %s", exc)
            return []

        scored: list[DocMatch] = []
        for doc in docs:
            vec = self._doc_vectors.get(doc.path)
            if vec is None:
                continue
            sim = _cosine(query_vec, vec)
            scored.append(DocMatch(doc=doc, score=sim))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:top_k]


def _doc_passage(doc: HaDoc) -> str:
    aliases = ", ".join(doc.aliases)
    head = doc.body[:600]
    return f"{doc.title}\n{aliases}\n{head}"


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)
