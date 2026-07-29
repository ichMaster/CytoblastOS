"""Configuration for the v0 prototype: the model key and the model id.

Secrets are read from `.env`, which is never committed (ARCHITECTURE
§Configuration and secrets). Nothing here is hardcoded — the model id is a
config value precisely so it can be swapped without touching code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

#: Environment variable holding the Anthropic API key.
API_KEY_VAR = "ANTHROPIC_API_KEY"

#: Environment variable selecting the model used for read paths.
READ_MODEL_VAR = "CYTO_MODEL_READ"

#: Every v0.1 path is a read, and read paths run on the cheap fast tier
#: (ARCHITECTURE §Trust modes). The hosting and cheap/strong routing rule is not
#: formally decided until v1.5 — until then this default is the whole rule.
DEFAULT_READ_MODEL = "claude-haiku-4-5"


class ConfigError(RuntimeError):
    """Configuration is missing or unusable.

    Carries a message that says what to fix, so a misconfigured prototype fails
    at startup with an instruction rather than with a traceback from inside the
    SDK.
    """


@dataclass(frozen=True)
class Config:
    """Resolved configuration for one run of the prototype."""

    api_key: str
    read_model: str


def load_config(env_file: Path | None = None) -> Config:
    """Load configuration from the environment, backed by `.env`.

    Args:
        env_file: Explicit `.env` path. When omitted, python-dotenv searches
            upward from the working directory.

    Returns:
        The resolved configuration.

    Raises:
        ConfigError: The API key is missing or blank.
    """
    # Real environment variables win over the file: an explicit export is a
    # deliberate override, and CI sets a dummy key without writing a file.
    load_dotenv(dotenv_path=env_file, override=False)

    api_key = (os.environ.get(API_KEY_VAR) or "").strip()
    if not api_key:
        raise ConfigError(
            f"{API_KEY_VAR} is not set. Copy .env.example to .env and add your "
            f"Anthropic API key, or export {API_KEY_VAR} in this shell."
        )

    read_model = (os.environ.get(READ_MODEL_VAR) or "").strip() or DEFAULT_READ_MODEL

    return Config(api_key=api_key, read_model=read_model)
