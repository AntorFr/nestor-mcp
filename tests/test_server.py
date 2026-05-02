from starlette.testclient import TestClient

from nestor_mcp.config import get_settings
from nestor_mcp.server import create_app, create_mcp_server


def test_app_exposes_mcp_transport_routes_at_root_paths() -> None:
    app = create_app(create_mcp_server())

    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/health" in paths
    assert "/sse" in paths
    assert "/messages" in paths
    assert "/mcp" in paths


def test_health_endpoint_works_with_mcp_routes_registered() -> None:
    app = create_app(create_mcp_server())

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200


def test_mcp_server_uses_configured_host_and_port() -> None:
    get_settings.cache_clear()
    settings = get_settings()

    server = create_mcp_server()

    try:
        assert server.settings.host == settings.mcp_host
        assert server.settings.port == settings.mcp_port
        assert server.settings.transport_security is None
    finally:
        get_settings.cache_clear()


def test_mcp_server_exposes_only_implemented_tools() -> None:
    server = create_mcp_server()
    tool_names = set(server._tool_manager._tools)

    assert "explain_smart_home_behavior" in tool_names
    assert "draft_home_assistant_change" in tool_names
    assert "get_home_assistant_change_status" in tool_names
    assert "search_knowledge" not in tool_names
    assert "summarize_newsletter" not in tool_names
    assert "create_task" not in tool_names
    assert "suggest_activity" not in tool_names
