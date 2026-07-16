# Status — nestor-mcp

> MàJ : 2026-07-17

**État :** Serveur MCP (FastMCP + FastAPI) déployé sur tantive en `0.3.6-beta`,
derrière le sidecar OAuth `mcp-auth-proxy` sur `nestor.mcp.berard.me`. Outils
exposés : explain / draft / status / list / cancel de changements Home Assistant
via GitOps. Le transport streamable HTTP est servi à la **racine** (contrainte du
sidecar OAuth, voir README). L'intégration MCP de Home Assistant est **branchée et
fonctionnelle** sur `https://nestor.mcp.berard.me/` (vérifié le 2026-07-17).

**Prochaines étapes :**
- [ ] `mcp-auth login nestor` (jamais fait : pas de `~/.config/mcp-auth/nestor.json`)
- [ ] README en français alors que le repo est public — migrer en anglais
