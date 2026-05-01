from mcp.server.fastmcp import FastMCP

from nestor_mcp.models.newsletter import NewsletterDigest
from nestor_mcp.services.newsletter_service import NewsletterService


def register_newsletter_tools(mcp: FastMCP) -> None:
    @mcp.tool()
    def summarize_newsletter(source: str) -> NewsletterDigest:
        """Summarize newsletter content from a trusted source."""
        return NewsletterService().summarize(source)

