"""Integration tests for the Textual chat, driven by the test pilot.

`respond` is stubbed, so no model call and no subprocess: the UI is exercised,
not the machine.
"""

from __future__ import annotations

import asyncio

import pytest

from cytoblast_proto import app as app_module
from cytoblast_proto.app import EXIT_COMMANDS, GREETING, ChatApp
from cytoblast_proto.config import ConfigError


def transcript_text(app: ChatApp) -> str:
    """Everything currently rendered in the transcript."""
    return "\n".join(str(widget.content) for widget in app.query(".message"))


async def settle(pilot, times: int = 6) -> None:
    """Let the worker thread finish and the UI repaint."""
    for _ in range(times):
        await pilot.pause()
        await asyncio.sleep(0.02)


async def ask(pilot, app: ChatApp, question: str) -> None:
    app.query_one("#question").value = question
    await pilot.press("enter")
    await settle(pilot)


# --------------------------------------------------------------------------- #
# The phase DoD, through the UI
# --------------------------------------------------------------------------- #


async def test_a_question_and_its_answer_both_appear_in_the_transcript() -> None:
    app = ChatApp(respond=lambda q: "You have 3.9 GB left.")

    async with app.run_test() as pilot:
        await ask(pilot, app, "how much free space is left")

        rendered = transcript_text(app)
        assert "how much free space is left" in rendered
        assert "You have 3.9 GB left." in rendered


async def test_both_dod_questions_round_trip_through_the_ui() -> None:
    seen: list[str] = []

    def respond(question: str) -> str:
        seen.append(question)
        return f"answer to {question}"

    app = ChatApp(respond=respond)

    async with app.run_test() as pilot:
        await ask(pilot, app, "how much free space is left")
        await ask(pilot, app, "why is it slow")

        assert seen == ["how much free space is left", "why is it slow"]
        rendered = transcript_text(app)
        assert "answer to how much free space is left" in rendered
        assert "answer to why is it slow" in rendered


async def test_the_greeting_names_what_can_be_asked() -> None:
    app = ChatApp(respond=lambda q: "unused")

    async with app.run_test() as pilot:
        await pilot.pause()

        rendered = transcript_text(app)
        assert rendered.startswith(GREETING.splitlines()[0])
        assert "disk space" in rendered
        assert "CPU" in rendered


async def test_user_and_agent_messages_are_visually_distinguishable() -> None:
    app = ChatApp(respond=lambda q: "the answer")

    async with app.run_test() as pilot:
        await ask(pilot, app, "how much disk space")

        assert app.query(".message.you")
        assert app.query(".message.agent")


# --------------------------------------------------------------------------- #
# Input handling
# --------------------------------------------------------------------------- #


async def test_the_input_is_cleared_after_submitting() -> None:
    app = ChatApp(respond=lambda q: "the answer")

    async with app.run_test() as pilot:
        await ask(pilot, app, "how much disk space")

        assert app.query_one("#question").value == ""


async def test_blank_input_is_ignored_and_never_reaches_the_turn() -> None:
    calls: list[str] = []
    app = ChatApp(respond=lambda q: calls.append(q) or "x")

    async with app.run_test() as pilot:
        await ask(pilot, app, "   ")

        assert calls == []


async def test_input_is_disabled_while_a_turn_is_in_flight() -> None:
    release = asyncio.Event()

    def slow(question: str) -> str:
        asyncio.run(asyncio.sleep(0))  # yield inside the thread
        while not release.is_set():
            pass
        return "eventually"

    app = ChatApp(respond=slow)

    async with app.run_test() as pilot:
        app.query_one("#question").value = "why is it slow"
        await pilot.press("enter")
        await pilot.pause()

        assert app.query_one("#question").disabled is True
        assert app.query_one("#thinking").has_class("busy")

        release.set()
        await settle(pilot, times=12)

        assert app.query_one("#question").disabled is False
        assert not app.query_one("#thinking").has_class("busy")


