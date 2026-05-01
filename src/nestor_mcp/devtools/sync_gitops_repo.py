from __future__ import annotations

from collections.abc import Sequence

from nestor_mcp.services.git_service import GitService


def main(argv: Sequence[str] | None = None) -> int:
    del argv
    repo = GitService().sync_repo_current()
    commit = repo.head.commit.hexsha
    branch = repo.active_branch.name
    print(f"GitOps repository synchronized: {branch} {commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
