class KnowledgeService:
    def search(self, query: str) -> list[str]:
        return [f"No knowledge backend configured for query: {query}"]

