"""Devin API adapter.

Implements the two calls described in the Devin API reference
(https://docs.devin.ai/api-reference/overview) and nothing else.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class DevinSession:
    """Projection of a Devin session used by the core layer."""

    session_id: str
    status_enum: str | None = None
    url: str | None = None
    structured_output: dict[str, Any] | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "DevinSession":
        structured_output = payload.get("structured_output")
        if isinstance(structured_output, str):
            try:
                structured_output = json.loads(structured_output)
            except json.JSONDecodeError:
                structured_output = {"raw": structured_output}
        if structured_output is not None and not isinstance(structured_output, dict):
            structured_output = {"raw": structured_output}
        return cls(
            session_id=str(payload.get("session_id") or payload.get("id") or ""),
            status_enum=payload.get("status_enum") or payload.get("status"),
            url=payload.get("url"),
            structured_output=structured_output,
        )


class DevinClient:
    """Adapter for session creation and polling."""

    def __init__(
        self,
        api_key: str,
        api_base: str = "https://api.devin.ai/v1",
        timeout: float = 30.0,
        client: httpx.Client | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_base = api_base.rstrip("/")
        self._timeout = timeout
        self._client = client

    def create_session(self, prompt: str, idempotent: bool = True) -> DevinSession:
        """Create a Devin session for ``prompt``."""
        response = self._request(
            "POST",
            f"{self._api_base}/sessions",
            json={"prompt": prompt, "idempotent": idempotent},
        )
        response.raise_for_status()
        return DevinSession.from_payload(response.json())

    def get_session(self, session_id: str) -> DevinSession:
        """Fetch the current state of a Devin session."""
        response = self._request("GET", f"{self._api_base}/session/{session_id}")
        response.raise_for_status()
        return DevinSession.from_payload(response.json())

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        if self._client is not None:
            return self._client.request(method, url, headers=self._headers(), **kwargs)
        with httpx.Client(timeout=self._timeout) as client:
            return client.request(method, url, headers=self._headers(), **kwargs)
