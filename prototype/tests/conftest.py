"""Shared test doubles for the prototype.

The model is mocked everywhere: no test in this repository makes a paid call
(ARCHITECTURE §Testing and CI).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from cytoblast_proto.config import Config


@dataclass
class FakeBlock:
    """One content block, with only the fields the code under test reads."""

    type: str
    text: str = ""


@dataclass
class FakeResponse:
    """Stands in for an SDK `Message`."""

    content: list[FakeBlock]


@dataclass
class FakeMessages:
    """The `client.messages` namespace."""

    reply: FakeResponse | None = None
    error: Exception | None = None
    calls: list[dict] = field(default_factory=list)

    def create(self, **kwargs) -> FakeResponse:
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        assert self.reply is not None, "FakeMessages needs either a reply or an error"
        return self.reply


@dataclass
class FakeClient:
    """Stands in for `anthropic.Anthropic`."""

    messages: FakeMessages


def make_client(text: str = "an answer", error: Exception | None = None) -> FakeClient:
    """Build a fake client that answers with `text`, or raises `error`."""
    reply = None if error is not None else FakeResponse(content=[FakeBlock("text", text)])
    return FakeClient(messages=FakeMessages(reply=reply, error=error))


@dataclass
class FakeCompleter:
    """A `Completer` that returns a canned answer and records its prompts."""

    answer: str = "an answer"
    model: str = "fake-model"
    prompts: list[tuple[str, str]] = field(default_factory=list)

    def complete(self, system: str, user: str) -> str:
        self.prompts.append((system, user))
        return self.answer


@pytest.fixture
def config() -> Config:
    """Configuration that never reaches the network."""
    return Config(api_key="not-a-real-key", read_model="claude-haiku-4-5")
