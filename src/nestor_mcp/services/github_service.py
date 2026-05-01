import httpx

from nestor_mcp.config import get_settings


class GitHubService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def create_pull_request(self, branch_name: str, title: str, body: str) -> str:
        if not self.settings.github_token:
            raise RuntimeError("GITHUB_TOKEN is required to create a pull request")

        api_url = str(self.settings.github_api_url).rstrip("/")
        url = f"{api_url}/repos/{self.settings.github_repo}/pulls"
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {self.settings.github_token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        payload = {
            "title": title,
            "head": branch_name,
            "base": self.settings.gitops_default_branch,
            "body": body,
        }

        with httpx.Client(timeout=30) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        return str(data["html_url"])
