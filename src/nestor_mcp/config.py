from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ENV_FILE = Path(".env")


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

    default_llm_provider: str = Field(default="mock", alias="DEFAULT_LLM_PROVIDER")
    default_code_agent_provider: str = Field(
        default="claude_code",
        alias="DEFAULT_CODE_AGENT_PROVIDER",
    )
    ha_explain_provider: str | None = Field(default=None, alias="HA_EXPLAIN_PROVIDER")
    ha_explain_model: str = Field(
        default="claude-haiku-4-5-20251001",
        alias="HA_EXPLAIN_MODEL",
    )
    ha_explain_timeout_seconds: int = Field(default=20, alias="HA_EXPLAIN_TIMEOUT_SECONDS")
    ha_gitops_provider: str | None = Field(default=None, alias="HA_GITOPS_PROVIDER")
    ha_gitops_timeout_seconds: int = Field(default=180, alias="HA_GITOPS_TIMEOUT_SECONDS")
    ha_gitops_assist_timeout_seconds: int = Field(
        default=8,
        alias="HA_GITOPS_ASSIST_TIMEOUT_SECONDS",
    )
    ha_gitops_draft_stale_seconds: int = Field(
        default=120,
        alias="HA_GITOPS_DRAFT_STALE_SECONDS",
    )
    ha_gitops_draft_expire_seconds: int = Field(
        default=1800,
        alias="HA_GITOPS_DRAFT_EXPIRE_SECONDS",
    )

    ha_retrieval_embeddings_enabled: bool = Field(
        default=True,
        alias="HA_RETRIEVAL_EMBEDDINGS_ENABLED",
    )
    ha_retrieval_embedding_model: str = Field(
        default="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
        alias="HA_RETRIEVAL_EMBEDDING_MODEL",
    )
    ha_retrieval_lexical_threshold: float = Field(
        default=5.0,
        alias="HA_RETRIEVAL_LEXICAL_THRESHOLD",
    )

    anthropic_api_key: str | None = Field(default=None, alias="ANTHROPIC_API_KEY")
    claude_code_command: str = Field(default="claude", alias="CLAUDE_CODE_COMMAND")
    claude_code_timeout_seconds: int = Field(default=120, alias="CLAUDE_CODE_TIMEOUT_SECONDS")


def load_environment_file() -> None:
    load_dotenv(ENV_FILE, override=False)


@lru_cache
def get_settings() -> Settings:
    load_environment_file()
    return Settings()
