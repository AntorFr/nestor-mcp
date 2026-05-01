from typing import Any

from nestor_mcp.models.common import StrictBaseModel


class HaEntity(StrictBaseModel):
    entity_id: str
    state: str
    attributes: dict[str, Any] = {}


class HaService(StrictBaseModel):
    domain: str
    services: list[str]


class HaInventory(StrictBaseModel):
    entities: list[HaEntity]
    services: list[HaService]
    config: dict[str, Any]

