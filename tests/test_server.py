from starlette.testclient import TestClient

from nestor_mcp.server import create_app, create_mcp_server


def test_app_exposes_mcp_transport_routes_at_root_paths() -> None:
    app = create_app(create_mcp_server())

    paths = {getattr(route, "path", None) for route in app.routes}

    assert "/health" in paths
    assert "/sse" in paths
    assert "/messages" in paths
    assert "/mcp" in paths


def test_sse_and_streamable_http_paths_are_not_missing() -> None:
    app = create_app(create_mcp_server())

    with TestClient(app, raise_server_exceptions=False) as client:
        assert client.get("/health").status_code == 200
        assert client.get("/sse").status_code != 404
        assert client.get("/sse/").status_code != 404
        assert client.get("/mcp").status_code != 404
        assert client.get("/mcp/").status_code != 404
