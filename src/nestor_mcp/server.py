import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI
from mcp.server.fastmcp import FastMCP

from pathlib import Path

from nestor_mcp.capabilities.workspace.ha_doc_index import HaDocIndex
from nestor_mcp.capabilities.workspace.repo_context import _shared_ranker
from nestor_mcp.config import get_settings
from nestor_mcp.logging_config import configure_logging
from nestor_mcp.tools.ha_gitops import register_ha_gitops_tools

logger = logging.getLogger(__name__)


def _prewarm_doc_vectors(ranker) -> None:
    settings = get_settings()
    repo_path = settings.gitops_repo_path
    try:
        docs = HaDocIndex.from_repo(Path(repo_path)).docs
    except Exception as exc:  # noqa: BLE001
        logger.warning("Doc prewarm skipped (index error): %s", exc)
        return
    if not docs:
        logger.info("Doc prewarm skipped (no docs at %s)", repo_path)
        return
    try:
        ranker._ensure_doc_vectors(docs)  # type: ignore[attr-defined]
        logger.info("Doc prewarm: %d docs embedded", len(docs))
    except Exception as exc:  # noqa: BLE001
        logger.warning("Doc prewarm failed: %s", exc)


def create_mcp_server() -> FastMCP:
    settings = get_settings()
    mcp = FastMCP(
        settings.mcp_server_name,
        host=settings.mcp_host,
        port=settings.mcp_port,
    )

    register_ha_gitops_tools(mcp)

    return mcp


def create_app(mcp: FastMCP | None = None) -> FastAPI:
    settings = get_settings()
    configure_logging(settings.log_level)
    mcp = mcp or create_mcp_server()
    sse_app = mcp.sse_app()
    streamable_http_app = mcp.streamable_http_app()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        ranker = _shared_ranker()
        if ranker is not None and hasattr(ranker, "warmup"):
            logger.info("Warming up retrieval embedding model...")
            ok = await asyncio.to_thread(ranker.warmup)
            logger.info("Embedding model warmup: %s", "ok" if ok else "skipped (unavailable)")
            if ok:
                await asyncio.to_thread(_prewarm_doc_vectors, ranker)
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
