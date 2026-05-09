from pathlib import Path

import pytest

from nestor_mcp.capabilities.code_agent.models import CodeAgentFile
from nestor_mcp.capabilities.llm.capability import LlmCapability
from nestor_mcp.capabilities.llm.models import LlmExplainRequest, LlmExplainResult
from nestor_mcp.capabilities.llm.providers import MockLlmCapability
from nestor_mcp.capabilities.workspace.file_selector import FileCandidate
from nestor_mcp.capabilities.workspace.ha_doc_index import DocMatch, HaDoc
from nestor_mcp.capabilities.workspace.ha_retriever import HaRetriever
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


class _RecordingSelector:
    def __init__(self, paths: list[str] | None = None) -> None:
        self.paths = paths
        self.calls: list[list[FileCandidate]] = []

    async def select(
        self, question: str, candidates: list[FileCandidate], max_files: int
    ) -> list[str]:
        self.calls.append(list(candidates))
        if self.paths is None:
            return [c.path for c in candidates[:max_files]]
        return [p for p in self.paths if p in {c.path for c in candidates}][:max_files]


@pytest.mark.anyio
async def test_retriever_matches_function_id_directly(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "packages/functions/portail.yaml",
        "automation:\n- id: function_portail_sonette\n  alias: Portail - Sonette\n",
    )
    selector = _RecordingSelector()
    retriever = HaRetriever(tmp_path, file_selector=selector)
    assert await retriever.retrieve("Que fait function_portail_sonette ?") == [
        "packages/functions/portail.yaml"
    ]


@pytest.mark.anyio
async def test_retriever_passes_embedding_hits_to_selector(tmp_path: Path) -> None:
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
    fake_ranker = _FakeRanker(target_path="docs/fonctions/portail.md")
    selector = _RecordingSelector(paths=["docs/fonctions/portail.md"])
    retriever = HaRetriever(
        tmp_path, embedding_ranker=fake_ranker, file_selector=selector
    )

    candidates = await retriever.retrieve("Le truc qui fait ding-dong en bas")

    assert fake_ranker.calls == 1
    assert selector.calls, "selector must be invoked"
    seen_paths = {c.path for c in selector.calls[0]}
    assert "docs/fonctions/portail.md" in seen_paths
    # Selected doc had a <!-- source: --> tag pointing at the YAML, so the
    # retriever expands the link automatically.
    assert candidates == [
        "docs/fonctions/portail.md",
        "packages/functions/portail.yaml",
    ]


@pytest.mark.anyio
async def test_retriever_falls_back_to_head_when_selector_returns_empty(
    tmp_path: Path,
) -> None:
    _write(
        tmp_path,
        "packages/functions/portail.yaml",
        "automation:\n- id: function_portail_sonette\n",
    )
    fake_ranker = _FakeRanker(target_path="packages/functions/portail.yaml")
    # Doc-less candidate so embedding ranker still produces something.
    _write(tmp_path, "docs/fonctions/portail.md", "# Portail\n")
    fake_ranker.target_path = "docs/fonctions/portail.md"
    selector = _RecordingSelector(paths=[])  # selector "rejects" everything
    retriever = HaRetriever(
        tmp_path, embedding_ranker=fake_ranker, file_selector=selector
    )

    candidates = await retriever.retrieve("Question sans rapport")

    assert candidates  # head fallback engaged
    assert "docs/fonctions/portail.md" in candidates


@pytest.mark.anyio
async def test_retriever_falls_back_to_previous_files_when_nothing_matches(
    tmp_path: Path,
) -> None:
    _write(tmp_path, "packages/areas/salon.yaml", "automation: []\n")
    retriever = HaRetriever(tmp_path)
    assert await retriever.retrieve(
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
