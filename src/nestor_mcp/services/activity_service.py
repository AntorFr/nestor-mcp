from nestor_mcp.models.activity import ActivitySuggestion


class ActivityService:
    def suggest(self, context: str) -> ActivitySuggestion:
        return ActivitySuggestion(title="Activity suggestion", context=context, steps=[])

