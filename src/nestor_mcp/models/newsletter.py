from nestor_mcp.models.common import StrictBaseModel


class NewsletterDigest(StrictBaseModel):
    source: str
    title: str
    highlights: list[str]

