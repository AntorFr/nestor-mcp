from uuid import uuid4

from nestor_mcp.models.task import TaskItem


class TaskService:
    def create(self, title: str, description: str | None = None) -> TaskItem:
        return TaskItem(id=str(uuid4()), title=title, description=description)

