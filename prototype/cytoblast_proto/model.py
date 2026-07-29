"""The single place the prototype talks to a model.

Deliberately small: v0 makes direct calls with no contracts (ROADMAP §v0). The
real model seam — with cheap/strong tier routing and a journal record per turn —
arrives in v1.3, and nothing here is meant to survive into it.

Two rules this module exists to enforce:

- **The client is injected, never constructed at import time**, so every test in
  the repository substitutes a fake. No paid call is ever made in CI
  (ARCHITECTURE §Testing and CI).
- **A model failure degrades, never blocks** (ARCHITECTURE §Error handling and
  resilience). Every failure comes back as a short readable string the chat can
  print, so a turn ends with an explanation rather than a traceback.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import anthropic

from .config import Config

#: Answers appear in a terminal and are meant to be short. Generous enough that
#: a three-sentence answer is never truncated, small enough to stay cheap.
MAX_TOKENS = 1024

# User-facing degraded results. Each says what happened and what would unblock
# it, because the person reading it is the person who can fix it.
DEGRADED_AUTH = (
    "The model rejected the API key. Check ANTHROPIC_API_KEY in .env — it may be "
    "missing, expired, or from the wrong account."
)
DEGRADED_RATE_LIMIT = "The model is rate limited right now. Ask again in a moment."
DEGRADED_CONNECTION = "Could not reach the model. Check your network connection and ask again."
DEGRADED_NO_TEXT = "The model replied without any text, so there is nothing to show."


@runtime_checkable
class Completer(Protocol):
    """The seam callers depend on, so a fake can stand in for the real client."""

    #: The model id this completer talks to, so a caller can surface it.
    model: str

    def complete(self, system: str, user: str) -> str:
        """Return the model's answer, or a readable message if it failed."""
        ...


def _first_text(response: object) -> str:
    """Pull the first text block out of a response.

    Never indexes `content[0]`: a response may lead with a thinking block or any
    other block type, depending on the configured model.
    """
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            text = (getattr(block, "text", "") or "").strip()
            if text:
                return text
    return DEGRADED_NO_TEXT


class AnthropicCompleter:
    """A `Completer` backed by the official Anthropic SDK."""

    def __init__(self, config: Config, client: anthropic.Anthropic | None = None) -> None:
        """Build a completer.

        Args:
            config: Supplies the API key and the read-path model id.
            client: An existing client, or a fake in tests. When omitted, a real
                client is constructed — which is why callers in tests always pass
                one.
        """
        self.model = config.read_model
        self._client = client if client is not None else anthropic.Anthropic(api_key=config.api_key)

    def complete(self, system: str, user: str) -> str:
        """Send one prompt and return the answer, or a degraded message."""
        try:
            response = self._client.messages.create(
                model=self.model,
                max_tokens=MAX_TOKENS,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.AuthenticationError:
            return DEGRADED_AUTH
        except anthropic.RateLimitError:
            return DEGRADED_RATE_LIMIT
        except anthropic.APIStatusError as exc:
            return (
                f"The model returned an error (HTTP {exc.status_code}). Ask again, "
                f"or check https://status.anthropic.com if it persists."
            )
        except anthropic.APIConnectionError:
            return DEGRADED_CONNECTION

        return _first_text(response)
