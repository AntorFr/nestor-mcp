from pathlib import Path

PROTECTED_PATH_PARTS = {".storage", "custom_components"}
PROTECTED_FILE_NAMES = {"secrets.yaml"}
SENSITIVE_TOKENS = ("password", "passwd", "secret", "token", "private_key", "api_key")


def ensure_relative_safe_path(path: str) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        raise ValueError("Path must be relative")
    if any(part == ".." for part in candidate.parts):
        raise ValueError("Path traversal is not allowed")
    if not candidate.parts:
        raise ValueError("Path must not be empty")
    return candidate


def ensure_editable_ha_path(path: str) -> Path:
    candidate = ensure_relative_safe_path(path)
    if candidate.name in PROTECTED_FILE_NAMES:
        raise ValueError(f"Protected Home Assistant file cannot be edited: {candidate}")
    if any(part in PROTECTED_PATH_PARTS for part in candidate.parts):
        raise ValueError(f"Protected Home Assistant path cannot be edited: {candidate}")
    if any(token in candidate.as_posix().lower() for token in SENSITIVE_TOKENS):
        raise ValueError(f"Sensitive path cannot be edited: {candidate}")
    return candidate
