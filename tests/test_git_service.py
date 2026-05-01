from pathlib import Path

from git import Repo

from nestor_mcp.models.ha_change import HomeAssistantChangeRequest, ProposedFileChange
from nestor_mcp.services.git_service import GitService, slugify_branch


def test_git_service_proposes_dry_run_change(tmp_path: Path) -> None:
    service = GitService(repo_path=tmp_path)
    result = service.propose_change(
        HomeAssistantChangeRequest(
            path="packages/light.yaml",
            content="light: []",
            message="Add light package",
        )
    )

    assert result.dry_run is True
    assert result.changed_path == "packages/light.yaml"
    assert result.branch_name == "nestor/packages-light.yaml"


def test_git_service_validates_yaml_content(tmp_path: Path) -> None:
    service = GitService(repo_path=tmp_path)

    results = service.validate_changes(
        [ProposedFileChange(path="packages/areas/salon.yaml", content="automation:\n  - id: ok")]
    )

    assert results[0].ok is True


def test_git_service_rejects_invalid_yaml(tmp_path: Path) -> None:
    service = GitService(repo_path=tmp_path)

    results = service.validate_changes(
        [ProposedFileChange(path="packages/areas/salon.yaml", content="automation: [")]
    )

    assert results[0].ok is False


def test_slugify_branch() -> None:
    assert slugify_branch("Éteindre Salon à Minuit").startswith("nestor/teindre-salon-minuit")


def test_git_service_rejects_non_empty_non_repo(tmp_path: Path) -> None:
    repo_path = tmp_path / "ha-config"
    repo_path.mkdir()
    (repo_path / "README.md").write_text("not a repo", encoding="utf-8")
    service = GitService(repo_path=repo_path)

    try:
        service.ensure_repo_current()
    except RuntimeError as exc:
        assert "not a git repository" in str(exc)
    else:
        raise AssertionError("Expected RuntimeError")


def test_git_service_accepts_existing_repo(tmp_path: Path) -> None:
    repo_path = tmp_path / "ha-config"
    repo_path.mkdir()
    Repo.init(repo_path)
    service = GitService(repo_path=repo_path)

    repo = service.repo()

    assert repo.working_tree_dir == str(repo_path)
