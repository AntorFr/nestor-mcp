import pytest

from nestor_mcp.security.policy import SecurityPolicy
from nestor_mcp.security.validators import ensure_editable_ha_path, ensure_relative_safe_path


def test_rejects_absolute_paths() -> None:
    with pytest.raises(ValueError, match="relative"):
        ensure_relative_safe_path("/tmp/config.yaml")


def test_rejects_path_traversal() -> None:
    with pytest.raises(ValueError, match="traversal"):
        ensure_relative_safe_path("../secrets.yaml")


def test_direct_home_assistant_writes_disabled_by_default() -> None:
    with pytest.raises(PermissionError):
        SecurityPolicy().ensure_direct_ha_write_allowed()


def test_rejects_protected_home_assistant_paths() -> None:
    with pytest.raises(ValueError, match="Protected"):
        ensure_editable_ha_path("secrets.yaml")

    with pytest.raises(ValueError, match="Protected"):
        ensure_editable_ha_path(".storage/core.config_entries")
