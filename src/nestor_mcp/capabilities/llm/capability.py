from abc import ABC, abstractmethod

from nestor_mcp.capabilities.llm.models import LlmExplainRequest, LlmExplainResult


class LlmCapability(ABC):
    @abstractmethod
    async def explain(self, request: LlmExplainRequest) -> LlmExplainResult:
        """Explain read-only context with a low-latency LLM provider."""
