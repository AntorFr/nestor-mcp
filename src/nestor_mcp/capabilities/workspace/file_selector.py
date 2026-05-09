"""LLM-based file selector for HA retrieval.

Given a question and a list of candidate file summaries, asks a small/fast
model to return the subset of paths actually needed to answer. Falls back
to a deterministic head-of-list strategy if the LLM is unavailable.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Protocol

import httpx

from nestor_mcp.capabilities.llm.providers import parse_json_object_from_text
from nestor_mcp.config import get_settings

logger = logging.getLogger(__name__)


@dataclass
class FileCandidate:
    path: str
    summary: str  # short blurb shown to the selector


class FileSelector(Protocol):
    async def select(
        self, question: str, candidates: list[FileCandidate], max_files: int
    ) -> list[str]: ...


class HeadFileSelector:
    """No-op selector: keeps the first N candidates in input order."""

    async def select(
        self, question: str, candidates: list[FileCandidate], max_files: int
    ) -> list[str]:
        return [c.path for c in candidates[:max_files]]


class AnthropicFileSelector:
    def __init__(self, model: str, timeout_seconds: float, api_key: str) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key

    async def select(
        self, question: str, candidates: list[FileCandidate], max_files: int
    ) -> list[str]:
        if not candidates:
            return []

        valid_paths = {c.path for c in candidates}
        listing = "\n".join(
            f"{i + 1}. {c.path}\n   {c.summary}" for i, c in enumerate(candidates)
        )
        system = (
            "Tu es un sélecteur de fichiers pour une configuration Home Assistant.\n"
            "On te donne une question utilisateur et une liste de fichiers candidats "
            "(chemin + description avec titre + sections).\n\n"
            "Objectif: rassembler TOUS les fichiers nécessaires pour donner une "
            "réponse COMPLETE — pas seulement le plus pertinent. Si plusieurs "
            "routines, fonctions ou pièces touchent au sujet, inclus-les TOUTES.\n"
            "En cas de doute, préfère sur-sélectionner. Inclus les .md explicatifs "
            "ET les .yaml de configuration utiles.\n\n"
            f"Renvoie UNIQUEMENT du JSON: {{\"paths\": [...]}} avec au plus {max_files} "
            "chemins choisis parmi la liste, dans l'ordre de pertinence. Ne réponds "
            "rien d'autre."
        )
        user = f"Question:\n{question}\n\nCandidats:\n{listing}"

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                response = await client.post(
                    "https://api.anthropic.com/v1/messages",
                    headers={
                        "x-api-key": self.api_key,
                        "anthropic-version": "2023-06-01",
                        "content-type": "application/json",
                    },
                    json={
                        "model": self.model,
                        "max_tokens": 500,
                        "temperature": 0.0,
                        "system": system,
                        "messages": [{"role": "user", "content": user}],
                    },
                )
                response.raise_for_status()
                data = response.json()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            logger.warning(
                "FileSelector LLM call failed: %s: %s",
                type(exc).__name__,
                exc or "(no message)",
            )
            return []

        text = _extract_text(data)
        if not text:
            return []
        try:
            parsed = parse_json_object_from_text(text)
        except (ValueError, json.JSONDecodeError) as exc:
            logger.warning("FileSelector returned non-JSON output: %s", exc)
            return []

        raw_paths = parsed.get("paths") or []
        if not isinstance(raw_paths, list):
            return []
        out: list[str] = []
        for p in raw_paths:
            if isinstance(p, str) and p in valid_paths and p not in out:
                out.append(p)
            if len(out) >= max_files:
                break
        return out


def get_file_selector() -> FileSelector:
    settings = get_settings()
    if not settings.ha_selector_enabled or not settings.anthropic_api_key:
        return HeadFileSelector()
    return AnthropicFileSelector(
        model=settings.ha_selector_model,
        timeout_seconds=settings.ha_selector_timeout_seconds,
        api_key=settings.anthropic_api_key,
    )


def _extract_text(data: object) -> str:
    if not isinstance(data, dict):
        return ""
    content = data.get("content")
    if not isinstance(content, list):
        return ""
    parts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    return "\n".join(p for p in parts if p).strip()
