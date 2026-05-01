from nestor_mcp.models.common import StrictBaseModel


class ActivitySuggestion(StrictBaseModel):
    title: str
    context: str
    steps: list[str]

