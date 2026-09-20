"""Devin adapter transport behaviour."""

from __future__ import annotations

import json

import httpx
import pytest

from app.adapters.devin_client import DevinClient


def make_client(transport: httpx.MockTransport) -> DevinClient:
    return DevinClient(api_key="test-devin-key", client=httpx.Client(transport=transport))


def test_create_session_posts_prompt_with_idempotent_flag() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers["Authorization"]
        seen["body"] = json.loads(request.read())
        return httpx.Response(
            200,
            json={
                "session_id": "devin-session-1",
                "url": "https://app.devin.ai/sessions/devin-session-1",
                "status_enum": "running",
            },
        )

    session = make_client(httpx.MockTransport(handler)).create_session("fix issue 101")

    assert seen["url"] == "https://api.devin.ai/v1/sessions"
    assert seen["auth"] == "Bearer test-devin-key"
    assert seen["body"] == {"prompt": "fix issue 101", "idempotent": True}
    assert session.session_id == "devin-session-1"
    assert session.status_enum == "running"


def test_get_session_parses_structured_output() -> None:
    seen: dict[str, object] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(
            200,
            json={
                "session_id": "devin-session-1",
                "status_enum": "finished",
                "structured_output": {
                    "pr_url": "https://github.com/namohkwan/superset/pull/7",
                    "result": "pass",
                },
            },
        )

    session = make_client(httpx.MockTransport(handler)).get_session("devin-session-1")

    assert seen["url"] == "https://api.devin.ai/v1/session/devin-session-1"
    assert session.status_enum == "finished"
    assert session.structured_output == {
        "pr_url": "https://github.com/namohkwan/superset/pull/7",
        "result": "pass",
    }


def test_structured_output_given_as_json_string_is_parsed() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "session_id": "s1",
                "status_enum": "finished",
                "structured_output": '{"pr_url": "u", "result": "fail"}',
            },
        )
    )

    session = make_client(transport).get_session("s1")

    assert session.structured_output == {"pr_url": "u", "result": "fail"}


def test_pull_request_url_is_extracted_from_session_payload() -> None:
    transport = httpx.MockTransport(
        lambda request: httpx.Response(
            200,
            json={
                "session_id": "s1",
                "status_enum": "blocked",
                "pull_requests": [{"url": "https://github.com/o/r/pull/2"}],
            },
        )
    )

    session = make_client(transport).get_session("s1")

    assert session.pull_request_url == "https://github.com/o/r/pull/2"


def test_create_session_raises_on_error_status() -> None:
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={}))

    with pytest.raises(httpx.HTTPStatusError):
        make_client(transport).create_session("prompt")
