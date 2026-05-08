from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DOC_DIRS = ("fonctions", "pieces", "routines")
SOURCE_TAG_RE = re.compile(r"<!--\s*source:\s*([a-z_]+):([a-zA-Z0-9_.\-]+)\s*-->")
TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)
WORD_RE = re.compile(r"[a-z0-9]+")
# Filtered from both questions and docs so generic French function words
# (and English question words) don't dominate scoring.
STOPWORDS = frozenset(
    {
        "les", "des", "une", "uns", "aux", "est", "sont", "etre", "ete", "etes",
        "avec", "sans", "pour", "par", "sur", "sous", "dans", "chez", "vers",
        "que", "qui", "quoi", "quel", "quels", "quelle", "quelles", "dont",
        "comment", "quand", "donc", "mais", "car", "ses", "son", "leur", "leurs",
        "cet", "cette", "ces", "tout", "tous", "toute", "toutes",
        "the", "and", "for", "with", "what", "how", "when", "are", "you",
    }
)


@dataclass
class HaDoc:
    path: str  # repo-relative
    title: str
    aliases: list[str]
    body: str
    sources: list[tuple[str, str]] = field(default_factory=list)  # (type, id)

    def tokens_title(self) -> set[str]:
        return _tokenize(self.title)

    def tokens_aliases(self) -> set[str]:
        out: set[str] = set()
        for alias in self.aliases:
            out |= _tokenize(alias)
        return out

    def tokens_body(self) -> set[str]:
        return _tokenize(self.body)


@dataclass
class DocMatch:
    doc: HaDoc
    score: float


class HaDocIndex:
    def __init__(self, docs: list[HaDoc]) -> None:
        self.docs = docs

    @classmethod
    def from_repo(cls, repo_path: Path) -> HaDocIndex:
        docs_root = repo_path / "docs"
        if not docs_root.is_dir():
            return cls([])

        docs: list[HaDoc] = []
        for sub in DOC_DIRS:
            sub_dir = docs_root / sub
            if not sub_dir.is_dir():
                continue
            for md_path in sorted(sub_dir.glob("*.md")):
                doc = _parse_doc(md_path, repo_path)
                if doc is not None:
                    docs.append(doc)
        return cls(docs)

    def search(self, question: str, top_k: int = 4, min_score: float = 1.0) -> list[DocMatch]:
        if not self.docs:
            return []
        q_tokens = _tokenize(question)
        if not q_tokens:
            return []
        scored: list[DocMatch] = []
        for doc in self.docs:
            score = _score_doc(doc, q_tokens)
            if score >= min_score:
                scored.append(DocMatch(doc=doc, score=score))
        scored.sort(key=lambda m: m.score, reverse=True)
        return scored[:top_k]


def _parse_doc(md_path: Path, repo_path: Path) -> HaDoc | None:
    try:
        raw = md_path.read_text(encoding="utf-8")
    except OSError:
        return None

    aliases: list[str] = []
    body = raw
    if raw.startswith("---\n"):
        end = raw.find("\n---", 4)
        if end != -1:
            front = raw[4:end]
            body = raw[end + 4 :].lstrip("\n")
            try:
                meta = yaml.safe_load(front) or {}
                if isinstance(meta, dict):
                    raw_aliases = meta.get("aliases") or meta.get("alias") or []
                    if isinstance(raw_aliases, str):
                        aliases = [raw_aliases]
                    elif isinstance(raw_aliases, list):
                        aliases = [str(a) for a in raw_aliases if a]
            except yaml.YAMLError:
                aliases = []

    title_match = TITLE_RE.search(body)
    title = title_match.group(1) if title_match else md_path.stem.replace("-", " ")
    sources = [(m.group(1), m.group(2)) for m in SOURCE_TAG_RE.finditer(body)]
    rel = md_path.relative_to(repo_path).as_posix()
    return HaDoc(path=rel, title=title, aliases=aliases, body=body, sources=sources)


def _score_doc(doc: HaDoc, q_tokens: set[str]) -> float:
    title_tokens = doc.tokens_title()
    alias_tokens = doc.tokens_aliases()
    body_tokens = doc.tokens_body()
    stem_tokens = _tokenize(Path(doc.path).stem.replace("-", " "))

    score = 0.0
    for tok in q_tokens:
        if tok in title_tokens:
            score += 5
        if tok in stem_tokens:
            score += 4
        if tok in alias_tokens:
            score += 3
        if tok in body_tokens:
            score += 1
    return score


def _tokenize(text: str) -> set[str]:
    if not text:
        return set()
    normalized = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in normalized if not unicodedata.combining(c))
    out: set[str] = set()
    for tok in WORD_RE.findall(stripped.lower()):
        if len(tok) < 3 or tok in STOPWORDS:
            continue
        out.add(tok)
        # Cheap French/English plural fold so "volets" matches "volet" and
        # "fermetures" matches "fermeture".
        if len(tok) >= 5 and tok.endswith("s") and not tok.endswith("ss"):
            out.add(tok[:-1])
    return out
