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
