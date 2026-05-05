from pathlib import Path

import pytest

from nestor_mcp.capabilities.code_agent.models import CodeAgentFile
from nestor_mcp.capabilities.llm.capability import LlmCapability
from nestor_mcp.capabilities.llm.models import LlmExplainRequest, LlmExplainResult
from nestor_mcp.capabilities.llm.providers import MockLlmCapability
from nestor_mcp.capabilities.workspace.ha_doc_index import DocMatch, HaDoc
from nestor_mcp.capabilities.workspace.ha_retriever import HaRetriever
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


class CapturingLlm(LlmCapability):
    def __init__(self) -> None:
        self.requests: list[LlmExplainRequest] = []

    async def explain(self, request: LlmExplainRequest) -> LlmExplainResult:
        self.requests.append(request)
        return LlmExplainResult(answer="Réponse simple.")


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
            llm=MockLlmCapability(),
        ),
    )

    first = await workflow.ask("Pourquoi les lumieres du salon s'allument toutes seules ?")
    second = await workflow.ask("Et le capteur sert a quoi ?", run_id=first.run_id)

    assert first.run_id == second.run_id
    assert "packages/areas/salon.yaml" in second.referenced_files
    assert collector.previous_files_seen == ["packages/areas/salon.yaml"]


def _write(repo: Path, rel: str, content: str) -> None:
    target = repo / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def test_retriever_matches_function_id_directly(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "packages/functions/portail.yaml",
        "automation:\n- id: function_portail_sonette\n  alias: Portail - Sonette\n",
    )
    context = RepoContextCapability(tmp_path)
    assert context.find_ha_package_candidates(
        "Que fait function_portail_sonette ?"
    ) == ["packages/functions/portail.yaml"]


def test_retriever_uses_doc_with_aliases(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "packages/functions/portail.yaml",
        "automation:\n- id: function_portail_sonette\n  alias: Sonette\n",
    )
    _write(
        tmp_path,
        "docs/fonctions/portail.md",
        "---\naliases: [sonette, carillon]\n---\n# Portail\n\n"
        "<!-- source: automation:function_portail_sonette -->\n",
    )
    context = RepoContextCapability(tmp_path)
    candidates = context.find_ha_package_candidates("Comment marche la sonette ?")
    assert "docs/fonctions/portail.md" in candidates
    assert "packages/functions/portail.yaml" in candidates


def test_retriever_unions_multiple_doc_matches(tmp_path: Path) -> None:
    _write(tmp_path, "packages/functions/lights.yaml", "automation:\n- id: lights_main\n")
    _write(
        tmp_path,
        "packages/functions/vacances.yaml",
        "automation:\n- id: vacances_scolaires\n",
    )
    _write(
        tmp_path,
        "docs/fonctions/eclairage.md",
        "# Eclairage\n<!-- source: automation:lights_main -->\n",
    )
    _write(
        tmp_path,
        "docs/fonctions/vacances-scolaires.md",
        "# Vacances scolaires\n<!-- source: automation:vacances_scolaires -->\n",
    )
    context = RepoContextCapability(tmp_path)
    candidates = context.find_ha_package_candidates(
        "Comment l'eclairage change pendant les vacances scolaires ?"
    )
    assert "docs/fonctions/eclairage.md" in candidates
    assert "docs/fonctions/vacances-scolaires.md" in candidates
    assert "packages/functions/lights.yaml" in candidates
    assert "packages/functions/vacances.yaml" in candidates


class _FakeRanker:
    def __init__(self, target_path: str) -> None:
        self.target_path = target_path
        self.calls = 0

    def rank(self, question: str, docs: list[HaDoc], top_k: int) -> list[DocMatch]:
        self.calls += 1
        for doc in docs:
            if doc.path == self.target_path:
                return [DocMatch(doc=doc, score=0.9)]
        return []


def test_retriever_uses_embedding_fallback_when_lexical_is_weak(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "packages/functions/portail.yaml",
        "automation:\n- id: function_portail_sonette\n",
    )
    _write(
        tmp_path,
        "docs/fonctions/portail.md",
        "# Portail\n<!-- source: automation:function_portail_sonette -->\n",
    )
    fake = _FakeRanker(target_path="docs/fonctions/portail.md")
    retriever = HaRetriever(tmp_path, embedding_ranker=fake, lexical_threshold=100.0)

    # Question with no lexical overlap with title/stem/aliases/body.
    candidates = retriever.retrieve("Le truc qui fait ding-dong en bas")

    assert fake.calls == 1
    assert "docs/fonctions/portail.md" in candidates
    assert "packages/functions/portail.yaml" in candidates


def test_retriever_skips_embedding_when_lexical_is_strong(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "docs/fonctions/portail.md",
        "---\naliases: [sonette, carillon]\n---\n# Portail sonette\n",
    )
    fake = _FakeRanker(target_path="docs/fonctions/portail.md")
    retriever = HaRetriever(tmp_path, embedding_ranker=fake, lexical_threshold=2.0)

    retriever.retrieve("Comment marche le portail sonette ?")

    assert fake.calls == 0


def test_retriever_falls_back_to_previous_files_when_nothing_matches(tmp_path: Path) -> None:
    _write(tmp_path, "packages/areas/salon.yaml", "automation: []\n")
    context = RepoContextCapability(tmp_path)
    assert context.find_ha_package_candidates(
        "??",
        previous_files=["packages/areas/salon.yaml"],
    ) == ["packages/areas/salon.yaml"]


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
async def test_ha_explain_workflow_passes_answer_style_to_llm(tmp_path: Path) -> None:
    llm = CapturingLlm()
    workflow = HaExplainWorkflow(
        store=WorkflowStore(tmp_path),
        graph_factory=HaExplainGraphFactory(
            context_collector=FakeContextCollector(),  # type: ignore[arg-type]
            llm=llm,
        ),
    )

    await workflow.ask("Pourquoi les lampes s'allument dans le salon ?")
    await workflow.ask("Donne les détails de configuration")

    assert llm.requests[0].context["answer_style"] == "default"
    assert llm.requests[1].context["answer_style"] == "expert"
