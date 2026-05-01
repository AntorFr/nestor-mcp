# Implementation Rails

These rules guide future implementation so Nestor remains general, secure, and maintainable.

## 1. Expose Business Tools, Not Technical Tools

MCP tools exposed to Assist should be user-intent oriented:

- `propose_home_assistant_change`
- `schedule_appointment`
- `create_household_task`
- `summarize_newsletter`

Avoid exposing raw provider operations directly to Assist unless they are safe and genuinely useful.

## 2. Keep Tools Thin

Tool functions should:

- parse tool arguments
- call a workflow or service
- return structured Pydantic models

Tool functions should not contain multi-step orchestration logic.

## 3. Model Long Tasks As Workflows

Use `orchestration.WorkflowRun` for anything that can need:

- follow-up questions
- user confirmation
- external side effects
- retry/recovery
- multi-step context collection

Simple read-only lookups can stay as direct services.

## 4. Use Providers Behind Contracts

Every external capability should sit behind an interface:

- code/config agent -> `CodeAgentCapability`
- isolated repository/file work -> workspace capability
- web lookup/summarization -> web research capability
- calendar -> `CalendarConnector`
- tasks -> `TaskConnector`
- n8n -> `N8nConnector`
- future MCP clients -> connector interfaces

Start with mock providers in tests. Add real providers only once the contract is stable.

## 5. Never Give Agents Raw Authority

Specialized agents must not receive:

- GitHub write tokens
- Home Assistant write tokens
- calendar write credentials
- telephony credentials
- unrestricted filesystem access

They may receive sanitized context and work in temporary/sandboxed workspaces. Nestor validates their proposed output and applies side effects itself.

## 6. Validate Before Confirmation

Before asking the user to confirm a side effect, workflows should run deterministic validation.

For Home Assistant GitOps:

- protected path checks
- YAML parse
- entity references against HA inventory when available
- service references against HA services when available
- no secrets or credentials

For calendar/todo:

- required fields
- timezone
- duplicate/conflict checks when possible
- permission checks

For phone calls:

- explicit consent
- allowed identity/information policy
- no financial or sensitive commitment without escalation

## 7. Confirmation Must Be Explicit

Do not infer confirmation from vague agreement.

Accepted examples:

- "ok cree la PR"
- "oui confirme le rendez-vous"
- "vas-y cree l'evenement"

Rejected examples:

- "ca a l'air bien"
- "peut-etre"
- "continue"

## 8. Persist State Early

Any workflow that can pause must persist:

- original user request
- context used
- pending questions
- proposed actions
- validation results
- confirmation state
- final external IDs such as PR URL or calendar event ID

## 9. Make Side Effects Idempotent

Every side-effecting step must tolerate retries.

Examples:

- branch names include run id
- PR creation checks whether a PR already exists
- event/task creation stores provider IDs
- connector calls use idempotency keys when supported

## 10. First HA GitOps Use Case

The first implementation should not hardcode request types.

Build this sequence:

1. `start_ha_gitops_change`
   - fetch persistent repo clone
   - collect Home Assistant inventory
   - infer candidate package files
   - send context to `CodeAgentCapability`

2. If agent returns questions:
   - store run as `needs_user_input`
   - return questions to Assist

3. If agent returns files:
   - validate proposed changes
   - store run as `awaiting_confirmation`
   - return summary and diff

4. `resume_ha_gitops_change`
   - pass user answers back to the code agent
   - repeat until proposed changes or failure

5. `confirm_ha_gitops_change`
   - revalidate
   - create branch
   - commit
   - push
   - open PR to `master`

## 11. Add Shared Capabilities Before Special Cases

If two workflows need the same behavior, implement it as a capability before embedding it in a workflow.

Examples:

- web research belongs in `capabilities/web_research`, not in newsletter only
- repo sandboxing/diff extraction belongs in `capabilities/workspace`, not in HA only
- code/config editing belongs in `capabilities/code_agent`, not in HA only

Workflows compose capabilities. They should not become utility libraries.

## 12. HA Explain Workflow

The read-only Home Assistant explanation workflow is the first LangGraph workflow.

It must:

- update the persistent GitOps clone before collecting repo context
- read Home Assistant only through read-only APIs
- call `LlmCapability.explain`
- support follow-up questions through the same `run_id`
- persist conversation history in `WorkflowStore`
- never write files, push branches, open PRs, or call Home Assistant write APIs

Default local provider is `HA_EXPLAIN_PROVIDER=mock`.

For Assist, use a low-latency direct LLM provider:

```env
HA_EXPLAIN_PROVIDER=anthropic_api
HA_EXPLAIN_MODEL=claude-haiku-4-5-20251001
HA_EXPLAIN_TIMEOUT_SECONDS=20
ANTHROPIC_API_KEY=...
```

The provider is expected to return JSON with:

- `answer`
- `referenced_files`
- `referenced_entities`
- `follow_up_suggestions`

Claude Code remains reserved for workflows that need code/config editing, such as HA GitOps.
