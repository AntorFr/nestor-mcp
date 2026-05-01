import httpx

from nestor_mcp.config import get_settings
from nestor_mcp.models.home_assistant import HaEntity, HaInventory, HaService
from nestor_mcp.security.policy import SecurityPolicy


class HomeAssistantService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.policy = SecurityPolicy()

    def headers(self) -> dict[str, str]:
        headers = {"Content-Type": "application/json"}
        if self.settings.home_assistant_token:
            headers["Authorization"] = f"Bearer {self.settings.home_assistant_token}"
        return headers

    def ensure_configured(self) -> None:
        if self.settings.home_assistant_url is None:
            raise RuntimeError("HOME_ASSISTANT_URL is not configured")

    async def get_json(self, path: str) -> object:
        self.ensure_configured()
        async with httpx.AsyncClient(base_url=str(self.settings.home_assistant_url)) as client:
            response = await client.get(path, headers=self.headers())
            response.raise_for_status()
            return response.json()

    async def get_config(self) -> dict:
        data = await self.get_json("/api/config")
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected Home Assistant config response")
        return data

    async def get_states(self) -> list[HaEntity]:
        data = await self.get_json("/api/states")
        if not isinstance(data, list):
            raise RuntimeError("Unexpected Home Assistant states response")
        return [
            HaEntity(
                entity_id=item["entity_id"],
                state=str(item.get("state", "")),
                attributes=item.get("attributes") or {},
            )
            for item in data
            if isinstance(item, dict) and "entity_id" in item
        ]

    async def get_state(self, entity_id: str) -> dict:
        data = await self.get_json(f"/api/states/{entity_id}")
        if not isinstance(data, dict):
            raise RuntimeError("Unexpected Home Assistant state response")
        return data

    async def get_services(self) -> list[HaService]:
        data = await self.get_json("/api/services")
        if not isinstance(data, list):
            raise RuntimeError("Unexpected Home Assistant services response")
        return [
            HaService(domain=item["domain"], services=list((item.get("services") or {}).keys()))
            for item in data
            if isinstance(item, dict) and "domain" in item
        ]

    async def get_inventory(self) -> HaInventory:
        return HaInventory(
            entities=await self.get_states(),
            services=await self.get_services(),
            config=await self.get_config(),
        )

    async def search_entities(self, query: str, domains: list[str] | None = None) -> list[HaEntity]:
        normalized_query = query.lower()
        states = await self.get_states()
        return [
            entity
            for entity in states
            if (domains is None or entity.entity_id.split(".", 1)[0] in domains)
            and (
                normalized_query in entity.entity_id.lower()
                or normalized_query in str(entity.attributes.get("friendly_name", "")).lower()
            )
        ]

    async def write_state(self, entity_id: str, state: str) -> None:
        self.policy.ensure_direct_ha_write_allowed()
        raise NotImplementedError("Direct Home Assistant writes are intentionally not implemented")
