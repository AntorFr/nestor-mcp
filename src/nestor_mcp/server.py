import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from nestor_mcp.config import get_settings
from nestor_mcp.logging_config import configure_logging
from nestor_mcp.tools.activities import register_activity_tools
from nestor_mcp.tools.ha_gitops import register_ha_gitops_tools
from nestor_mcp.tools.knowledge import register_knowledge_tools
from nestor_mcp.tools.newsletter import register_newsletter_tools
from nestor_mcp.tools.tasks import register_task_tools

logger = logging.getLogger(__name__)


def create_mcp_server() -> FastMCP:
    settings = get_settings()
    mcp = FastMCP(
        settings.mcp_server_name,
        host=settings.mcp_host,
        port=settings.mcp_port,
    )

    register_ha_gitops_tools(mcp)
    register_newsletter_tools(mcp)
    register_knowledge_tools(mcp)
    register_task_tools(mcp)
    register_activity_tools(mcp)

    return mcp


def create_app(mcp: FastMCP | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    mcp = mcp or create_mcp_server()
    sse_app = mcp.sse_app()
    streamable_http_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with mcp.session_manager.run():
            yield

    app = FastAPI(title=settings.mcp_server_name, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.router.routes.extend(sse_app.routes)
    app.router.routes.extend(streamable_http_app.routes)

    return app


mcp_server = create_mcp_server()
app = create_app(mcp_server)


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level)
    logger.info(
        "Starting %s on %s:%s",
        settings.mcp_server_name,
        settings.mcp_host,
        settings.mcp_port,
    )
    uvicorn.run("nestor_mcp.server:app", host=settings.mcp_host, port=settings.mcp_port)


if __name__ == "__main__":
    main()
