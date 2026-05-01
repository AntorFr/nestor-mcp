from pathlib import Path

import pytest

from nestor_mcp.capabilities.code_agent.capability import CodeAgentCapability
from nestor_mcp.capabilities.code_agent.models import (
    CodeAgentExplainRequest,
    CodeAgentExplainResult,
    CodeAgentFile,
    CodeAgentRequest,
    CodeAgentResult,
    CodeAgentResultType,
)
from nestor_mcp.capabilities.code_agent.providers import MockCodeAgentCapability
from nestor_mcp.capabilities.workspace.repo_context import RepoContextCapability
from nestor_mcp.orchestration.store import WorkflowStore
from nestor_mcp.workflows.ha_explain.graph import HaExplainGraphFactory, infer_answer_style
from nestor_mcp.workflows.ha_explain.workflow import HaExplainWorkflow


class FakeContextCollector:
    def __init__(self) -> None:
        self.previous_files_seen: list[str] = []

    async def collect(
        self,
        question: str,
        previous_files: list[str] | None = None,
    ) -> tuple[list[CodeAgentFile], list[dict]]:
        self.previous_files_seen = previous_files or []
        files = [
            CodeAgentFile(
                path="packages/areas/salon.yaml",
                content="automation:\n- alias: Area - Salon - Lumiere auto\n",
            )
        ]
        entities = [{"entity_id": "light.salon_lumieres", "state": "off", "attributes": {}}]
        return files, entities


class CapturingCodeAgent(CodeAgentCapability):
    def __init__(self) -> None:
        self.requests: list[CodeAgentExplainRequest] = []

    async def propose_changes(self, request: CodeAgentRequest) -> CodeAgentResult:
        return CodeAgentResult(
            type=CodeAgentResultType.failed,
            summary="Not implemented in this fake.",
        )

    async def explain_config(self, request: CodeAgentExplainRequest) -> CodeAgentExplainResult:
        self.requests.append(request)
        return CodeAgentExplainResult(answer="Réponse simple.")


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_ha_explain_workflow_returns_run_id_and_persists_followup(tmp_path: Path) -> None:
    collector = FakeContextCollector()
    workflow = HaExplainWorkflow(
        store=WorkflowStore(tmp_path),
        graph_factory=HaExplainGraphFactory(
            context_collector=collector,  # type: ignore[arg-type]
            code_agent=MockCodeAgentCapability(),
        ),
    )

    first = await workflow.ask("Pourquoi les lumieres du salon s'allument toutes seules ?")
    second = await workflow.ask("Et le capteur sert a quoi ?", run_id=first.run_id)

    assert first.run_id == second.run_id
    assert "packages/areas/salon.yaml" in second.referenced_files
    assert collector.previous_files_seen == ["packages/areas/salon.yaml"]


def test_repo_context_finds_ha_package_candidates(tmp_path: Path) -> None:
    salon = tmp_path / "packages/areas/salon.yaml"
    lights = tmp_path / "packages/functions/lights.yaml"
    salon.parent.mkdir(parents=True)
    lights.parent.mkdir(parents=True)
    salon.write_text("automation: []", encoding="utf-8")
    lights.write_text("adaptive_lighting: []", encoding="utf-8")

    context = RepoContextCapability(tmp_path)

    assert context.find_ha_package_candidates("lumières salon") == [
        "packages/areas/salon.yaml",
        "packages/functions/lights.yaml",
    ]


def test_infer_answer_style_defaults_to_user_friendly() -> None:
    assert infer_answer_style("Pourquoi les lampes s'allument dans le salon ?") == "default"


def test_infer_answer_style_detects_expert_request() -> None:
    assert (
        infer_answer_style(
            "Explique pourquoi les lampes s'allument en donnant les détails de configuration"
        )
        == "expert"
    )


@pytest.mark.anyio
async def test_ha_explain_workflow_passes_answer_style_to_code_agent(tmp_path: Path) -> None:
    agent = CapturingCodeAgent()
    workflow = HaExplainWorkflow(
        store=WorkflowStore(tmp_path),
        graph_factory=HaExplainGraphFactory(
            context_collector=FakeContextCollector(),  # type: ignore[arg-type]
            code_agent=agent,
        ),
    )

    await workflow.ask("Pourquoi les lampes s'allument dans le salon ?")
    await workflow.ask("Donne les détails de configuration")

    assert agent.requests[0].context["answer_style"] == "default"
    assert agent.requests[1].context["answer_style"] == "expert"
