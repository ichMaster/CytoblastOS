"""The terminal chat: a Textual app over one turn.

The only module that touches Textual, so everything beneath it stays importable
and testable without a terminal. Disposable with the rest of v0 — the surface
that survives into v1 is the *scenario*, not this code.

The model call runs in a worker thread, so the UI keeps redrawing and scrolling
while an answer is in flight.
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Callable
from functools import partial

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import VerticalScroll
from textual.widgets import Footer, Header, Input, Static
from textual.worker import Worker, WorkerCancelled, WorkerFailed

from .config import ConfigError, load_config
from .model import AnthropicCompleter
from .turn import answer

#: Everything the app needs from the rest of the prototype: a question in, an
#: answer out. Injected, so tests drive the UI without a model or a subprocess.
Responder = Callable[[str], str]

#: Typed instead of asked, so it never reaches the model.
EXIT_COMMANDS = frozenset({"/exit", "/quit", "/q"})

GREETING = (
    "CytoblastOS prototype. I can answer three things about this machine:\n"
    "  · how much disk space is left\n"
    "  · what is using the CPU and memory\n"
    "  · how long it has been up, and who is logged in\n"
    "Ask in any language. Ctrl+C, Ctrl+D, or /exit to quit."
)

THINKING = "…reading the machine"


class ChatApp(App[None]):
    """A scrollable transcript with an input line."""

    TITLE = "CytoblastOS"
    SUB_TITLE = "v0 prototype"

    # Textual 8 binds ctrl+c to a "press ctrl+q to quit" hint rather than to
    # quit, and ctrl+d is unbound. Both are reflexes in a terminal chat, so they
    # are bound explicitly — priority, to beat the system binding and the Input.
    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True, show=True),
        Binding("ctrl+d", "quit", "Quit", priority=True, show=False),
    ]

    CSS = """
    #transcript {
        height: 1fr;
        padding: 1 2;
        background: $surface;
    }
    .message {
        margin-bottom: 1;
    }
    .you {
        color: $accent;
        text-style: bold;
    }
    .agent {
        color: $foreground;
    }
    .system {
        color: $text-muted;
    }
    .failed {
        color: $error;
    }
    #thinking {
        height: auto;
        padding: 0 2;
        color: $text-muted;
        text-style: italic;
        display: none;
    }
    #thinking.busy {
        display: block;
    }
    #question {
        dock: bottom;
        margin: 0 1 1 1;
    }
    """

    def __init__(self, respond: Responder) -> None:
        """Build the app.

        Args:
            respond: Takes the typed question and returns the answer. Blocking —
                it is called on a worker thread, never on the event loop.
        """
        super().__init__()
        self._respond = respond

    # ---------------------------------------------------------------- layout

    def compose(self) -> ComposeResult:
        yield Header()
        yield VerticalScroll(id="transcript")
        yield Static(THINKING, id="thinking")
        yield Input(placeholder="Ask about this machine…", id="question")
        yield Footer()

    def on_mount(self) -> None:
        self._say(GREETING, "system")
        self.query_one("#question", Input).focus()

    # --------------------------------------------------------------- helpers

    @property
    def transcript(self) -> VerticalScroll:
        return self.query_one("#transcript", VerticalScroll)

    def _at_bottom(self) -> bool:
        """Whether the transcript is scrolled to the newest message.

        Checked *before* mounting, so a user who has scrolled up to read is not
        yanked back down by an arriving answer.
        """
        transcript = self.transcript
        return transcript.scroll_offset.y >= transcript.max_scroll_y - 1

    def _say(self, text: str, role: str) -> None:
        """Append one message to the transcript."""
        follow = self._at_bottom()
        prefix = {"you": "you  ", "agent": "cyto ", "system": "", "failed": "cyto "}[role]
        message = Static(f"{prefix}{text}" if prefix else text, classes=f"message {role}")
        self.transcript.mount(message)
        if follow:
            # call_after_refresh, so the new height is known before scrolling.
            self.call_after_refresh(self.transcript.scroll_end, animate=False)

    def _set_busy(self, busy: bool) -> None:
        """Show the thinking line and stop taking input while a turn runs."""
        self.query_one("#thinking", Static).set_class(busy, "busy")
        question = self.query_one("#question", Input)
        question.disabled = busy
        if not busy:
            question.focus()

    # ---------------------------------------------------------------- events

    def on_input_submitted(self, event: Input.Submitted) -> None:
        question = event.value.strip()
        event.input.value = ""

        if not question:
            return

        if question.lower() in EXIT_COMMANDS:
            self.exit()
            return

        self._say(question, "you")
        self._set_busy(True)
        self._answer(question)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        """Stop the thinking line once the worker is no longer running."""
        if event.worker.name == "_answer" and not event.worker.is_running:
            self._set_busy(False)

    # ---------------------------------------------------------------- worker

    async def _answer_now(self, question: str) -> str:
        """Run the blocking turn off the event loop."""
        return await asyncio.to_thread(self._respond, question)

    def _answer(self, question: str) -> Worker[None]:
        """Start the turn as an exclusive worker, so a quit can cancel it."""
        return self.run_worker(
            self._deliver(question),
            name="_answer",
            group="turn",
            exclusive=True,
        )

    async def _deliver(self, question: str) -> None:
        try:
            text = await self._answer_now(question)
        except (WorkerCancelled, WorkerFailed):  # pragma: no cover - quit path
            return
        except Exception as exc:  # noqa: BLE001 - a crash must not take the UI down
            self._say(f"Something went wrong answering that: {exc}", "failed")
            return
        self._say(text, "agent")

    # ------------------------------------------------------------------ quit

    async def action_quit(self) -> None:
        """Cancel any turn in flight, then exit — never orphan a worker."""
        self.workers.cancel_all()
        self.exit()


def main(argv: list[str] | None = None) -> int:
    """Entry point. Reports a bad configuration before the screen is drawn."""
    del argv  # no options yet
    try:
        config = load_config()
    except ConfigError as exc:
        # Before the UI starts, so the message is readable rather than painted
        # over a half-drawn screen.
        print(f"Cannot start: {exc}", file=sys.stderr)
        return 1

    completer = AnthropicCompleter(config)
    ChatApp(respond=partial(answer, completer=completer)).run()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
