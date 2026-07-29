"""Unit tests for configuration loading.

No real key and no network: every test controls the environment explicitly, so
an API key exported in the developer's shell cannot leak in and change a result.
"""

from __future__ import annotations

import pytest

from cytoblast_proto.config import (
    API_KEY_VAR,
    DEFAULT_READ_MODEL,
    READ_MODEL_VAR,
    ConfigError,
    load_config,
)


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Remove both variables so only what a test sets is visible."""
    monkeypatch.delenv(API_KEY_VAR, raising=False)
    monkeypatch.delenv(READ_MODEL_VAR, raising=False)


def _write_env(tmp_path, body: str):
    env_file = tmp_path / ".env"
    env_file.write_text(body, encoding="utf-8")
    return env_file


def test_loads_both_values_from_env_file(tmp_path) -> None:
    env_file = _write_env(
        tmp_path,
        f"{API_KEY_VAR}=sk-ant-test-key\n{READ_MODEL_VAR}=claude-sonnet-5\n",
    )

    config = load_config(env_file=env_file)

    assert config.api_key == "sk-ant-test-key"
    assert config.read_model == "claude-sonnet-5"


def test_read_model_falls_back_to_the_cheap_fast_tier(tmp_path) -> None:
    """An unset model id resolves to the documented default, not to None."""
    env_file = _write_env(tmp_path, f"{API_KEY_VAR}=sk-ant-test-key\n")

    config = load_config(env_file=env_file)

    assert config.read_model == DEFAULT_READ_MODEL


def test_missing_api_key_raises_an_actionable_error(tmp_path) -> None:
    env_file = _write_env(tmp_path, f"{READ_MODEL_VAR}=claude-haiku-4-5\n")

    with pytest.raises(ConfigError) as excinfo:
        load_config(env_file=env_file)

    message = str(excinfo.value)
    assert API_KEY_VAR in message
    assert ".env" in message


def test_blank_api_key_is_treated_as_missing(tmp_path) -> None:
    """A key set to whitespace is a misconfiguration, not a valid credential."""
    env_file = _write_env(tmp_path, f'{API_KEY_VAR}="   "\n')

    with pytest.raises(ConfigError):
        load_config(env_file=env_file)


def test_exported_environment_wins_over_the_file(tmp_path, monkeypatch: pytest.MonkeyPatch) -> None:
    env_file = _write_env(
        tmp_path,
        f"{API_KEY_VAR}=from-file\n{READ_MODEL_VAR}=from-file-model\n",
    )
    monkeypatch.setenv(API_KEY_VAR, "from-shell")
    monkeypatch.setenv(READ_MODEL_VAR, "from-shell-model")

    config = load_config(env_file=env_file)

    assert config.api_key == "from-shell"
    assert config.read_model == "from-shell-model"


def test_blank_read_model_falls_back_rather_than_being_used(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = _write_env(tmp_path, f"{API_KEY_VAR}=sk-ant-test-key\n")
    monkeypatch.setenv(READ_MODEL_VAR, "   ")

    config = load_config(env_file=env_file)

    assert config.read_model == DEFAULT_READ_MODEL
