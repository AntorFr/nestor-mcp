from nestor_mcp.config import get_settings
from nestor_mcp.security.validators import ensure_editable_ha_path


class SecurityPolicy:
    def __init__(self) -> None:
        self.settings = get_settings()

    def ensure_direct_ha_write_allowed(self) -> None:
        if not self.settings.allow_direct_ha_writes:
            raise PermissionError("Direct Home Assistant writes are disabled")

    def ensure_gitops_change_allowed(self, path: str) -> None:
        ensure_editable_ha_path(path)
