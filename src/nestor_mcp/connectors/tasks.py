from abc import ABC, abstractmethod

from nestor_mcp.models.task import TaskItem


class TaskConnector(ABC):
    @abstractmethod
    async def create_task(self, title: str, description: str | None = None) -> TaskItem:
        """Create a task in an external task system."""

