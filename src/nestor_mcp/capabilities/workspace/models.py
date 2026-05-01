from pathlib import Path

from nestor_mcp.models.common import StrictBaseModel


class WorkspaceRef(StrictBaseModel):
    id: str
    path: Path
    source: str


class PatchSet(StrictBaseModel):
    files: dict[str, str]
    diff: str

