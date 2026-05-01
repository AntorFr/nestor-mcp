from mcp.server.fastmcp import FastMCP

from nestor_mcp.models.activity import ActivitySuggestion
from nestor_mcp.services.activity_service import ActivityService


def register_activity_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def suggest_activity(context: str) -> ActivitySuggestion:
        """Suggest a household or family activity."""
        return ActivityService().suggest(context)

