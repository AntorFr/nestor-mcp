# nestor-mcp

Serveur MCP pour exposer des skills maison à Home Assistant Assist via un LLM Conversation Agent.

Le serveur est conçu pour être GitOps-first : les tools préparent des changements, validations ou propositions, mais ne modifient pas directement une instance Home Assistant de production.

## Fonctionnalités prévues

- Exposition de tools MCP découvrables par Home Assistant.
- Explication en lecture seule de la configuration Home Assistant via le repo GitOps local.
- Préparation de changements Home Assistant sous forme de commits/branches/PR.
- Services dédiés pour newsletters, knowledge base, tâches et activités.
- Garde-fous de sécurité centralisés.
- Exécution locale ou via Docker Compose.

## Démarrage local

```bash
cp .env.example .env
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
pytest
```

## Lancer le serveur

```bash
python -m nestor_mcp.server
```

Ou avec Docker :

```bash
docker compose up --build
```

Le serveur expose :

- `GET /health` pour les probes.
- `/mcp` pour le transport MCP streamable HTTP.
- `/sse` pour le transport MCP SSE.

## Test du workflow Home Assistant

Le workflow d'explication HA peut être testé sans Home Assistant Assist :

```bash
docker compose run --rm nestor-mcp python -m nestor_mcp.devtools.explain_ha \
  "Pourquoi les lumières s'allument toutes seules dans le salon ?"
```

La réponse par défaut est volontairement non technique. Une question qui demande les détails de
configuration, les fichiers, le YAML ou les entités active un mode plus expert.

## Variables d'environnement

Voir [.env.example](.env.example).

Les fichiers `.env*` sont exclus du dépôt, sauf `.env.example`.

## Principes de sécurité

- `ALLOW_DIRECT_HA_WRITES=false` par défaut.
- Les chemins GitOps sont validés pour rester dans le dépôt configuré.
- Les changements dangereux doivent être refusés avant toute interaction externe.

## Architecture

Nestor expose des tools métier à Home Assistant Assist, puis orchestre les workflows et délègue les intégrations concrètes à des providers spécialisés :

- `orchestration/` : état durable, workflows, reprise après question/confirmation.
- `capabilities/` : fonctions transverses réutilisables comme agent code, workspace, web research.
- `agents/` : adaptateurs bas niveau pour providers d'agents si nécessaire.
- `connectors/` : adaptateurs vers n8n, calendriers, tâches ou futurs MCP externes.
- `workflows/` : cas d'usage longs comme HA GitOps, rendez-vous, calendrier.
- `security/` : validations et politiques avant toute action externe.

Voir [docs/architecture.md](docs/architecture.md) et [docs/implementation-rails.md](docs/implementation-rails.md).

## CI/CD

La GitHub Action [docker-release.yml](.github/workflows/docker-release.yml) exécute Ruff et pytest,
puis publie l'image Docker sur GitHub Container Registry pour les pushes sur `master` et les tags.

Image attendue :

```text
ghcr.io/antorfr/nestor-mcp
```

Pour créer la première beta :

```bash
git tag 0.0.1-beta
git push origin 0.0.1-beta
```

Le tag publiera notamment :

```text
ghcr.io/antorfr/nestor-mcp:0.0.1-beta
```

et créera une GitHub Release avec les notes générées automatiquement.
