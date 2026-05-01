import json

import httpx

from nestor_mcp.capabilities.llm.capability import LlmCapability
from nestor_mcp.capabilities.llm.models import LlmExplainRequest, LlmExplainResult
from nestor_mcp.config import get_settings


class MockLlmCapability(LlmCapability):
    async def explain(self, request: LlmExplainRequest) -> LlmExplainResult:
        file_list = ", ".join(file.path for file in request.files) or "aucun fichier"
        entity_ids = [
            entity["entity_id"]
            for entity in request.context.get("ha_entities", [])
            if isinstance(entity, dict) and "entity_id" in entity
        ][:12]
        entity_text = ", ".join(entity_ids) if entity_ids else "aucune entité HA disponible"
        return LlmExplainResult(
            answer=(
                f"J'ai analysé la question: {request.question}\n\n"
                f"Fichiers candidats: {file_list}.\n"
                f"Entités pertinentes: {entity_text}.\n\n"
                "Le provider mock confirme que le workflow a collecté le contexte nécessaire."
            ),
            referenced_files=[file.path for file in request.files],
            referenced_entities=entity_ids,
            follow_up_suggestions=[
                "Détailler les déclencheurs",
                "Lister les entités impliquées",
                "Expliquer les conditions",
            ],
        )


class AnthropicApiLlmCapability(LlmCapability):
    async def explain(self, request: LlmExplainRequest) -> LlmExplainResult:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not configured")

        async with httpx.AsyncClient(timeout=settings.ha_explain_timeout_seconds) as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": settings.anthropic_api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": settings.ha_explain_model,
                    "max_tokens": 1200,
                    "temperature": 0.1,
                    "system": build_explain_system_prompt(request),
                    "messages": [
                        {
                            "role": "user",
                            "content": build_explain_user_prompt(request),
                        }
                    ],
                },
            )
            response.raise_for_status()

        return parse_anthropic_explain_response(response.json())


def get_llm_capability(workflow: str) -> LlmCapability:
    settings = get_settings()
    provider = settings.default_llm_provider
    if workflow == "ha_explain":
        provider = settings.ha_explain_provider or provider

    provider = provider.lower()
    if provider == "anthropic_api":
        return AnthropicApiLlmCapability()
    if provider == "mock":
        return MockLlmCapability()
    raise ValueError(f"Unsupported LLM provider for {workflow}: {provider}")


def build_explain_system_prompt(request: LlmExplainRequest) -> str:
    return (
        "Tu es un assistant expert Home Assistant en mode lecture seule.\n"
        "Tu dois expliquer la configuration fournie sans proposer de modification.\n"
        "Respecte strictement les instructions de style et de niveau de détail.\n"
        "Réponds uniquement en JSON valide avec les clés: answer, referenced_files, "
        "referenced_entities, follow_up_suggestions.\n\n"
        f"{request.instructions}"
    )


def build_explain_user_prompt(request: LlmExplainRequest) -> str:
    payload = {
        "question": request.question,
        "history": request.history,
        "context": request.context,
        "files": [file.model_dump() for file in request.files],
    }
    return json.dumps(payload, ensure_ascii=False)


def parse_anthropic_explain_response(data: object) -> LlmExplainResult:
    if not isinstance(data, dict):
        raise RuntimeError("Unexpected Anthropic response")

    content = data.get("content")
    if not isinstance(content, list):
        raise RuntimeError("Unexpected Anthropic content response")

    text_parts = [
        item.get("text", "")
        for item in content
        if isinstance(item, dict) and item.get("type") == "text"
    ]
    text = "\n".join(part for part in text_parts if part).strip()
    if not text:
        raise RuntimeError("Anthropic response does not contain text")

    return LlmExplainResult.model_validate(parse_json_object_from_text(text))


def parse_json_object_from_text(text: str) -> dict:
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = json.loads(extract_first_json_object(text))
    if not isinstance(data, dict):
        raise ValueError("LLM result must contain a JSON object")
    return data


def extract_first_json_object(text: str) -> str:
    start = text.find("{")
    if start == -1:
        raise ValueError("LLM result does not contain a JSON object")

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

    raise ValueError("LLM result contains an incomplete JSON object")
