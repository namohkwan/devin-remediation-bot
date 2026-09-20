"""Configuration must fail fast when secrets are missing."""

from __future__ import annotations

import pytest

from app.config import REQUIRED_ENV_VARS, ConfigurationError, load_settings
from tests.conftest import TEST_ENV


def test_load_settings_returns_all_values() -> None:
    settings = load_settings(dict(TEST_ENV))

    assert settings.devin_api_key == "test-devin-key"
    assert settings.github_token == "test-github-token"
    assert settings.github_webhook_secret == "test-webhook-secret"
    assert settings.target_repo == "namohkwan/superset"
    assert settings.devin_api_base == "https://api.devin.ai/v1"
    assert settings.trigger_label == "devin-fix"


@pytest.mark.parametrize("missing", REQUIRED_ENV_VARS)
def test_missing_env_var_fails_fast(missing: str) -> None:
    env = dict(TEST_ENV)
    del env[missing]

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(env)

    assert missing in str(excinfo.value)


def test_blank_env_var_is_treated_as_missing() -> None:
    env = dict(TEST_ENV, DEVIN_API_KEY="   ")

    with pytest.raises(ConfigurationError) as excinfo:
        load_settings(env)

    assert "DEVIN_API_KEY" in str(excinfo.value)


def test_describe_redacts_secrets() -> None:
    described = load_settings(dict(TEST_ENV)).describe()

    assert "test-devin-key" not in str(described)
    assert "test-github-token" not in str(described)
    assert described["devin_api_key"] == "***configured***"
