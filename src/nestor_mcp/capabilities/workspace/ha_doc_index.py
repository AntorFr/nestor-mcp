"""Markdown doc index for HA repo (titles, aliases, source-tag back-references).

The lexical scoring previously hosted here has been replaced by the LLM
file selector, so this module only carries metadata used downstream:
- a short summary per doc (title + first chars) for the selector prompt,
- the <!-- source: type:id --> tags so we can expand a selected doc to the
  YAML file(s) it documents.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

DOC_DIRS = ("fonctions", "pieces", "routines")
SOURCE_TAG_RE = re.compile(r"<!--\s*source:\s*([a-z_]+):([a-zA-Z0-9_.\-]+)\s*-->")
TITLE_RE = re.compile(r"^#\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class HaDoc:
    path: str  # repo-relative
    title: str
    aliases: list[str]
    body: str
    sources: list[tuple[str, str]] = field(default_factory=list)  # (type, id)


@dataclass
class DocMatch:
    doc: HaDoc
    score: float


class HaDocIndex:
    def __init__(self, docs: list[HaDoc]) -> None:
        self.docs = docs
        self.by_path = {doc.path: doc for doc in docs}

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
