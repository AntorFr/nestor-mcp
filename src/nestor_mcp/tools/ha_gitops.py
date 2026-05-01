from mcp.server.fastmcp import FastMCP

from nestor_mcp.models.ha_change import HaChangeConfirmationResult, HaChangeProposal
from nestor_mcp.models.home_assistant import HaInventory
from nestor_mcp.services.ha_change_service import HaChangeService
from nestor_mcp.services.home_assistant import HomeAssistantService
from nestor_mcp.services.proposal_store import ProposalStore
from nestor_mcp.workflows.ha_explain.models import HaExplainResponse
from nestor_mcp.workflows.ha_explain.workflow import HaExplainWorkflow


def register_ha_gitops_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def ha_config_context() -> HaInventory:
        """Read Home Assistant entities, services and config without writing to production."""
        return await HomeAssistantService().get_inventory()

    @mcp.tool()
    async def explain_smart_home_behavior(
        question: str,
        run_id: str | None = None,
    ) -> str:
        """
        Use this when the user asks why something happens in their smart home or
        Home Assistant setup. Examples: why lights turn on or off by themselves,
        why an automation or script runs, why a sensor changes state, why a room
        behaves unexpectedly, or how a routine works. This tool inspects the real
        Home Assistant configuration, current entities and repository files, then
        explains the behavior in user-friendly French. Use follow-up questions with
        the same run_id when the user asks for more detail about the same topic.
        """
        response = await HaExplainWorkflow().ask(question=question, run_id=run_id)
        return format_ha_explain_tool_response(response)

    @mcp.tool()
    async def explain_home_assistant_config(
        question: str,
        run_id: str | None = None,
    ) -> str:
        """
        Use this for technical questions about the real Home Assistant
        configuration, automations, scripts, entities, YAML packages or repository
        files. Prefer explain_smart_home_behavior for normal user questions like
        "why do the living room lights turn on by themselves?".
        """
        return await explain_smart_home_behavior(question=question, run_id=run_id)

    @mcp.tool()
    async def draft_home_assistant_change(
        user_request: str,
        path: str | None = None,
        content: str | None = None,
        commit_message: str | None = None,
    ) -> HaChangeProposal:
        """Draft a GitOps Home Assistant change and ask clarification questions if needed."""
        return await HaChangeService().draft_change(
            user_request=user_request,
            path=path,
            content=content,
            commit_message=commit_message,
        )

    @mcp.tool()
    def confirm_home_assistant_change(proposal_id: str) -> HaChangeConfirmationResult:
        """After explicit user approval, push a branch and open a PR to master."""
        return HaChangeService().confirm_change(proposal_id)

    @mcp.tool()
    def get_home_assistant_change_status(proposal_id: str) -> HaChangeProposal:
        """Get the current status of a drafted Home Assistant GitOps change."""
        return ProposalStore().get(proposal_id)

    @mcp.tool()
    async def propose_home_assistant_change(
        user_request: str,
        path: str | None = None,
        content: str | None = None,
        commit_message: str | None = None,
    ) -> HaChangeProposal:
        """Backward-compatible alias for drafting a Home Assistant GitOps change."""
        return await HaChangeService().draft_change(
            user_request=user_request,
            path=path,
            content=content,
            commit_message=commit_message,
        )


def format_ha_explain_tool_response(response: HaExplainResponse) -> str:
    lines = [response.answer]
    if response.follow_up_suggestions:
        lines.append("")
        lines.append("Questions de suivi possibles :")
        lines.extend(f"- {suggestion}" for suggestion in response.follow_up_suggestions[:3])
    lines.append("")
    lines.append(f"Référence de conversation Nestor : {response.run_id}")
    return "\n".join(lines)
