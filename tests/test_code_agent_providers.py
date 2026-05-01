import json

from nestor_mcp.capabilities.code_agent.providers import (
    parse_claude_change_output,
    parse_claude_explain_output,
)


def test_parse_claude_explain_output_accepts_direct_json() -> None:
    result = parse_claude_explain_output(
        json.dumps(
            {
                "answer": "Les lumières sont allumées par une automation.",
                "referenced_files": ["packages/areas/salon/lights.yaml"],
                "referenced_entities": ["light.salon"],
                "follow_up_suggestions": ["Voir les conditions"],
            }
        )
    )

    assert result.answer == "Les lumières sont allumées par une automation."
    assert result.referenced_files == ["packages/areas/salon/lights.yaml"]


def test_parse_claude_explain_output_accepts_claude_result_wrapper() -> None:
    result = parse_claude_explain_output(
        json.dumps(
            {
                "type": "result",
                "result": json.dumps(
                    {
                        "answer": "Automation détectée.",
                        "referenced_files": ["packages/functions/lights.yaml"],
                        "referenced_entities": ["automation.salon"],
                        "follow_up_suggestions": [],
                    }
                ),
            }
        )
    )

    assert result.answer == "Automation détectée."
    assert result.referenced_entities == ["automation.salon"]


def test_parse_claude_explain_output_extracts_json_from_text_result() -> None:
    result = parse_claude_explain_output(
        json.dumps(
            {
                "type": "result",
                "result": (
                    "Voici la réponse:\n"
                    "```json\n"
                    '{"answer":"OK","referenced_files":[],"referenced_entities":[],'
                    '"follow_up_suggestions":["Approfondir"]}'
                    "\n```"
                ),
            }
        )
    )

    assert result.answer == "OK"
    assert result.follow_up_suggestions == ["Approfondir"]


def test_parse_claude_change_output_accepts_proposed_files() -> None:
    result = parse_claude_change_output(
        json.dumps(
            {
                "type": "result",
                "result": json.dumps(
                    {
                        "type": "proposed_changes",
                        "summary": "Ajoute une automation.",
                        "questions": [],
                        "files": [
                            {
                                "path": "packages/areas/salon.yaml",
                                "content": "automation: []\n",
                            }
                        ],
                        "error": None,
                    }
                ),
            }
        )
    )

    assert result.type == "proposed_changes"
    assert result.files[0].path == "packages/areas/salon.yaml"
