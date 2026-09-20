"""GitHub adapter transport behaviour."""

from __future__ import annotations

import httpx
import pytest

from app.adapters.github_client import GitHubClient, GitHubIssue

ISSUE_PAYLOAD = {
    "number": 101,
    "title": "Chart fails to render",
    "body": "Stack trace here",
    "html_url": "https://github.com/namohkwan/superset/issues/101",
    "labels": [{"name": "bug"}, {"name": "devin-fix"}],
}


def make_client(handler: httpx.MockTransport) -> GitHubClient:
    return GitHubClient(
        token="test-github-token",
        repo="namohkwan/superset",
        client=httpx.Client(transport=handler),
    )


def test_get_issue_builds_url_and_auth_header() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        return httpx.Response(200, json=ISSUE_PAYLOAD)

    issue = make_client(httpx.MockTransport(handler)).get_issue(101)

    assert seen["url"] == "https://api.github.com/repos/namohkwan/superset/issues/101"
    assert seen["auth"] == "Bearer test-github-token"
    assert issue == GitHubIssue(
        number=101,
        title="Chart fails to render",
        body="Stack trace here",
        labels=("bug", "devin-fix"),
        html_url="https://github.com/namohkwan/superset/issues/101",
    )


def test_get_issue_raises_on_error_status() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(404, json={}))

    with pytest.raises(httpx.HTTPStatusError):
        make_client(transport).get_issue(999)


def test_issue_payload_tolerates_null_body() -> None:
    issue = GitHubIssue.from_payload({"number": 5, "title": "t", "body": None})

    assert issue.body == ""
    assert issue.labels == ()
