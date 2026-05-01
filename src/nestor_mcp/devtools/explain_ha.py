import argparse
import asyncio
from collections.abc import Sequence

from nestor_mcp.workflows.ha_explain.models import HaExplainResponse
from nestor_mcp.workflows.ha_explain.workflow import HaExplainWorkflow


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Ask the HA explain workflow a question.")
    parser.add_argument("question", help="Question to ask about the Home Assistant config")
    parser.add_argument("--run-id", help="Existing run id for a follow-up question")
    parser.add_argument("--json", action="store_true", help="Print the raw JSON response")
    return parser


async def run_explain(
    question: str,
    run_id: str | None = None,
    workflow: HaExplainWorkflow | None = None,
) -> HaExplainResponse:
    workflow = workflow or HaExplainWorkflow()
    return await workflow.ask(question=question, run_id=run_id)


def format_text_response(response: HaExplainResponse) -> str:
    parts = [
        f"run_id: {response.run_id}",
        "",
        response.answer,
    ]
    if response.referenced_files:
        parts.extend(
            ["", "referenced_files:", *[f"- {path}" for path in response.referenced_files]]
        )
    if response.referenced_entities:
        parts.extend(
            [
                "",
                "referenced_entities:",
                *[f"- {entity}" for entity in response.referenced_entities],
            ]
        )
    if response.follow_up_suggestions:
        parts.extend(
            [
                "",
                "follow_up_suggestions:",
                *[f"- {suggestion}" for suggestion in response.follow_up_suggestions],
            ]
        )
    return "\n".join(parts)


async def async_main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    response = await run_explain(question=args.question, run_id=args.run_id)
    if args.json:
        print(response.model_dump_json(indent=2))
    else:
        print(format_text_response(response))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
