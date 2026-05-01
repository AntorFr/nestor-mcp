from mcp.server.fastmcp import FastMCP

from nestor_mcp.services.knowledge_service import KnowledgeService


def register_knowledge_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def search_knowledge(query: str) -> list[str]:
        """Search the local household knowledge base."""
        return KnowledgeService().search(query)

