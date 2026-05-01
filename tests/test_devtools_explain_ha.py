import pytest

from nestor_mcp.devtools.explain_ha import format_text_response, run_explain
from nestor_mcp.orchestration.state import WorkflowStatus
from nestor_mcp.workflows.ha_explain.models import HaExplainResponse


class FakeWorkflow:
    async def ask(self, question: str, run_id: str | None = None) -> HaExplainResponse:
        return HaExplainResponse(
            run_id=run_id or "haexp_test",
            status=WorkflowStatus.completed,
            answer=f"Answer for: {question}",
            referenced_files=["packages/areas/salon.yaml"],
            referenced_entities=["light.salon_lumieres"],
            follow_up_suggestions=["Détailler les déclencheurs"],
        )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_run_explain_accepts_injected_workflow() -> None:
    response = await run_explain("Pourquoi ?", workflow=FakeWorkflow())  # type: ignore[arg-type]

    assert response.run_id == "haexp_test"
    assert response.referenced_files == ["packages/areas/salon.yaml"]


def test_format_text_response_contains_debug_fields() -> None:
    response = HaExplainResponse(
        run_id="haexp_test",
        status=WorkflowStatus.completed,
        answer="Test answer",
        referenced_files=["packages/areas/salon.yaml"],
        referenced_entities=["light.salon_lumieres"],
        follow_up_suggestions=["Détailler les déclencheurs"],
    )

    text = format_text_response(response)

    assert "run_id: haexp_test" in text
    assert "- packages/areas/salon.yaml" in text
    assert "- light.salon_lumieres" in text
