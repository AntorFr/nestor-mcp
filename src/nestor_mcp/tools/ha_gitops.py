from mcp.server.fastmcp import FastMCP

from nestor_mcp.models.ha_change import HaChangeConfirmationResult, HaChangeProposal
from nestor_mcp.services.ha_change_service import HaChangeService
from nestor_mcp.services.home_assistant import HomeAssistantService
from nestor_mcp.services.proposal_store import ProposalStore
from nestor_mcp.workflows.ha_explain.models import HaExplainResponse
from nestor_mcp.workflows.ha_explain.workflow import HaExplainWorkflow


def register_ha_gitops_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    async def ha_config_context() -> str:
        """
        Return a compact read-only summary of the Home Assistant inventory. Do not
        use this to inspect all entities in detail; for behavior explanations use
        explain_smart_home_behavior, and for configuration changes use
        draft_home_assistant_change.
        """
        inventory = await HomeAssistantService().get_inventory()
        domains: dict[str, int] = {}
        for entity in inventory.entities:
            domain = entity.entity_id.split(".", 1)[0]
            domains[domain] = domains.get(domain, 0) + 1
        domain_summary = ", ".join(
            f"{domain}: {count}" for domain, count in sorted(domains.items())[:20]
        )
        return (
            f"Home Assistant inventory: {len(inventory.entities)} entities, "
            f"{len(inventory.services)} service domains. Entity domains: {domain_summary}. "
            "Use dedicated Nestor tools for detailed analysis or GitOps changes."
        )

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
        commit_message: str | None = None,
    ) -> HaChangeProposal:
        """
        Use this when the user asks to change, add, remove or fix a Home Assistant
        automation, script, helper, package or YAML configuration. This drafts a
        GitOps proposal only: it may ask clarification questions, prepares file
        changes with the configured code agent, validates YAML and Home Assistant
        references, then waits for explicit user confirmation before any branch,
        push or pull request is created. Pass only the user's requested behavior;
        do not invent YAML content or file paths in the tool arguments.
        """
        return await HaChangeService().draft_change(
            user_request=user_request,
            commit_message=commit_message,
            accept_supplied_content=False,
        )

    @mcp.tool()
    def confirm_home_assistant_change(proposal_id: str) -> HaChangeConfirmationResult:
        """
        Use this only after the user explicitly approves a Home Assistant change
        proposal. It pushes the prepared changes to a Git branch and opens a pull
        request to the configured main branch. Never call this for a first request
        or without explicit approval.
        """
        return HaChangeService().confirm_change(proposal_id)

    @mcp.tool()
    async def answer_home_assistant_change_question(
        proposal_id: str,
        answer: str,
    ) -> HaChangeProposal:
        """
        Use this when Nestor previously asked a clarification question about a
        Home Assistant change proposal. Provide the proposal_id and the user's
        answer. Nestor will update the same proposal, ask more questions if still
        ambiguous, or prepare validated changes waiting for explicit approval.
        """
        return await HaChangeService().answer_clarification(proposal_id, answer)

    @mcp.tool()
    def get_home_assistant_change_status(proposal_id: str) -> HaChangeProposal:
        """Get the current status of a drafted Home Assistant GitOps change."""
        return ProposalStore().get(proposal_id)

    @mcp.tool()
    async def propose_home_assistant_change(
        user_request: str,
        commit_message: str | None = None,
    ) -> HaChangeProposal:
        """Backward-compatible alias for drafting a Home Assistant GitOps change."""
        return await HaChangeService().draft_change(
            user_request=user_request,
            commit_message=commit_message,
            accept_supplied_content=False,
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