# --------------------------------------------------------------------------- #
# Failure rendering
# --------------------------------------------------------------------------- #


async def test_a_degraded_answer_is_rendered_like_any_other() -> None:
    """The turn already degrades to a string; the UI just shows it."""
    app = ChatApp(respond=lambda q: "The model is rate limited right now.")

    async with app.run_test() as pilot:
        await ask(pilot, app, "how much disk space")

        assert "The model is rate limited right now." in transcript_text(app)


async def test_an_exception_in_the_turn_is_shown_not_crashed() -> None:
    def explode(question: str) -> str:
        raise RuntimeError("the turn blew up")

    app = ChatApp(respond=explode)

    async with app.run_test() as pilot:
        await ask(pilot, app, "how much disk space")

        rendered = transcript_text(app)
        assert "Something went wrong" in rendered
        assert "the turn blew up" in rendered
        assert app.query(".message.failed")
        # Still usable afterwards.
        assert app.query_one("#question").disabled is False


# --------------------------------------------------------------------------- #
# Exit handling
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize("command", sorted(EXIT_COMMANDS))
async def test_exit_commands_quit(command: str) -> None:
    app = ChatApp(respond=lambda q: "unused")

    async with app.run_test() as pilot:
        app.query_one("#question").value = command
        await pilot.press("enter")
        await pilot.pause()

        assert not app.is_running


async def test_an_exit_command_never_reaches_the_turn() -> None:
    calls: list[str] = []
    app = ChatApp(respond=lambda q: calls.append(q) or "x")

    async with app.run_test() as pilot:
        app.query_one("#question").value = "/exit"
        await pilot.press("enter")
        await pilot.pause()

        assert calls == []


@pytest.mark.parametrize("key", ["ctrl+c", "ctrl+d"])
async def test_the_quit_keys_quit(key: str) -> None:
    """Textual 8 does not quit on ctrl+c by default; both are bound explicitly."""
    app = ChatApp(respond=lambda q: "unused")

    async with app.run_test() as pilot:
        await pilot.press(key)
        await pilot.pause()

        assert not app.is_running


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #


def test_a_missing_api_key_is_reported_before_the_ui_starts(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """No stack trace, and no half-drawn screen to read it over."""
    started: list[bool] = []

    def refuse() -> None:
        raise ConfigError("ANTHROPIC_API_KEY is not set. Copy .env.example to .env")

    monkeypatch.setattr(app_module, "load_config", refuse)
    monkeypatch.setattr(ChatApp, "run", lambda self: started.append(True))

    assert app_module.main() == 1
    assert started == []  # the app never opened
    stderr = capsys.readouterr().err
    assert "Cannot start" in stderr
    assert "ANTHROPIC_API_KEY" in stderr


def test_a_good_configuration_starts_the_app(monkeypatch: pytest.MonkeyPatch) -> None:
    from cytoblast_proto.config import Config

    started: list[bool] = []
    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda: Config(api_key="not-a-real-key", read_model="claude-haiku-4-5"),
    )
    monkeypatch.setattr(ChatApp, "run", lambda self: started.append(True))

    assert app_module.main() == 0
    assert started == [True]


async def test_quitting_cancels_a_turn_in_flight(monkeypatch: pytest.MonkeyPatch) -> None:
    """An in-flight worker must be cancelled, not orphaned."""
    app = ChatApp(respond=lambda q: "unused")
    cancelled: list[bool] = []

    async with app.run_test() as pilot:
        monkeypatch.setattr(
            type(app.workers),
            "cancel_all",
            lambda self: cancelled.append(True),
        )

        await app.action_quit()
        # Counted inside the context: app shutdown cancels workers again on the
        # way out, which would mask whether action_quit did it.
        cancelled_by_quit = len(cancelled)
        await pilot.pause()

    assert cancelled_by_quit == 1
    assert not app.is_running
