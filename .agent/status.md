# Status — nestor-mcp

> MàJ : 2026-07-16

**État :** Serveur MCP (FastMCP + FastAPI) déployé sur tantive en `0.3.5-beta`,
derrière le sidecar OAuth `mcp-auth-proxy` sur `nestor.mcp.berard.me`. Outils
exposés : explain / draft / status / list / cancel de changements Home Assistant
via GitOps. Le transport streamable HTTP est servi à la **racine** (contrainte du
sidecar OAuth, voir README) — l'intégration MCP de Home Assistant se configure
avec `https://nestor.mcp.berard.me/`.

**Prochaines étapes :**
- [ ] Vérifier en conditions réelles que l'intégration MCP de HA s'ajoute bien
      sur `https://nestor.mcp.berard.me/` (OAuth → handshake → outils listés)
- [ ] `mcp-auth login nestor` (jamais fait : pas de `~/.config/mcp-auth/nestor.json`)
- [ ] README en français alors que le repo est public — migrer en anglais
