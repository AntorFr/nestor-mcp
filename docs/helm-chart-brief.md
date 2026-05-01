# Brief Helm chart Nestor MCP

## Objectif

Créer un Helm chart pour déployer `nestor-mcp` dans Kubernetes, à côté de Home Assistant et des
autres services maison.

## Image

- Registry : `ghcr.io/antorfr/nestor-mcp`
- Premier tag cible : `0.0.1-beta`
- Port applicatif : `8000`
- Commande par défaut déjà fournie par l'image : `python -m nestor_mcp.server`

## Endpoints

- Health check : `GET /health`
- MCP streamable HTTP : `/mcp`
- MCP SSE : `/sse`

Probes recommandées :

- readinessProbe HTTP sur `/health`, port `8000`
- livenessProbe HTTP sur `/health`, port `8000`

## Configuration

L'application charge le fichier `.env` monté dans le répertoire de travail `/app`, puis propage ces
valeurs dans l'environnement du process sans écraser les variables déjà injectées par Kubernetes.
Les sous-process comme Claude Code héritent donc aussi des valeurs du `.env`.

Le chart peut monter un fichier `.env` complet via Secret sur `/app/.env`. Les valeurs sensibles
doivent venir d'un Secret Kubernetes ou d'un values override non commité.

Variables non sensibles :

- `MCP_HOST=0.0.0.0`
- `MCP_PORT=8000`
- `GITOPS_REPO_PATH=/data/home-assistant-config`
- `GITOPS_REPO_URL=https://github.com/AntorFr/Home-AssistantConfig.git`
- `GITOPS_DEFAULT_BRANCH=master`
- `PROPOSALS_PATH=/data/nestor-mcp/proposals`
- `WORKFLOW_RUNS_PATH=/data/nestor-mcp/workflow-runs`
- `DEFAULT_LLM_PROVIDER=mock`
- `DEFAULT_CODE_AGENT_PROVIDER=claude_code`
- `HA_EXPLAIN_PROVIDER=anthropic_api`
- `HA_EXPLAIN_MODEL=claude-3-5-haiku-latest`
- `HA_EXPLAIN_TIMEOUT_SECONDS=20`
- `HA_GITOPS_PROVIDER=claude_code`
- `HA_GITOPS_TIMEOUT_SECONDS=180`
- `CLAUDE_CODE_COMMAND=claude`
- `CLAUDE_CODE_TIMEOUT_SECONDS=120`

Secrets :

- `ANTHROPIC_API_KEY`
- `HOME_ASSISTANT_URL`
- `HOME_ASSISTANT_TOKEN`
- futur : token GitHub si le workflow d'édition/PR est activé

## Volumes persistants

Le pod doit conserver :

- le clone local du repo Home Assistant : `/data/home-assistant-config`
- les propositions GitOps : `/data/nestor-mcp/proposals`
- les états de workflows/conversations : `/data/nestor-mcp/workflow-runs`

Deux options acceptables :

- un PVC unique monté sur `/data`
- trois PVCs séparés pour isoler repo, propositions et états

Pour le premier déploiement, un PVC unique est suffisant.

Prévoir aussi un volume writable sur `/tmp` lorsque `readOnlyRootFilesystem=true`. L'image définit
`HOME=/tmp`, `XDG_CACHE_HOME=/tmp/.cache` et `XDG_CONFIG_HOME=/tmp/.config` pour que Claude Code et
les outils Node/Python disposent d'un espace d'écriture temporaire sans rendre le filesystem racine
inscriptible.

## Service et exposition

Créer un `Service` ClusterIP exposant le port `8000`.

L'accès doit être limité au réseau interne Kubernetes/Home Assistant. Pas d'exposition publique par
défaut.

Si Home Assistant est hors cluster, prévoir une option Ingress ou LoadBalancer explicitement
désactivée par défaut.

## Sécurité

Recommandations :

- ne pas exécuter en privileged
- `allowPrivilegeEscalation: false`
- filesystem root idéalement read-only, avec `/data` et `/tmp` en écriture
- secrets injectés via Kubernetes Secret, pas dans les values commités
- ressources configurables dans `values.yaml`

## Ressources

Point de départ :

- requests CPU : `100m`
- requests memory : `256Mi`
- limits CPU : `1000m`
- limits memory : `1Gi`

Claude Code peut consommer davantage pendant les analyses. Garder ces valeurs configurables.

## Notes GitOps

Le service synchronise le repo local avant chaque analyse. Le répertoire monté sur
`GITOPS_REPO_PATH` peut être vide au premier démarrage : Nestor clonera le repo configuré.

Le workflow actuel est en lecture seule. Les futurs workflows d'édition devront créer une branche et
un PR vers `master`, sans modification directe de Home Assistant en production.
