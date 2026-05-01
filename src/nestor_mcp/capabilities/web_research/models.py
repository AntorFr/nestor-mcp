from nestor_mcp.models.common import StrictBaseModel


class WebResearchSource(StrictBaseModel):
    title: str
    url: str
    summary: str


class WebResearchResult(StrictBaseModel):
    query: str
    sources: list[WebResearchSource]

