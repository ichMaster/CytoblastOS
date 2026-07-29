"""One turn: question → reading → answer in the user's language.

This is the phase DoD in one module. The division of labour is deliberate: the
**readings do the knowing** and the **model does the phrasing**. The model is
never asked what is true about the machine, only how to say it.

Selection is **rule-based on purpose**. Real routing belongs to the orchestrator
in v1.3, and a miniature model-driven router here would be scope thrown away
twice — once when v0 is frozen and again when v1.3 lands.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from functools import lru_cache

from .model import Completer
from .readings import (
    Reading,
    read_free_space,
    read_load_and_top,
    read_uptime_health,
)

SYSTEM_PROMPT = """\
You are CytoblastOS, answering a question about the machine you are running on.

- Answer only from the reading supplied below. Never invent or estimate a number,
  a process name, or a date — if it is not in the reading, you do not know it.
- Reply in the same language the question was asked in.
- Be short and concrete: two or three sentences, no preamble, no restating the
  question.
- If the reading failed, say plainly what could not be read and stop. Do not
  guess at what the answer might have been.
"""

#: Returned without calling the model when nothing matches. English only: this
#: prototype cannot translate without a model call, and spending one to say "I
#: don't know" is not worth it. (A finding for the v0.4 SDLC notes.)
FALLBACK = (
    "I can answer three things about this machine: how much disk space is left, "
    "what is using the CPU and memory, and how long it has been up. "
    "Ask me one of those."
)

_APOSTROPHES = "’ʼ`"


@lru_cache(maxsize=256)
def _pattern(keyword: str) -> re.Pattern[str]:
    """A keyword matches at a **word start**, and may match a prefix from there.

    Plain substring matching is not good enough in two languages at once, and
    both failures are silent:

    - `вільн` ("free") is a substring of `повільно` ("slowly"), which sent
      "чому так повільно" to the disk reading.
    - `час роботи` must still match `час роботи системи`.

    A leading `\\b` with no trailing boundary gives stem matching without the
    mid-word collisions: `вільн` matches `вільного` but not `повільно`.
    """
    return re.compile(r"\b" + re.escape(keyword), re.UNICODE)


def _hits(keyword: str, question: str) -> bool:
    return _pattern(keyword).search(question) is not None


@dataclass(frozen=True)
class Topic:
    """One answerable subject: how to recognise it, and how to read it.

    `strong` keywords decide a question on their own ("disk", "memory");
    `weak` keywords only tip a balance ("left", "slow"), so that
    "how much memory is free" resolves to load rather than to disk.
    """

    name: str
    read: Callable[[], Reading]
    strong: tuple[str, ...]
    weak: tuple[str, ...]

    def score(self, question: str) -> int:
        """How strongly this topic matches a normalised question."""
        return sum(2 for k in self.strong if _hits(k, question)) + sum(
            1 for k in self.weak if _hits(k, question)
        )


def default_topics() -> tuple[Topic, ...]:
    """The three subjects v0.1 can answer, bound to the real readings.

    Keywords cover English and Ukrainian — the origin specification is
    Ukrainian, and the DoD asks for answers in the user's language, so
    recognising the question in that language is part of the job. Ukrainian
    keywords are stems, so inflected forms match.
    """
    return (
        Topic(
            name="free space",
            read=read_free_space,
            strong=("disk", "space", "storage", "capacity", "gb", "диск", "місц", "сховищ"),
            weak=("free", "full", "left", "drive", "volume", "вільн", "заповнен", "залиш"),
        ),
        Topic(
            name="load",
            read=read_load_and_top,
            strong=(
                "cpu",
                "memory",
                "ram",
                "load",
                # "freezing" shares its prefix with "free", so a word boundary
                # cannot separate them. It is the stronger signal of the two:
                # a frozen machine is a load question, not a disk question.
                "freez",
                "процесор",
                "пам'ят",
                "навантаж",
                "процес",
            ),
            weak=(
                "slow",
                "sluggish",
                "lag",
                "busy",
                "hang",
                "hog",
                "eating",
                "consum",
                "performance",
                "повільн",
                "гальм",
                "завис",
                "тормоз",
            ),
        ),
        Topic(
            name="health",
            read=read_uptime_health,
            strong=("uptime", "boot", "reboot", "restart", "час роботи", "перезавант", "аптайм"),
            weak=(
                "how long",
                "logged in",
                "users",
                "health",
                "як довго",
                "користувач",
                "увійш",
                "сеанс",
            ),
        ),
    )


def _normalize(question: str) -> str:
    """Lowercase, and fold apostrophe variants so Ukrainian stems match."""
    folded = question.lower()
    for char in _APOSTROPHES:
        folded = folded.replace(char, "'")
    return folded


def select_topic(question: str, topics: Sequence[Topic] | None = None) -> Topic | None:
    """Pick the topic a question is about, or None when nothing matches."""
    candidates = default_topics() if topics is None else topics
    normalised = _normalize(question)

    best: Topic | None = None
    best_score = 0
    for topic in candidates:
        score = topic.score(normalised)
        if score > best_score:
            best, best_score = topic, score

    return best


def build_prompt(question: str, reading: Reading) -> tuple[str, str]:
    """Build the (system, user) pair for one turn.

    A failed reading is passed through **as a failure** rather than omitted, so
    the answer explains what could not be read instead of inventing a number.
    """
    status = "reading taken" if reading.ok else "READING FAILED"
    user = (
        f"Question: {question}\n\n"
        f"Subject: {reading.name}\n"
        f"Status: {status}\n"
        f"Reading:\n{reading.text}"
    )
    return SYSTEM_PROMPT, user


def answer(
    question: str,
    completer: Completer,
    topics: Sequence[Topic] | None = None,
) -> str:
    """Answer one question about this machine.

    Args:
        question: What the user typed, in any language.
        completer: The model seam. Injected so tests never make a paid call.
        topics: Override the subject list; tests pass stubbed readings.

    Returns:
        The answer, a degraded explanation if the reading or the model failed, or
        the fallback when the question is not about anything this prototype can
        read.
    """
    if not question.strip():
        return FALLBACK

    topic = select_topic(question, topics)
    if topic is None:
        # No model call: spending a request to say "I don't know" is waste.
        return FALLBACK

    reading = topic.read()
    system, user = build_prompt(question, reading)
    return completer.complete(system, user)
