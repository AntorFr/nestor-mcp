import asyncio
import logging

from mcp.server.fastmcp import FastMCP

from nestor_mcp.config import get_settings
from nestor_mcp.models.ha_change import (
    HaChangeCancellationResult,
    HaChangeConfirmationResult,
    HaChangeProposal,
    HaChangeProposalList,
    HaChangeProposalStatus,
)
from nestor_mcp.services.ha_change_service import HaChangeService
from nestor_mcp.services.home_assistant import HomeAssistantService
from nestor_mcp.workflows.ha_explain.models import HaExplainResponse
from nestor_mcp.workflows.ha_explain.workflow import HaExplainWorkflow

logger = logging.getLogger(__name__)
_BACKGROUND_DRAFT_TASKS: dict[str, asyncio.Task] = {}


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
        GitOps proposal only. It returns quickly with a proposal_id while Nestor
        prepares file changes asynchronously with the configured code agent. The
        user or assistant should call get_home_assistant_change_status with that
        proposal_id after a few seconds. Nestor waits for explicit user
        confirmation before any branch, push or pull request is created. Pass only
        the user's requested behavior; do not invent YAML content or file paths in
        the tool arguments.
        """
        service = HaChangeService()
        proposal = service.start_draft_change(
            user_request=user_request,
            commit_message=commit_message,
        )
        if proposal.status != HaChangeProposalStatus.drafting:
            return proposal
        task = schedule_background_draft_completion(proposal.id)
        timeout = get_settings().ha_gitops_assist_timeout_seconds
        if timeout > 0:
            try:
                return await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
            except TimeoutError:
                pass
        return proposal

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
    async def get_home_assistant_change_status(proposal_id: str = "current") -> HaChangeProposal:
        """
        Get details for one specific Home Assistant GitOps change proposal.
        Use this only when the user provides a concrete proposal_id returned by
        Nestor, or immediately after draft_home_assistant_change returns a
        proposal_id with status drafting. Do not use this to answer broad
        questions like "are there changes in progress?", "list pending changes",
        "open requests" or "modifications en cours"; use
        list_home_assistant_changes for those list/overview questions. The
        fallback proposal_id values "current", "latest", "active", "open",
        "pending", "ongoing" or "in_progress" return the most recently updated
        active or confirmed proposal only as a compatibility fallback.
        """
        service = HaChangeService()
        proposal = service.get_change_status(proposal_id)
        if proposal.status == HaChangeProposalStatus.drafting and (
            not is_background_draft_running(proposal.id) or service.is_stale_draft(proposal)
        ):
            schedule_background_draft_completion(proposal.id)
        return proposal

    @mcp.tool()
    async def list_home_assistant_changes() -> HaChangeProposalList:
        """
        List all current Home Assistant GitOps change proposals known by Nestor.
        Always use this tool, not get_home_assistant_change_status, when the user
        asks whether there are changes in progress, pending changes, open
        requests, unconfirmed proposals, PR proposals, or "demandes/modifications
        en cours". The result includes drafts, proposals waiting for
        clarification, proposals waiting for confirmation, and recently created
        PRs.
        """
        service = HaChangeService()
        proposals = []
        for proposal in service.list_reusable_proposals():
            refreshed = service.get_change_status(proposal.id)
            if refreshed.status == HaChangeProposalStatus.drafting and (
                not is_background_draft_running(refreshed.id) or service.is_stale_draft(refreshed)
            ):
                schedule_background_draft_completion(refreshed.id)
            proposals.append(refreshed)
        return HaChangeProposalList(proposals=proposals, count=len(proposals))

    @mcp.tool()
    def cancel_home_assistant_change(proposal_id: str) -> HaChangeCancellationResult:
        """
        Cancel a Home Assistant GitOps change proposal that the user no longer
        wants, but only before a pull request has been created. Use this when the
        user asks to cancel, abandon, reject or forget a pending Home Assistant
        change proposal. Do not use it for proposals with an existing PR; those
        must be closed in GitHub review.
        """
        cancel_background_draft_completion(proposal_id)
        proposal = HaChangeService().cancel_change(proposal_id)
        return HaChangeCancellationResult(
            proposal_id=proposal.id,
            status=proposal.status,
            message="Proposition Home Assistant annulée. Aucune branche ni PR n'a été créée.",
        )

    @mcp.tool()
    async def propose_home_assistant_change(
        user_request: str,
        commit_message: str | None = None,
    ) -> HaChangeProposal:
        """Backward-compatible alias for drafting a Home Assistant GitOps change."""
        return await draft_home_assistant_change(
            user_request=user_request,
            commit_message=commit_message,
        )


def schedule_background_draft_completion(proposal_id: str) -> asyncio.Task:
    existing = _BACKGROUND_DRAFT_TASKS.get(proposal_id)
    if existing and not existing.done():
        return existing
    task = asyncio.create_task(HaChangeService().complete_draft_change(proposal_id))
    _BACKGROUND_DRAFT_TASKS[proposal_id] = task
    task.add_done_callback(lambda done_task: _handle_background_draft_done(proposal_id, done_task))
    return task


def is_background_draft_running(proposal_id: str) -> bool:
    existing = _BACKGROUND_DRAFT_TASKS.get(proposal_id)
    return bool(existing and not existing.done())


def cancel_background_draft_completion(proposal_id: str) -> bool:
    task = _BACKGROUND_DRAFT_TASKS.pop(proposal_id, None)
    if not task or task.done():
        return False
    task.cancel()
    return True


def _handle_background_draft_done(proposal_id: str, task: asyncio.Task) -> None:
    if _BACKGROUND_DRAFT_TASKS.get(proposal_id) is task:
        _BACKGROUND_DRAFT_TASKS.pop(proposal_id, None)
    try:
        task.result()
    except Exception:
        logger.exception("Background HA change draft task failed")


def format_ha_explain_tool_response(response: HaExplainResponse) -> str:
    lines = [response.answer]
    if response.follow_up_suggestions:
        lines.append("")
        lines.append("Questions de suivi possibles :")
        lines.extend(f"- {suggestion}" for suggestion in response.follow_up_suggestions[:3])
    lines.append("")
    lines.append(f"Référence de conversation Nestor : {response.run_id}")
    return "\n".join(lines)
