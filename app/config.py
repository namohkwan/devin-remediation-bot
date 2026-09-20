"""Central configuration.

This module is the ONLY place in the application that reads environment
variables. Every other layer receives configuration through
:func:`get_settings` or explicit constructor arguments, which keeps secret
handling auditable in a single file.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

REQUIRED_ENV_VARS: tuple[str, ...] = (
    "DEVIN_API_KEY",
    "GITHUB_TOKEN",
    "GITHUB_WEBHOOK_SECRET",
    "TARGET_REPO",
)

DEFAULT_DEVIN_API_BASE = "https://api.devin.ai/v1"
DEFAULT_GITHUB_API_BASE = "https://api.github.com"
DEFAULT_DATABASE_PATH = "data/remediation.db"
DEFAULT_TRIGGER_LABEL = "devin-fix"


class ConfigurationError(RuntimeError):
    """Raised at startup when required configuration is missing."""


@dataclass(frozen=True)
class Settings:
    """Immutable application settings.

    Secret values are never logged or rendered; only their presence is
    reported by :meth:`describe`.
    """

    devin_api_key: str
    github_token: str
    github_webhook_secret: str
    target_repo: str
    devin_api_base: str = DEFAULT_DEVIN_API_BASE
    github_api_base: str = DEFAULT_GITHUB_API_BASE
    database_path: str = DEFAULT_DATABASE_PATH
    trigger_label: str = DEFAULT_TRIGGER_LABEL
    request_timeout_seconds: float = 30.0

    def describe(self) -> dict[str, str]:
        """Return a redacted view suitable for logs and the dashboard."""
        return {
            "target_repo": self.target_repo,
            "devin_api_base": self.devin_api_base,
            "github_api_base": self.github_api_base,
            "database_path": self.database_path,
            "trigger_label": self.trigger_label,
            "devin_api_key": "***configured***",
            "github_token": "***configured***",
            "github_webhook_secret": "***configured***",
        }


def load_settings(env: dict[str, str] | None = None) -> Settings:
    """Build :class:`Settings`, failing fast when anything required is absent.

    ``env`` defaults to the process environment after ``.env`` is loaded, and
    is injectable so tests never mutate global state.
    """
    if env is None:
        load_dotenv(override=False)
        env = dict(os.environ)

    missing = [name for name in REQUIRED_ENV_VARS if not (env.get(name) or "").strip()]
    if missing:
        raise ConfigurationError(
            "Missing required environment variable(s): "
            + ", ".join(missing)
            + ". Copy .env.example to .env and provide real values, or export "
            "them in the runtime environment. Secrets must never be committed."
        )

    return Settings(
        devin_api_key=env["DEVIN_API_KEY"].strip(),
        github_token=env["GITHUB_TOKEN"].strip(),
        github_webhook_secret=env["GITHUB_WEBHOOK_SECRET"].strip(),
        target_repo=env["TARGET_REPO"].strip(),
        devin_api_base=(env.get("DEVIN_API_BASE") or DEFAULT_DEVIN_API_BASE).strip(),
        github_api_base=(env.get("GITHUB_API_BASE") or DEFAULT_GITHUB_API_BASE).strip(),
        database_path=(env.get("DATABASE_PATH") or DEFAULT_DATABASE_PATH).strip(),
        trigger_label=(env.get("TRIGGER_LABEL") or DEFAULT_TRIGGER_LABEL).strip(),
        request_timeout_seconds=float(env.get("REQUEST_TIMEOUT_SECONDS") or 30.0),
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return process-wide settings, validated on first access."""
    return load_settings()


def reset_settings_cache() -> None:
    """Clear the cached settings (used by tests and CLI re-entry)."""
    get_settings.cache_clear()
