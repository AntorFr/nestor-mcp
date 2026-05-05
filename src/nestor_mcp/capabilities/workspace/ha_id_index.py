from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

PACKAGES_DIR = "packages"
ID_TOKEN_RE = re.compile(r"[a-z][a-z0-9_]{3,}(?:\.[a-z0-9_]+)?")


@dataclass
class HaIdIndex:
    by_id: dict[str, str] = field(default_factory=dict)  # id -> repo-relative file path
    by_filename_stem: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_repo(cls, repo_path: Path) -> HaIdIndex:
        index = cls()
        pkg_root = repo_path / PACKAGES_DIR
        if not pkg_root.is_dir():
            return index
        for yaml_path in pkg_root.rglob("*.yaml"):
            rel = yaml_path.relative_to(repo_path).as_posix()
            stem = yaml_path.stem.lower()
            index.by_filename_stem.setdefault(stem, rel)
            index._index_yaml_file(yaml_path, rel)
        return index

    def _index_yaml_file(self, yaml_path: Path, rel: str) -> None:
        try:
            data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
        except (OSError, yaml.YAMLError):
            return
        for token in _walk_ids(data):
            self.by_id.setdefault(token.lower(), rel)

    def find(self, question: str) -> list[str]:
        normalized = question.lower()
        hits: list[str] = []
        seen: set[str] = set()
        for token in ID_TOKEN_RE.findall(normalized):
            path = self.by_id.get(token)
            if path is None and "." not in token:
                # Try filename stem (e.g. "portail" -> portail.yaml)
                path = self.by_filename_stem.get(token)
            if path and path not in seen:
                seen.add(path)
                hits.append(path)
        return hits


def _walk_ids(node: object) -> list[str]:
    out: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            if key in ("id", "alias", "name", "entity_id", "unique_id") and isinstance(value, str):
                out.append(value)
            elif key == "entity_id" and isinstance(value, list):
                out.extend(v for v in value if isinstance(v, str))
            else:
                out.extend(_walk_ids(value))
    elif isinstance(node, list):
        for item in node:
            out.extend(_walk_ids(item))
    return out
