from nestor_mcp.models.newsletter import NewsletterDigest


class NewsletterService:
    def summarize(self, source: str) -> NewsletterDigest:
        return NewsletterDigest(source=source, title="Newsletter digest", highlights=[])

