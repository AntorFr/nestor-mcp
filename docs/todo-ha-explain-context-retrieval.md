# TODO - Fiabiliser la detection de contexte HA pour `explain_home_assistant_config`

## Statut
- Priorite: haute (probleme structurant)
- Etat: a traiter plus tard
- Date de creation: 2026-05-03

## Probleme observe
Le workflow d'explication HA peut repondre qu'une automation est introuvable alors qu'elle existe dans le repo GitOps monte dans le pod.

Exemple concret:
- Question utilisateur sur `function_portail_sonette`.
- Reponse MCP: automation non trouvee.
- Realite: automation presente dans `packages/functions/portail.yaml`.

## Impact
- Faux negatifs en analyse config (perte de confiance utilisateur).
- Reponses LLM basees sur un contexte incomplet.
- Maintenance difficile: chaque nouveau fichier/fonction impose de maintenir un mapping manuel.

## Cause racine (confirmee)
Le collecteur de contexte utilise une selection statique `keyword -> fichier`.

Si la question ne contient pas un mot-cle prevu dans les tables de hints, le fichier cible n'est jamais fourni au LLM.

Dans le cas `function_portail_sonette`, le fichier `packages/functions/portail.yaml` n'est pas reference dans les hints, donc il peut etre exclu.

## Localisation dans le code
- `src/nestor_mcp/workflows/ha_explain/context.py`
  - `HaExplainContextCollector.collect(...)`
  - Appelle `RepoContextCapability.find_ha_package_candidates(...)` puis `read_files(...)`.
- `src/nestor_mcp/capabilities/workspace/repo_context.py`
  - `FUNCTION_FILE_HINTS`, `AREA_FILE_HINTS`, `ROUTINE_FILE_HINTS`
  - `find_ha_package_candidates(...)`: logique de matching statique.

## Verification terrain (k8s)
Verification faite dans le pod `home/nestor-mcp-848f95fbfc-wwv7m`:
- Le fichier existe dans `/data/home-assistant-config/packages/functions/portail.yaml`.
- Le fichier contient bien `function_portail_sonette`.
- Le code charge dans le pod confirme l'absence de hint `portail.yaml` dans `FUNCTION_FILE_HINTS`.

Conclusion: ce n'est pas un probleme de replication du volume, mais de retrieval applicatif.

## Options de correction (du minimum au robuste)

### Option A - Quick win (court terme)
Ajouter des hints manquants (ex: `portail -> packages/functions/portail.yaml`) + quelques synonymes.

Avantages:
- Tres rapide.
- Limite immediatement les faux negatifs connus.

Limites:
- Dette technique conservee.
- Ne scale pas quand le repo evolue.

### Option B - Fallback lexical global (court/moyen terme)
Conserver le mapping statique, mais ajouter un fallback recherche globale quand peu/pas de candidats:
- recherche `id`, `alias`, `entity_id`, nom de fichier
- scoring simple (exact > prefix > fuzzy)

Avantages:
- Gros gain de robustesse avec effort modere.
- Compatible avec l'architecture actuelle.

Limites:
- Toujours heuristique.
- Peut remonter trop de candidats sans rerank.

### Option C - Retrieval hybride indexe (solution cible)
Construire un index local des objets HA (yaml parse + metadonnees), puis retrieval en 3 etapes:
1. exact/fuzzy ID lookup
2. lexical search (BM25/trigram)
3. semantic fallback (embeddings), puis rerank

Avantages:
- Robuste et extensible.
- Moins de maintenance manuelle.

Limites:
- Plus de complexite d'implementation.
- Besoin de metriques et observabilite.

## Recommandation
Implementer **B** rapidement, puis converger vers **C**.

Ordre conseille:
1. B1: fallback recherche globale id/alias/entity_id/fichier
2. B2: garde-fou de reponse (ne pas conclure "introuvable" sans fallback tente)
3. C1: index incrementale basee sur hash/mtime + commit
4. C2: rerank + metriques recall@k

## Taches concretes (backlog)
- [ ] Ajouter un fallback de recherche globale dans `RepoContextCapability`.
- [ ] Ajouter extraction de snippets pertinents (pas seulement fichier complet).
- [ ] Ajouter une politique de confiance avant de repondre "introuvable".
- [ ] Exposer des logs de retrieval (candidats, scores, fichiers injectes LLM).
- [ ] Ajouter des tests "golden retrieval" sur des cas reels:
  - `function_portail_sonette`
  - requetes par `entity_id`
  - requetes par alias partiel
  - fautes de frappe courantes (`sonette`/`sonnette`)
- [ ] Definir un SLO retrieval (ex: recall@5 >= 95% sur corpus de reference).

## Criteres d'acceptation
- Pour les cas golden, le fichier cible est toujours dans les candidats top-k.
- Le workflow n'affiche plus de faux "introuvable" pour des objets presents dans le repo.
- Les logs permettent d'expliquer pourquoi un fichier a ete (ou non) retenu.

## Notes de reprise rapide
- Point d'entree outil: `src/nestor_mcp/tools/ha_gitops.py` (`explain_home_assistant_config`).
- Chaine d'appel: `ha_gitops.py` -> `workflows/ha_explain/workflow.py` -> `workflows/ha_explain/graph.py` -> `workflows/ha_explain/context.py` -> `capabilities/workspace/repo_context.py`.
- Parametre repo par defaut: `GITOPS_REPO_PATH` (sinon `/data/home-assistant-config`).
