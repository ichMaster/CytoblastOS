"""Unit and integration tests for one turn.

The model is a fake and the readings are stubs: no paid call, no subprocess.
"""

from __future__ import annotations

import pytest
from conftest import FakeCompleter

from cytoblast_proto.readings import Reading
from cytoblast_proto.turn import (
    FALLBACK,
    SYSTEM_PROMPT,
    Topic,
    answer,
    build_prompt,
    default_topics,
    select_topic,
)


def stub_topics(reading: Reading | None = None) -> tuple[Topic, ...]:
    """The real keyword sets, but readings that touch nothing."""
    real = default_topics()
    return tuple(
        Topic(
            name=topic.name,
            read=lambda t=topic: (
                reading or Reading(name=t.name, ok=True, text=f"stub {t.name}", data={"stub": True})
            ),
            strong=topic.strong,
            weak=topic.weak,
        )
        for topic in real
    )


# --------------------------------------------------------------------------- #
# Selection
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        # --- the two DoD questions ---
        ("how much free space is left", "free space"),
        ("why is it slow", "load"),
        # --- free space, English ---
        ("how much disk space do I have", "free space"),
        ("is the drive full?", "free space"),
        ("what's my storage capacity", "free space"),
        # --- free space, Ukrainian ---
        ("скільки вільного місця залишилось", "free space"),
        ("диск заповнений?", "free space"),
        # --- load, English ---
        ("what is eating my CPU", "load"),
        ("why is the machine so sluggish", "load"),
        ("which process is using the most memory", "load"),
        ("everything keeps freezing", "load"),
        # --- load, Ukrainian ---
        ("чому так повільно працює", "load"),
        ("що вантажить процесор", "load"),
        ("яке навантаження", "load"),
        # --- health, English ---
        ("what is the uptime", "health"),
        ("how long has this been up", "health"),
        ("when did it last reboot", "health"),
        ("who is logged in", "health"),
        # --- health, Ukrainian ---
        ("який час роботи системи", "health"),
        ("коли було перезавантаження", "health"),
    ],
)
def test_selection_maps_phrasings_to_topics(question: str, expected: str) -> None:
    topic = select_topic(question)

    assert topic is not None, f"no topic matched: {question!r}"
    assert topic.name == expected


@pytest.mark.parametrize(
    "question",
    [
        "what is the capital of France",
        "write me a poem",
        "",
        "   ",
        "asdfghjkl",
        "send an email to my manager",
    ],
)
def test_unrecognised_questions_select_nothing(question: str) -> None:
    assert select_topic(question) is None


def test_strong_keywords_break_a_tie_toward_the_right_topic() -> None:
    """ "free" hints at disk, but "memory" decides it."""
    topic = select_topic("how much memory is free")

    assert topic is not None
    assert topic.name == "load"


def test_keywords_match_at_a_word_start_not_mid_word() -> None:
    """Regression: `вільн` ("free") is a substring of `повільно` ("slowly").

    With plain substring matching, "чому так повільно" scored for the disk
    reading and won the tie — a silently wrong answer in Ukrainian.
    """
    topic = select_topic("чому так повільно")

    assert topic is not None
    assert topic.name == "load"


def test_a_ukrainian_stem_still_matches_an_inflected_word() -> None:
    """The boundary must not cost stem matching: `вільн` in `вільного`."""
    topic = select_topic("скільки вільного місця")

    assert topic is not None
    assert topic.name == "free space"


def test_freezing_outranks_free() -> None:
    """Regression: "freezing" starts with "free", which no boundary can split."""
    topic = select_topic("everything keeps freezing")

    assert topic is not None
    assert topic.name == "load"


def test_selection_is_case_insensitive() -> None:
    assert select_topic("HOW MUCH DISK SPACE") == select_topic("how much disk space")


def test_selection_folds_ukrainian_apostrophe_variants() -> None:
    """пам'ять may be typed with ' or ’ — both must match the same stem."""
    straight = select_topic("скільки пам'яті вільно")
    curly = select_topic("скільки пам’яті вільно")

    assert straight is not None
    assert curly is not None
    assert straight.name == curly.name == "load"


# --------------------------------------------------------------------------- #
# Prompt construction
# --------------------------------------------------------------------------- #


def test_prompt_carries_the_question_and_the_reading() -> None:
    reading = Reading(name="free space", ok=True, text="3.9 GB available", data={})

    system, user = build_prompt("how much space?", reading)

    assert system == SYSTEM_PROMPT
    assert "how much space?" in user
    assert "3.9 GB available" in user
    assert "free space" in user
    assert "reading taken" in user


def test_prompt_marks_a_failed_reading_as_failed() -> None:
    """A degraded reading must reach the model as a failure, not as silence."""
    reading = Reading.failed("free space", "df is not available on this system")

    _system, user = build_prompt("how much space?", reading)

    assert "READING FAILED" in user
    assert "df is not available" in user


def test_system_prompt_states_the_binding_rules() -> None:
    lowered = SYSTEM_PROMPT.lower()

    assert "only from the reading" in lowered
    assert "same language" in lowered
    assert "never invent" in lowered
    assert "failed" in lowered


# --------------------------------------------------------------------------- #
# The turn, end to end
# --------------------------------------------------------------------------- #


def test_a_full_turn_returns_the_models_text_unchanged() -> None:
    completer = FakeCompleter(answer="You have 3.9 GB left.")

    result = answer("how much free space is left", completer, topics=stub_topics())

    assert result == "You have 3.9 GB left."


def test_a_full_turn_puts_the_reading_into_the_prompt() -> None:
    completer = FakeCompleter()

    answer("why is it slow", completer, topics=stub_topics())

    ((system, user),) = completer.prompts
    assert system == SYSTEM_PROMPT
    assert "why is it slow" in user
    assert "stub load" in user  # the reading's data reached the prompt


def test_both_dod_questions_reach_the_model_with_their_reading() -> None:
    """The phase DoD, asserted directly."""
    for question, expected_reading in [
        ("how much free space is left", "stub free space"),
        ("why is it slow", "stub load"),
    ]:
        completer = FakeCompleter(answer="an answer")

        result = answer(question, completer, topics=stub_topics())

        assert result == "an answer"
        ((_system, user),) = completer.prompts
        assert expected_reading in user


def test_a_failed_reading_still_reaches_the_model() -> None:
    failed = Reading.failed("free space", "df exploded")
    completer = FakeCompleter(answer="I could not read the disk.")

    result = answer("how much space?", completer, topics=stub_topics(reading=failed))

    assert result == "I could not read the disk."
    ((_system, user),) = completer.prompts
    assert "READING FAILED" in user
    assert "df exploded" in user


@pytest.mark.parametrize(
    "question", ["what is the capital of France", "", "   ", "write me a poem"]
)
def test_the_fallback_makes_no_model_call(question: str) -> None:
    completer = FakeCompleter()

    result = answer(question, completer, topics=stub_topics())

    assert result == FALLBACK
    assert completer.prompts == []


def test_the_fallback_names_what_can_be_answered() -> None:
    lowered = FALLBACK.lower()

    assert "disk space" in lowered
    assert "cpu" in lowered
    assert "up" in lowered


def test_a_degraded_model_result_is_returned_as_is() -> None:
    """The seam already degrades; the turn must not second-guess it."""
    completer = FakeCompleter(answer="The model is rate limited right now.")

    result = answer("how much disk space", completer, topics=stub_topics())

    assert result == "The model is rate limited right now."


def test_default_topics_are_bound_to_the_three_real_readings() -> None:
    names = [topic.name for topic in default_topics()]

    assert names == ["free space", "load", "health"]
