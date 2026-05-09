from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from nestor_mcp.capabilities.llm.capability import LlmCapability
from nestor_mcp.capabilities.llm.models import LlmExplainRequest
from nestor_mcp.capabilities.llm.providers import get_llm_capability
from nestor_mcp.workflows.ha_explain.context import HaExplainContextCollector

EXPERT_DETAIL_KEYWORDS = (
    "configuration",
    "config",
    "yaml",
    "fichier",
    "fichiers",
    "entité",
    "entités",
    "entity",
    "id",
    "identifiant",
    "automation",
    "automatisation",
    "blueprint",
    "script",
    "détail",
    "détails",
    "detail",
    "details",
    "technique",
    "debug",
)


class HaExplainState(TypedDict, total=False):
    run_id: str
    question: str
    history: list[dict[str, str]]
    previous_files: list[str]
    files: list[dict[str, str]]
    ha_entities: list[dict[str, Any]]
    answer: str
    referenced_files: list[str]
    referenced_entities: list[str]
    follow_up_suggestions: list[str]


class HaExplainGraphFactory:
    def __init__(
        self,
        context_collector: HaExplainContextCollector | None = None,
        llm: LlmCapability | None = None,
    ) -> None:
        self.context_collector = context_collector or HaExplainContextCollector()
        self.llm = llm

    def build(self):
        graph = StateGraph(HaExplainState)
        graph.add_node("collect_context", self.collect_context)
        graph.add_node("call_llm", self.call_llm)
        graph.set_entry_point("collect_context")
        graph.add_edge("collect_context", "call_llm")
        graph.add_edge("call_llm", END)
        return graph.compile(checkpointer=InMemorySaver())

    async def collect_context(self, state: HaExplainState) -> HaExplainState:
        files, entities = await self.context_collector.collect(
            question=state["question"],
            previous_files=state.get("previous_files", []),
        )
        return {
            "files": [file.model_dump() for file in files],
            "ha_entities": entities,
        }

    async def call_llm(self, state: HaExplainState) -> HaExplainState:
        llm = self.llm or get_llm_capability("ha_explain")
        result = await llm.explain(
            LlmExplainRequest(
                run_id=state["run_id"],
                question=state["question"],
                instructions=HA_EXPLAIN_INSTRUCTIONS,
                context={
                    "answer_style": infer_answer_style(state["question"]),
                    "ha_entities": state.get("ha_entities", []),
                },
                files=state.get("files", []),
                history=state.get("history", []),
            )
        )
        return {
            "answer": result.answer,
            "referenced_files": result.referenced_files,
            "referenced_entities": result.referenced_entities,
            "follow_up_suggestions": result.follow_up_suggestions,
        }


def infer_answer_style(question: str) -> str:
    normalized = question.casefold()
    if any(keyword in normalized for keyword in EXPERT_DETAIL_KEYWORDS):
        return "expert"
    return "default"


HA_EXPLAIN_INSTRUCTIONS = """
Tu expliques une configuration Home Assistant existante en français.
Tu travailles en lecture seule.
Tu dois t'appuyer uniquement sur les fichiers et l'inventaire fournis.

Avant de rédiger, parcours TOUS les fichiers fournis et inventorie chaque
automatisation, scène, script ou règle qui touche au sujet de la question.
La réponse doit couvrir l'ENSEMBLE des règles trouvées (départ, retour,
soirée, nuit, soleil, modes spéciaux, etc.), pas seulement le premier cas
rencontré. Si plusieurs fichiers décrivent des règles distinctes sur le
même thème, mentionne-les toutes (chacune brièvement) en indiquant ce qui
les déclenche.

Si la question est un follow-up, utilise l'historique et les fichiers déjà référencés.
Adapte le niveau de détail à context.answer_style:
- default: réponds pour une personne qui ne connaît pas Home Assistant ni la configuration.
  Explique la cause en langage naturel, sans citer les chemins de fichiers, les IDs d'entités,
  les noms internes d'automatisation, le YAML ou les blueprints. Traduis les identifiants en
  noms compréhensibles comme "les détecteurs de présence du salon", "la luminosité", "le mode TV".
  Reste court, concret et orienté utilisateur.
- expert: tu peux citer les chemins de fichiers, IDs d'entités, noms d'automatisations,
  conditions, déclencheurs, actions, YAML et blueprints si cela aide.
Dans tous les cas, renseigne referenced_files et referenced_entities avec les références techniques
utilisées, même si tu ne les mentionnes pas dans la réponse par défaut.
Ne propose pas de modification de configuration dans ce workflow.
"""
