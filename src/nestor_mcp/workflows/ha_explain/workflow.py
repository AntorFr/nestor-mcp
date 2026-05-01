from uuid import uuid4

from langchain_core.runnables import RunnableConfig

from nestor_mcp.orchestration.state import WorkflowRun, WorkflowStatus
from nestor_mcp.orchestration.store import WorkflowStore
from nestor_mcp.workflows.ha_explain.graph import HaExplainGraphFactory
from nestor_mcp.workflows.ha_explain.models import HaExplainResponse


class HaExplainWorkflow:
    name = "ha_explain"

    def __init__(
        self,
        store: WorkflowStore | None = None,
        graph_factory: HaExplainGraphFactory | None = None,
    ) -> None:
        self.store = store or WorkflowStore()
        self.graph = (graph_factory or HaExplainGraphFactory()).build()

    async def ask(self, question: str, run_id: str | None = None) -> HaExplainResponse:
        run = self.load_or_create_run(question, run_id)
        history = list(run.context.get("history", []))
        previous_files = list(run.context.get("referenced_files", []))
        state = {
            "run_id": run.id,
            "question": question,
            "history": history,
            "previous_files": previous_files,
        }
        result = await self.graph.ainvoke(
            state,
            config=RunnableConfig(configurable={"thread_id": run.id}),
        )
        response = HaExplainResponse(
            run_id=run.id,
            status=WorkflowStatus.completed,
            answer=result.get("answer", ""),
            referenced_files=result.get("referenced_files", []),
            referenced_entities=result.get("referenced_entities", []),
            follow_up_suggestions=result.get("follow_up_suggestions", []),
        )

        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": response.answer})
        updated = run.model_copy(
            update={
                "status": WorkflowStatus.completed,
                "context": {
                    **run.context,
                    "history": history,
                    "referenced_files": response.referenced_files,
                    "referenced_entities": response.referenced_entities,
                },
                "result": response.model_dump(),
            }
        )
        self.store.save(updated)
        return response

    def load_or_create_run(self, question: str, run_id: str | None) -> WorkflowRun:
        if run_id:
            return self.store.get(run_id)

        new_run = WorkflowRun(
            id=f"haexp_{uuid4()}",
            workflow_name=self.name,
            status=WorkflowStatus.running,
            input={"question": question},
        )
        self.store.save(new_run)
        return new_run
