# Nestor MCP Architecture

`nestor-mcp` is the orchestration boundary between Home Assistant Assist and specialized systems.

Home Assistant Assist should call high-level Nestor tools. Nestor may call external MCP servers, n8n webhooks, code agents, APIs, or local services, but those systems must not bypass Nestor's policy and validation layer.

## Core Responsibilities

Nestor owns:

- workflow orchestration
- state persistence
- user questions and confirmations
- policy enforcement
- validation
- context collection
- connector routing
- audit-friendly result summaries

Nestor does not own:

- every third-party API implementation
- raw calendar or todo provider logic when a dedicated MCP/n8n connector can do it
- unrestricted autonomous side effects
- code generation heuristics hardcoded per Home Assistant request type

## Layering

```text
Home Assistant Assist
  calls high-level tools
nestor-mcp
  orchestrates workflows and applies policy
external providers
  code agents, n8n, MCP connectors, GitHub, Home Assistant APIs
```

## Packages

```text
capabilities/
  Reusable cross-workflow capabilities: code agents, web research, workspaces,
  approvals, memory, notifications.

orchestration/
  Generic workflow primitives: run state, store, workflow interface.

agents/
  Low-level provider adapters for specialized agents when needed.

connectors/
  External connector contracts and adapters: calendar, task, n8n, future MCP clients.

workflows/
  Use-case workflows: HA GitOps, phone appointments, calendar planning, newsletter, tasks.

services/
  Deterministic domain services and external API wrappers.

tools/
  MCP tool registration. Tools should be thin and call workflows/services.

security/
  Policies and validators. All side effects pass through here.
```

## Dependency Rule

Dependencies must flow in one direction:

```text
tools -> workflows -> capabilities -> connectors/services
```

Avoid these dependencies:

```text
connectors -> workflows
capabilities -> workflows
workflow A -> workflow B directly
```

If a workflow must trigger another workflow, it should go through the orchestration layer.

## Capabilities vs Connectors

Capabilities are reusable Nestor abilities with policy-aware contracts.

Examples:

- code/config agent capability
- workspace capability
- web research capability
- approval capability
- notification capability

Connectors are low-level adapters to concrete systems.

Examples:

- GitHub API
- Home Assistant API
- n8n webhook
- Google Calendar
- Todoist
- search provider

Workflows should usually depend on capabilities. Capabilities may depend on connectors.

## Side Effect Rule

Sub-agents propose. Nestor disposes.

Specialized agents may inspect a sandboxed workspace and return questions or proposed changes. They must not receive production write credentials such as GitHub tokens, Home Assistant write permissions, calendar write tokens, or telephony authorization unless a workflow explicitly grants a constrained connector action through Nestor.

## Workflow Shape

Each complex use case should follow this shape:

```text
start
  collect context
  call specialized agent or connector
  return questions if needed
resume
  incorporate user answer
  continue planning or produce proposed actions
validate
  deterministic checks
await confirmation
  require explicit approval for sensitive actions
apply
  perform side effects idempotently
complete
  return result and audit summary
```

## LangGraph Compatibility

The current implementation keeps orchestration lightweight, but the concepts mirror LangGraph:

- `WorkflowRun.id` maps to a thread/run id.
- `WorkflowStatus.needs_user_input` maps to an interrupt.
- `WorkflowStore` maps to a checkpoint store.
- workflow methods map to graph nodes.

If workflows become numerous or deeply stateful, this structure can be migrated to LangGraph without changing the domain contracts.
