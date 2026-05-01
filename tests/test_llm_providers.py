import json

from nestor_mcp.capabilities.llm.providers import (
    MockLlmCapability,
    get_llm_capability,
    parse_anthropic_explain_response,
)


def test_parse_anthropic_explain_response_accepts_json_text() -> None:
    result = parse_anthropic_explain_response(
        {
            "content": [
                {
                    "type": "text",
                    "text": json.dumps(
                        {
                            "answer": "Réponse courte.",
                            "referenced_files": ["packages/areas/salon.yaml"],
                            "referenced_entities": ["light.salon"],
                            "follow_up_suggestions": ["Détailler"],
                        }
                    ),
                }
            ]
        }
    )

    assert result.answer == "Réponse courte."
    assert result.referenced_files == ["packages/areas/salon.yaml"]


def test_parse_anthropic_explain_response_extracts_json_from_markdown() -> None:
    result = parse_anthropic_explain_response(
        {
            "content": [
                {
                    "type": "text",
                    "text": (
                        "```json\n"
                        '{"answer":"OK","referenced_files":[],"referenced_entities":[],'
                        '"follow_up_suggestions":[]}'
                        "\n```"
                    ),
                }
            ]
        }
    )

    assert result.answer == "OK"


def test_get_llm_capability_uses_ha_explain_provider(monkeypatch) -> None:
    from nestor_mcp.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("DEFAULT_LLM_PROVIDER", "anthropic_api")
    monkeypatch.setenv("HA_EXPLAIN_PROVIDER", "mock")

    try:
        capability = get_llm_capability("ha_explain")
    finally:
        get_settings.cache_clear()

    assert isinstance(capability, MockLlmCapability)
