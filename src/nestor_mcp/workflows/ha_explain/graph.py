from typing import Any, TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, StateGraph

from nestor_mcp.capabilities.code_agent.capability import CodeAgentCapability
from nestor_mcp.capabilities.code_agent.models import CodeAgentExplainRequest
from nestor_mcp.capabilities.code_agent.providers import get_code_agent_capability
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
        code_agent: CodeAgentCapability | None = None,
    ) -> None:
        self.context_collector = context_collector or HaExplainContextCollector()
        self.code_agent = code_agent

    def build(self):
        graph = StateGraph(HaExplainState)
        graph.add_node("collect_context", self.collect_context)
        graph.add_node("call_code_agent", self.call_code_agent)
        graph.set_entry_point("collect_context")
        graph.add_edge("collect_context", "call_code_agent")
        graph.add_edge("call_code_agent", END)
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

    async def call_code_agent(self, state: HaExplainState) -> HaExplainState:
        agent = self.code_agent or get_code_agent_capability()
        result = await agent.explain_config(
            CodeAgentExplainRequest(
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
