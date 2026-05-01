from abc import ABC, abstractmethod
from datetime import datetime

from nestor_mcp.models.common import StrictBaseModel


class CalendarEventDraft(StrictBaseModel):
    title: str
    starts_at: datetime
    ends_at: datetime
    calendar_id: str | None = None
    description: str | None = None


class CalendarConnector(ABC):
    @abstractmethod
    async def create_event(self, event: CalendarEventDraft) -> str:
        """Create an event and return the provider event id."""

