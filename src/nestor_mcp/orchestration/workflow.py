from abc import ABC, abstractmethod
from typing import Any

from nestor_mcp.orchestration.state import WorkflowRun


class SkillWorkflow(ABC):
    name: str

    @abstractmethod
    async def start(self, user_input: dict[str, Any]) -> WorkflowRun:
        """Start a workflow run."""

    @abstractmethod
    async def resume(self, run_id: str, user_input: dict[str, Any]) -> WorkflowRun:
        """Resume a workflow run after a user answer or confirmation."""

    @abstractmethod
    async def status(self, run_id: str) -> WorkflowRun:
        """Return the current workflow run state."""

