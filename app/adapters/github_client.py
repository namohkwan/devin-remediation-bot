"""GitHub REST adapter.

Contains transport concerns only: no business rules live here, so a change in
the GitHub API surface is absorbed by this module alone.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class GitHubIssue:
    """Minimal issue projection consumed by the core layer."""

    number: int
    title: str
    body: str
    labels: tuple[str, ...] = ()
    html_url: str | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "GitHubIssue":
        labels = tuple(
            label["name"]
            for label in payload.get("labels", [])
            if isinstance(label, dict) and label.get("name")
        )
        return cls(
            number=int(payload["number"]),
            title=payload.get("title") or "",
            body=payload.get("body") or "",
            labels=labels,
            html_url=payload.get("html_url"),
        )


class GitHubClient:
    """Adapter exposing the single GitHub call the bot needs."""

    def __init__(
        self,
        token: str,
        repo: str,
        api_base: str = "https://api.github.com",
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._token = token
        self._repo = repo
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout
        self._client = client

    def get_issue(self, number: int) -> GitHubIssue:
        """Fetch a single issue from the configured target repository."""
        url = f"{self._api_base}/repos/{self._repo}/issues/{number}"
        response = self._request("GET", url)
        response.raise_for_status()
        return GitHubIssue.from_payload(response.json())

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self._client is not None:
            return self._client.request(method, url, headers=self._headers(), **kwargs)
        with httpx.Client(timeout=self._timeout) as client:
            return client.request(method, url, headers=self._headers(), **kwargs)
