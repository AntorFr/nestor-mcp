# Nestor Home Assistant Editing Rules

Nestor edits Home Assistant through GitOps only. It must never write directly to production Home Assistant.

## Repository

- Repository: `AntorFr/Home-AssistantConfig`
- Base branch: `master`
- Work model: persistent local clone, refreshed before every analysis with `git fetch` and fast-forward pull.
- Output model: branch on the same repository, then pull request to `master`.

## Package Placement

Use `packages/areas/*.yaml` for room or area-specific configuration:

- grouped sensors
- grouped lights
- automations local to one room
- scripts local to one room

Use `packages/functions/*.yaml` for cross-area behavior:

- lights
- heating
- presence
- notifications
- security
- energy
- TV or media behavior shared across areas

Use `packages/routines/*.yaml` for life routines:

- morning, evening, night
- away mode
- children routines
- work routines
- global routine scripts

Use `packages/integrations/*.yaml` for one external integration:

- Tesla
- Netatmo
- Linky
- Roborock
- Unifi Protect

Use `packages/devices/*.yaml` for device families and cluster/mobile behavior.

Use `packages/system/*.yaml` for infrastructure monitoring:

- network
- MQTT
- system health

## Protected Paths

Never edit:

- `secrets.yaml`
- `.storage/`
- `custom_components/`, unless explicitly requested
- files containing tokens, passwords, private keys, or credentials

## Validation

Before creating a branch or pull request:

- parse touched YAML files
- reject protected paths
- verify referenced `entity_id` values against Home Assistant states when possible
- verify `action` or service calls against Home Assistant services when possible
- require explicit user confirmation

