from pathlib import Path
from re import sub

from git import Actor, Repo
from yaml import YAMLError, safe_load

from nestor_mcp.config import get_settings
from nestor_mcp.models.ha_change import (
    HomeAssistantChangeRequest,
    HomeAssistantChangeResult,
    ProposedFileChange,
    ValidationResult,
)
from nestor_mcp.security.validators import ensure_editable_ha_path


class GitService:
    def __init__(self, repo_path: Path | None = None) -> None:
        self.settings = get_settings()
        self.repo_path = Path(repo_path or self.settings.gitops_repo_path)

    def repo(self) -> Repo:
        return Repo(self.repo_path)

    def ensure_repo_available(self) -> Repo:
        git_dir = self.repo_path / ".git"
        if not self.repo_path.exists() or not git_dir.exists():
            if self.repo_path.exists() and any(self.repo_path.iterdir()):
                raise RuntimeError(
                    f"GitOps repository path exists but is not a git repository: {self.repo_path}"
                )
            self.repo_path.parent.mkdir(parents=True, exist_ok=True)
            return Repo.clone_from(
                self.settings.gitops_repo_url,
                self.repo_path,
                branch=self.settings.gitops_default_branch,
            )

        return self.repo()

    def sync_repo_current(self) -> Repo:
        repo = self.ensure_repo_available()
        if repo.is_dirty(untracked_files=True):
            raise RuntimeError(
                "GitOps repository has local changes; refusing to synchronize"
            )

        branch = self.settings.gitops_default_branch
        repo.git.fetch("origin", branch)
        repo.git.checkout(branch)
        repo.git.pull("--ff-only", "origin", branch)
        return repo

    def ensure_repo_current(self) -> Repo:
        return self.sync_repo_current()

    def propose_change(self, request: HomeAssistantChangeRequest) -> HomeAssistantChangeResult:
        safe_path = ensure_editable_ha_path(request.path)
        target = self.repo_path / safe_path
        return HomeAssistantChangeResult(
            branch_name=f"nestor/{safe_path.as_posix().replace('/', '-')}",
            changed_path=safe_path.as_posix(),
            message=request.message,
            dry_run=True,
            summary=f"Prepared change for {target}",
        )

    def validate_changes(self, changes: list[ProposedFileChange]) -> list[ValidationResult]:
        results: list[ValidationResult] = []
        for change in changes:
            try:
                ensure_editable_ha_path(change.path)
            except ValueError as exc:
                results.append(ValidationResult(ok=False, message=str(exc)))
                continue

            if change.path.endswith((".yaml", ".yml")):
                try:
                    safe_load(change.content) if change.content.strip() else None
                except YAMLError as exc:
                    results.append(ValidationResult(ok=False, message=f"{change.path}: {exc}"))
                    continue

            results.append(ValidationResult(ok=True, message=f"{change.path}: ok"))
        return results

    def create_branch_commit_and_push(
        self,
        branch_name: str,
        changes: list[ProposedFileChange],
        commit_message: str,
    ) -> str:
        if not self.settings.github_token:
            raise RuntimeError("GITHUB_TOKEN is required to push a branch")

        repo = self.sync_repo_current()
        if branch_name in [head.name for head in repo.heads]:
            raise RuntimeError(f"Local branch already exists: {branch_name}")

        base_ref = f"origin/{self.settings.gitops_default_branch}"
        repo.git.checkout("-b", branch_name, base_ref)

        for change in changes:
            safe_path = ensure_editable_ha_path(change.path)
            target = self.repo_path / safe_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(change.content, encoding="utf-8")
            repo.index.add([str(target)])

        author = Actor(self.settings.git_author_name, self.settings.git_author_email)
        commit = repo.index.commit(commit_message, author=author, committer=author)

        push_url = self.authenticated_repo_url()
        repo.git.push(push_url, f"{branch_name}:{branch_name}")
        return str(commit.hexsha)

    def authenticated_repo_url(self) -> str:
        token = self.settings.github_token
        if not token:
            raise RuntimeError("GITHUB_TOKEN is required")
        repo_path = self.settings.github_repo
        return f"https://x-access-token:{token}@github.com/{repo_path}.git"


def slugify_branch(value: str, prefix: str = "nestor") -> str:
    slug = sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return f"{prefix}/{slug[:60] or 'ha-change'}"
