from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    env: str = Field(default="local", alias="NESTOR_ENV")
    log_level: str = Field(default="INFO", alias="NESTOR_LOG_LEVEL")

    mcp_server_name: str = Field(default="nestor-mcp", alias="MCP_SERVER_NAME")
    mcp_host: str = Field(default="0.0.0.0", alias="MCP_HOST")
    mcp_port: int = Field(default=8000, alias="MCP_PORT")

    home_assistant_url: AnyHttpUrl | None = Field(default=None, alias="HOME_ASSISTANT_URL")
    home_assistant_token: str | None = Field(default=None, alias="HOME_ASSISTANT_TOKEN")
    allow_direct_ha_writes: bool = Field(default=False, alias="ALLOW_DIRECT_HA_WRITES")

    gitops_repo_path: Path = Field(
        default=Path("/data/home-assistant-config"),
        alias="GITOPS_REPO_PATH",
    )
    gitops_repo_url: str = Field(
        default="https://github.com/AntorFr/Home-AssistantConfig.git",
        alias="GITOPS_REPO_URL",
    )
    gitops_default_branch: str = Field(default="master", alias="GITOPS_DEFAULT_BRANCH")

    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    github_repo: str = Field(default="AntorFr/Home-AssistantConfig", alias="GITHUB_REPO")
    github_api_url: AnyHttpUrl = Field(default="https://api.github.com", alias="GITHUB_API_URL")
    git_author_name: str = Field(default="Nestor MCP", alias="GIT_AUTHOR_NAME")
    git_author_email: str = Field(
        default="nestor-mcp@users.noreply.github.com",
        alias="GIT_AUTHOR_EMAIL",
    )

    proposals_path: Path = Field(default=Path("/data/nestor-mcp/proposals"), alias="PROPOSALS_PATH")
    workflow_runs_path: Path = Field(
        default=Path("/data/nestor-mcp/workflow-runs"),
        alias="WORKFLOW_RUNS_PATH",
    )

    code_agent_provider: str = Field(default="mock", alias="CODE_AGENT_PROVIDER")
    claude_code_command: str = Field(default="claude", alias="CLAUDE_CODE_COMMAND")
    claude_code_timeout_seconds: int = Field(default=120, alias="CLAUDE_CODE_TIMEOUT_SECONDS")


@lru_cache
def get_settings() -> Settings:
    return Settings()
