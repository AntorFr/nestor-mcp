from mcp.server.fastmcp import FastMCP

from nestor_mcp.models.task import TaskItem
from nestor_mcp.services.task_service import TaskService


def register_task_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def create_task(title: str, description: str | None = None) -> TaskItem:
        """Create a household task draft."""
        return TaskService().create(title=title, description=description)

