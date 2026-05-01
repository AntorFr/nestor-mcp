import asyncio
import json

from nestor_mcp.capabilities.code_agent.capability import CodeAgentCapability
from nestor_mcp.capabilities.code_agent.models import (
    CodeAgentExplainRequest,
    CodeAgentExplainResult,
    CodeAgentRequest,
    CodeAgentResult,
    CodeAgentResultType,
)
from nestor_mcp.config import get_settings


class MockCodeAgentCapability(CodeAgentCapability):
    async def propose_changes(self, request: CodeAgentRequest) -> CodeAgentResult:
        return CodeAgentResult(
            type=CodeAgentResultType.needs_clarification,
            summary="Mock code agent requires more information.",
            questions=["Quel changement exact dois-je produire ?"],
        )

    async def explain_config(self, request: CodeAgentExplainRequest) -> CodeAgentExplainResult:
        file_list = ", ".join(file.path for file in request.files) or "aucun fichier"
        entity_ids = [
            entity["entity_id"]
            for entity in request.context.get("ha_entities", [])
            if isinstance(entity, dict) and "entity_id" in entity
        ][:12]
        entity_text = ", ".join(entity_ids) if entity_ids else "aucune entité HA disponible"
        return CodeAgentExplainResult(
            answer=(
                f"J'ai analysé la question: {request.question}\n\n"
                f"Fichiers candidats: {file_list}.\n"
                f"Entités pertinentes: {entity_text}.\n\n"
                "Le provider mock ne fait pas encore d'analyse sémantique complète, mais le "
                "workflow a collecté le contexte nécessaire pour un agent code read-only."
            ),
            referenced_files=[file.path for file in request.files],
            referenced_entities=entity_ids,
            follow_up_suggestions=[
                "Détailler les déclencheurs",
                "Lister les entités impliquées",
                "Expliquer les conditions",
            ],
        )


class ClaudeCodeCapability(CodeAgentCapability):
    async def propose_changes(self, request: CodeAgentRequest) -> CodeAgentResult:
        settings = get_settings()
        prompt = build_change_prompt(request)
        process = await asyncio.create_subprocess_exec(
            settings.claude_code_command,
            "-p",
            prompt,
            "--output-format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.ha_gitops_timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError("Claude Code timed out while proposing changes") from exc

        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())

        return parse_claude_change_output(stdout.decode("utf-8", errors="replace"))

    async def explain_config(self, request: CodeAgentExplainRequest) -> CodeAgentExplainResult:
        settings = get_settings()
        prompt = build_explain_prompt(request)
        process = await asyncio.create_subprocess_exec(
            settings.claude_code_command,
            "-p",
            prompt,
            "--output-format",
            "json",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=settings.claude_code_timeout_seconds,
            )
        except TimeoutError as exc:
            process.kill()
            await process.communicate()
            raise RuntimeError("Claude Code timed out") from exc

        if process.returncode != 0:
            raise RuntimeError(stderr.decode("utf-8", errors="replace").strip())

        return parse_claude_explain_output(stdout.decode("utf-8", errors="replace"))


def get_code_agent_capability() -> CodeAgentCapability:
    settings = get_settings()
    provider = (settings.ha_gitops_provider or settings.default_code_agent_provider).lower()
    if provider == "claude_code":
        return ClaudeCodeCapability()
    if provider == "mock":
        return MockCodeAgentCapability()
    raise ValueError(f"Unsupported code agent provider: {provider}")


def build_explain_prompt(request: CodeAgentExplainRequest) -> str:
    payload = {
        "question": request.question,
        "instructions": request.instructions,
        "history": request.history,
        "context": request.context,
        "files": [file.model_dump() for file in request.files],
    }
    return (
        "Tu es un agent expert Home Assistant en mode lecture seule.\n"
        "Tu dois expliquer la configuration fournie sans proposer de modification.\n"
        "Respecte strictement les instructions de style et de niveau de détail incluses "
        "dans le payload.\n"
        "Réponds uniquement en JSON valide avec les clés: answer, referenced_files, "
        "referenced_entities, follow_up_suggestions.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def build_change_prompt(request: CodeAgentRequest) -> str:
    payload = {
        "run_id": request.run_id,
        "user_request": request.user_request,
        "instructions": request.instructions,
        "context": request.context,
        "files": [file.model_dump() for file in request.files],
        "user_answers": request.user_answers,
    }
    return (
        "Tu es un agent code spécialisé Home Assistant.\n"
        "Tu dois proposer une modification GitOps sûre, sans pousser, sans créer de branche, "
        "sans appeler Home Assistant, sans modifier secrets.yaml ni .storage.\n"
        "Les fichiers fournis sont le contexte autorisé. Si une information manque, pose des "
        "questions au lieu d'inventer des entités ou des comportements.\n"
        "Réponds uniquement en JSON valide avec les clés: type, summary, questions, files, error.\n"
        "type doit valoir needs_clarification, proposed_changes ou failed.\n"
        "files doit contenir des objets {path, content} avec le contenu complet du fichier cible, "
        "pas un patch partiel.\n\n"
        f"{json.dumps(payload, ensure_ascii=False)}"
    )


def parse_claude_change_output(output: str) -> CodeAgentResult:
    data = json.loads(output)
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        data = parse_json_object_from_text(data["result"])
    return CodeAgentResult.model_validate(data)


def parse_claude_explain_output(output: str) -> CodeAgentExplainResult:
    data = json.loads(output)
    if isinstance(data, dict) and isinstance(data.get("result"), str):
        data = parse_json_object_from_text(data["result"])
    return CodeAgentExplainResult.model_validate(data)


def parse_json_object_from_text(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = json.loads(extract_first_json_object(text))
    if not isinstance(data, dict):
        raise ValueError("Claude Code result must contain a JSON object")
    return data


def extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("Claude Code result does not contain a JSON object")

    depth = 0
    in_string = False
    escaped = False
    for index, char in enumerate(text[start:], start=start):
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return text[start : index + 1]

    raise ValueError("Claude Code result contains an incomplete JSON object")
