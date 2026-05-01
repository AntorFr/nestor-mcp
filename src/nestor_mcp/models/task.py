from nestor_mcp.models.common import StrictBaseModel


class TaskItem(StrictBaseModel):
    id: str
    title: str
    description: str | None = None
    completed: bool = False

