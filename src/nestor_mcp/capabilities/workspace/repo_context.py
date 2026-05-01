from pathlib import Path

from nestor_mcp.capabilities.code_agent.models import CodeAgentFile

AREA_FILE_HINTS = {
    "salon": "packages/areas/salon.yaml",
    "cuisine": "packages/areas/cuisine.yaml",
    "bureau": "packages/areas/bureau.yaml",
    "garage": "packages/areas/garage.yaml",
    "jardin": "packages/areas/jardin.yaml",
    "piscine": "packages/areas/piscine.yaml",
    "buanderie": "packages/areas/buanderie.yaml",
    "salle a manger": "packages/areas/salle_a_manger.yaml",
    "salle à manger": "packages/areas/salle_a_manger.yaml",
    "chambre parent": "packages/areas/chambre_parent.yaml",
    "chambre timothee": "packages/areas/chambre_timothee.yaml",
    "chambre timothée": "packages/areas/chambre_timothee.yaml",
    "chambre emilie": "packages/areas/chambre_emilie.yaml",
    "chambre émilie": "packages/areas/chambre_emilie.yaml",
}

FUNCTION_FILE_HINTS = {
    "lumiere": "packages/functions/lights.yaml",
    "lumière": "packages/functions/lights.yaml",
    "lumieres": "packages/functions/lights.yaml",
    "lumières": "packages/functions/lights.yaml",
    "chauffage": "packages/functions/heating.yaml",
    "presence": "packages/functions/presence.yaml",
    "présence": "packages/functions/presence.yaml",
    "notification": "packages/functions/notification.yaml",
    "securite": "packages/functions/securtity_system.yaml",
    "sécurité": "packages/functions/securtity_system.yaml",
    "energie": "packages/functions/energy_monitor.yaml",
    "énergie": "packages/functions/energy_monitor.yaml",
    "tv": "packages/functions/tv.yaml",
}

ROUTINE_FILE_HINTS = {
    "routine": "packages/routines/day.yaml",
    "matin": "packages/routines/day.yaml",
    "soir": "packages/routines/day.yaml",
    "nuit": "packages/routines/day.yaml",
    "absence": "packages/routines/away.yaml",
    "enfant": "packages/routines/children.yaml",
    "travail": "packages/routines/work.yaml",
}


class RepoContextCapability:
    def __init__(self, repo_path: Path) -> None:
        self.repo_path = repo_path

    def find_ha_package_candidates(
        self,
        question: str,
        previous_files: list[str] | None = None,
    ) -> list[str]:
        normalized = question.lower()
        matches: list[str] = []
        for hints in (AREA_FILE_HINTS, FUNCTION_FILE_HINTS, ROUTINE_FILE_HINTS):
            for keyword, path in hints.items():
                if keyword in normalized and path not in matches:
                    matches.append(path)

        if not matches and previous_files:
            matches.extend(previous_files)

        return [path for path in matches if (self.repo_path / path).exists()][:6]

    def read_files(self, paths: list[str], max_chars_per_file: int = 18000) -> list[CodeAgentFile]:
        files = []
        for path in paths:
            target = self.repo_path / path
            if not target.exists() or not target.is_file():
                continue
            content = target.read_text(encoding="utf-8")[:max_chars_per_file]
            files.append(CodeAgentFile(path=path, content=content))
        return files
