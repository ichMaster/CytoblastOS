"""Unit tests for the model seam.

Every test drives a fake client: no paid call, no network.
"""

from __future__ import annotations

import anthropic
import httpx
import pytest
from conftest import FakeBlock, FakeClient, FakeMessages, FakeResponse, make_client

from cytoblast_proto.config import Config
from cytoblast_proto.model import (
    DEGRADED_AUTH,
    DEGRADED_CONNECTION,
    DEGRADED_NO_TEXT,
    DEGRADED_RATE_LIMIT,
    MAX_TOKENS,
    AnthropicCompleter,
    Completer,
)

_REQUEST = httpx.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(kind: type, status: int) -> Exception:
    """Build a real SDK status error without touching the network."""
    return kind(
        "from the test",
        response=httpx.Response(status, request=_REQUEST),
        body=None,
    )


def test_returns_the_models_text(config: Config) -> None:
    client = make_client("84 GB free of 460 GB.")

    completer = AnthropicCompleter(config, client=client)

    assert completer.complete("be brief", "how much free space?") == "84 GB free of 460 GB."


def test_sends_the_configured_model_and_prompt(config: Config) -> None:
    client = make_client()

    AnthropicCompleter(config, client=client).complete("SYSTEM", "USER")

    (call,) = client.messages.calls
    assert call["model"] == config.read_model
    assert call["max_tokens"] == MAX_TOKENS
    assert call["system"] == "SYSTEM"
    assert call["messages"] == [{"role": "user", "content": "USER"}]


def test_exposes_the_model_id_it_used(config: Config) -> None:
    completer = AnthropicCompleter(config, client=make_client())

    assert completer.model == config.read_model


def test_satisfies_the_completer_protocol(config: Config) -> None:
    completer = AnthropicCompleter(config, client=make_client())

    assert isinstance(completer, Completer)


def test_reads_past_a_leading_non_text_block(config: Config) -> None:
    """A thinking block first must not break the read, and must not be returned."""
    reply = FakeResponse(
        content=[
            FakeBlock("thinking", "internal reasoning"),
            FakeBlock("text", "the answer"),
        ]
    )
    client = FakeClient(messages=FakeMessages(reply=reply))

    result = AnthropicCompleter(config, client=client).complete("s", "u")

    assert result == "the answer"


@pytest.mark.parametrize(
    "content",
    [
        [],
        [FakeBlock("thinking", "reasoning only")],
        [FakeBlock("text", "   ")],
    ],
    ids=["no-blocks", "no-text-block", "blank-text"],
)
def test_a_response_without_usable_text_degrades(config: Config, content: list) -> None:
    client = FakeClient(messages=FakeMessages(reply=FakeResponse(content=content)))

    result = AnthropicCompleter(config, client=client).complete("s", "u")

    assert result == DEGRADED_NO_TEXT


def test_auth_failure_degrades_to_an_actionable_message(config: Config) -> None:
    client = make_client(error=_status_error(anthropic.AuthenticationError, 401))

    result = AnthropicCompleter(config, client=client).complete("s", "u")

    assert result == DEGRADED_AUTH
    assert "ANTHROPIC_API_KEY" in result


def test_rate_limit_degrades(config: Config) -> None:
    client = make_client(error=_status_error(anthropic.RateLimitError, 429))

    assert AnthropicCompleter(config, client=client).complete("s", "u") == DEGRADED_RATE_LIMIT


def test_connection_failure_degrades(config: Config) -> None:
    client = make_client(error=anthropic.APIConnectionError(request=_REQUEST))

    assert AnthropicCompleter(config, client=client).complete("s", "u") == DEGRADED_CONNECTION


def test_other_status_errors_degrade_with_the_code(config: Config) -> None:
    client = make_client(error=_status_error(anthropic.InternalServerError, 500))

    result = AnthropicCompleter(config, client=client).complete("s", "u")

    assert "500" in result
    assert "error" in result.lower()


def test_no_failure_path_raises(config: Config) -> None:
    """The chat must never see an exception from this seam."""
    errors = [
        _status_error(anthropic.AuthenticationError, 401),
        _status_error(anthropic.RateLimitError, 429),
        _status_error(anthropic.InternalServerError, 500),
        _status_error(anthropic.BadRequestError, 400),
        anthropic.APIConnectionError(request=_REQUEST),
    ]

    for error in errors:
        completer = AnthropicCompleter(config, client=make_client(error=error))
        assert isinstance(completer.complete("s", "u"), str)
