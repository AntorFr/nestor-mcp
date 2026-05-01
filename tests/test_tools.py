from nestor_mcp.services.task_service import TaskService


def test_task_service_creates_task() -> None:
    task = TaskService().create("Water plants")

    assert task.title == "Water plants"
    assert task.completed is False

