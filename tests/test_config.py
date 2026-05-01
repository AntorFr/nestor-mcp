import os
from pathlib import Path

from nestor_mcp.config import get_settings, load_environment_file


def test_load_environment_file_exports_dotenv_values_to_process_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    (tmp_path / ".env").write_text("ANTHROPIC_API_KEY=test-key\n", encoding="utf-8")

    load_environment_file()

    assert os.environ["ANTHROPIC_API_KEY"] == "test-key"


def test_load_environment_file_does_not_override_existing_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("HOME_ASSISTANT_TOKEN", "from-kubernetes-secret")
    (tmp_path / ".env").write_text("HOME_ASSISTANT_TOKEN=from-env-file\n", encoding="utf-8")

    load_environment_file()

    assert os.environ["HOME_ASSISTANT_TOKEN"] == "from-kubernetes-secret"


def test_get_settings_loads_dotenv_before_settings_are_created(
    tmp_path: Path,
    monkeypatch,
) -> None:
    get_settings.cache_clear()
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CODE_AGENT_PROVIDER", raising=False)
    (tmp_path / ".env").write_text("CODE_AGENT_PROVIDER=claude_code\n", encoding="utf-8")

    try:
        settings = get_settings()
    finally:
        get_settings.cache_clear()

    assert settings.code_agent_provider == "claude_code"
    assert os.environ["CODE_AGENT_PROVIDER"] == "claude_code"
