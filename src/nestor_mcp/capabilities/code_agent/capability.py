from abc import ABC, abstractmethod

from nestor_mcp.capabilities.code_agent.models import (
    CodeAgentExplainRequest,
    CodeAgentExplainResult,
    CodeAgentRequest,
    CodeAgentResult,
)


class CodeAgentCapability(ABC):
    @abstractmethod
    async def propose_changes(self, request: CodeAgentRequest) -> CodeAgentResult:
        """Return clarification questions or proposed file changes."""

    @abstractmethod
    async def explain_config(self, request: CodeAgentExplainRequest) -> CodeAgentExplainResult:
        """Explain code/config from read-only context."""
