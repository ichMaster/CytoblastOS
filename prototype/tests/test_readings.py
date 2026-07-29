"""Unit tests for the three system readings.

Parsers run against committed fixtures of real command output; readings run
against a fake runner. No subprocess is spawned and nothing is mutated.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from cytoblast_proto.readings import (
    COMMAND_TIMEOUT_SECONDS,
    COMMANDS,
    FREE_SPACE,
    HEALTH,
    LOAD,
    CommandResult,
    Reading,
    parse_boottime,
    parse_df,
    parse_loadavg,
    parse_ps,
    parse_who,
    read_free_space,
    read_load_and_top,
    read_uptime_health,
    run_command,
)

FIXTURES = Path(__file__).parent / "fixtures"


def fixture(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


class FakeRunner:
    """Answers per command word with a canned result."""

    def __init__(self, replies: dict[str, CommandResult]) -> None:
        self.replies = replies
        self.calls: list[list[str]] = []

    def __call__(self, command) -> CommandResult:
        command = list(command)
        self.calls.append(command)
        for key, reply in self.replies.items():
            if key in command or key in " ".join(command):
                return reply
        return CommandResult(ok=False, error=f"no fake reply for {command}")


def ok_runner() -> FakeRunner:
    """A runner where every command succeeds, from the fixtures."""
    return FakeRunner(
        {
            "df": CommandResult(ok=True, stdout=fixture("df_root.txt")),
            "vm.loadavg": CommandResult(ok=True, stdout=fixture("loadavg.txt")),
            "pid,pcpu,pmem,comm": CommandResult(ok=True, stdout=fixture("ps.txt")),
            "kern.boottime": CommandResult(ok=True, stdout=fixture("boottime.txt")),
            "who": CommandResult(ok=True, stdout=fixture("who.txt")),
        }
    )


# --------------------------------------------------------------------------- #
# Parsers against real output
# --------------------------------------------------------------------------- #


def test_parse_df_reads_real_output() -> None:
    volume = parse_df(fixture("df_root.txt"), "/")

    assert volume is not None
    assert volume.mount == "/"
    assert volume.total_kb > 0
    assert volume.available_kb >= 0
    assert 0 <= volume.capacity_pct <= 100
    # 1024-byte blocks: a 460 GB disk is ~4.8e8 blocks, not ~4.6e2.
    assert volume.total_gb > 100


def test_parse_df_handles_a_filesystem_name_containing_a_space() -> None:
    """`map auto_home` would break a naive split on whitespace."""
    volume = parse_df(fixture("df_map_auto_home.txt"), "/System/Volumes/Data/home")

    assert volume is not None
    assert volume.capacity_pct == 100
    assert volume.total_kb == 0


def test_parse_loadavg_reads_real_output() -> None:
    load = parse_loadavg(fixture("loadavg.txt"))

    assert load is not None
    assert len(load) == 3
    assert all(value >= 0 for value in load)


def test_parse_ps_reads_real_output() -> None:
    processes = parse_ps(fixture("ps.txt"))

    assert processes is not None
    assert len(processes) >= 5
    # COMM is a path with spaces and parentheses; the basename is what is kept.
    names = [p.name for p in processes]
    assert "launchd" in names
    assert "Google Chrome Helper (Renderer)" in names
    assert all(p.pid > 0 for p in processes)
    assert max(p.cpu_pct for p in processes) > 50  # the 99.6% row survived


def test_parse_boottime_reads_real_output() -> None:
    boot = parse_boottime(fixture("boottime.txt"))

    assert boot is not None
    assert boot > 1_600_000_000  # a plausible epoch, not a parsed usec field


def test_parse_who_reads_real_output() -> None:
    sessions = parse_who(fixture("who.txt"))

    assert sessions is not None
    assert len(sessions) >= 2
    assert all(user and terminal for user, terminal in sessions)


# --------------------------------------------------------------------------- #
# Parsers against empty and malformed input: None, never an exception
# --------------------------------------------------------------------------- #

MALFORMED = [
    "",
    "   \n\n",
    "not even close to the real thing",
    "Filesystem 1024-blocks Used Available Capacity\n",  # header with no rows
    "\x00\x01 binary garbage",
]


@pytest.mark.parametrize("text", MALFORMED)
def test_parse_df_returns_none_on_bad_input(text: str) -> None:
    assert parse_df(text, "/") is None


@pytest.mark.parametrize("text", MALFORMED)
def test_parse_loadavg_returns_none_on_bad_input(text: str) -> None:
    assert parse_loadavg(text) is None


@pytest.mark.parametrize("text", MALFORMED)
def test_parse_ps_returns_none_on_bad_input(text: str) -> None:
    assert parse_ps(text) is None


@pytest.mark.parametrize("text", MALFORMED)
def test_parse_boottime_returns_none_on_bad_input(text: str) -> None:
    assert parse_boottime(text) is None


def test_parse_df_ignores_a_truncated_row() -> None:
    """A row with too few columns must not become a half-parsed volume."""
    assert parse_df("Filesystem 1024-blocks Used\n/dev/disk1 482797652\n", "/") is None


def test_parse_ps_skips_unparseable_rows_but_keeps_good_ones() -> None:
    text = "  PID  %CPU %MEM COMM\nbroken row\n  1   0.5  0.1 /sbin/launchd\n"

    processes = parse_ps(text)

    assert processes is not None
    assert len(processes) == 1
    assert processes[0].name == "launchd"


def test_parse_who_treats_no_sessions_as_empty_not_broken() -> None:
    """Nobody logged in is a valid answer, not a failed reading."""
    assert parse_who("") == []
    assert parse_who("   \n") == []


# --------------------------------------------------------------------------- #
# run_command: failures are results
# --------------------------------------------------------------------------- #


def test_run_command_reports_a_missing_binary() -> None:
    result = run_command(["cytoblast-no-such-binary-exists"])

    assert result.ok is False
    assert "not available" in (result.error or "")


def test_run_command_reports_a_non_zero_exit() -> None:
    result = run_command(["df", "-k", "/no/such/path/on/this/machine"])

    assert result.ok is False
    assert result.error


def test_run_command_reports_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung command is a failed reading, never a blocked turn."""

    def _timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="ps", timeout=COMMAND_TIMEOUT_SECONDS)

    monkeypatch.setattr(subprocess, "run", _timeout)

    result = run_command(["ps"])

    assert result.ok is False
    assert "longer than" in (result.error or "")


# --------------------------------------------------------------------------- #
# Readings: the happy path, then every failure mode
# --------------------------------------------------------------------------- #


def test_free_space_reading_from_fixtures() -> None:
    reading = read_free_space(runner=ok_runner(), mounts=("/",))

    assert reading.ok
    assert reading.name == FREE_SPACE
    assert "GB available" in reading.text
    assert reading.data["volumes"]
    assert reading.error is None


def test_load_reading_from_fixtures() -> None:
    reading = read_load_and_top(runner=ok_runner())

    assert reading.ok
    assert reading.name == LOAD
    assert "Load averages:" in reading.text
    assert "Top CPU consumers:" in reading.text
    assert "Top memory consumers:" in reading.text
    assert len(reading.data["top_cpu"]) > 0


def test_load_reading_respects_top_n() -> None:
    reading = read_load_and_top(runner=ok_runner(), top_n=2)

    assert len(reading.data["top_cpu"]) == 2
    assert len(reading.data["top_memory"]) == 2


def test_health_reading_from_fixtures() -> None:
    boot = parse_boottime(fixture("boottime.txt"))
    assert boot is not None
    # An injected clock, so the assertion does not drift with the wall clock.
    reading = read_uptime_health(runner=ok_runner(), now=boot + 90_000)

    assert reading.ok
    assert reading.name == HEALTH
    assert "Up 1 day" in reading.text
    assert reading.data["uptime_seconds"] == 90_000
    assert "alice" in reading.data["users"]


def test_a_failed_command_degrades_each_reading() -> None:
    broken = FakeRunner({})  # every command returns ok=False

    for reading in (
        read_free_space(runner=broken),
        read_load_and_top(runner=broken),
        read_uptime_health(runner=broken),
    ):
        assert reading.ok is False
        assert reading.error
        assert "could not be taken" in reading.text


def test_unparseable_output_degrades_each_reading() -> None:
    garbage = FakeRunner(
        {
            "df": CommandResult(ok=True, stdout="nonsense"),
            "vm.loadavg": CommandResult(ok=True, stdout="nonsense"),
            "kern.boottime": CommandResult(ok=True, stdout="nonsense"),
        }
    )

    for reading in (
        read_free_space(runner=garbage),
        read_load_and_top(runner=garbage),
        read_uptime_health(runner=garbage),
    ):
        assert reading.ok is False
        assert "could not be parsed" in (reading.error or "")


def test_free_space_reports_a_partially_readable_set_of_mounts() -> None:
    """One bad mount must not discard the mounts that did read."""

    def first_mount_only(command):
        return (
            CommandResult(ok=True, stdout=fixture("df_root.txt"))
            if command[-1] == "/"
            else CommandResult(ok=False, error="No such file or directory")
        )

    reading = read_free_space(runner=first_mount_only, mounts=("/", "/nope"))

    assert reading.ok  # still useful
    assert len(reading.data["volumes"]) == 1
    assert reading.data["unreadable"]
    assert "Not readable" in reading.text
    assert "/nope" in reading.text


def test_load_reading_survives_a_broken_process_list() -> None:
    """Load average alone is still worth answering with."""
    runner = FakeRunner(
        {
            "vm.loadavg": CommandResult(ok=True, stdout=fixture("loadavg.txt")),
            "pid,pcpu,pmem,comm": CommandResult(ok=False, error="ps exploded"),
        }
    )

    reading = read_load_and_top(runner=runner)

    assert reading.ok
    assert "Load averages:" in reading.text
    assert "Process list not readable" in reading.text
    assert reading.data["process_list_error"] == "ps exploded"


def test_health_reading_survives_a_broken_session_list() -> None:
    runner = FakeRunner(
        {
            "kern.boottime": CommandResult(ok=True, stdout=fixture("boottime.txt")),
            "who": CommandResult(ok=False, error="who exploded"),
        }
    )

    reading = read_uptime_health(runner=runner)

    assert reading.ok
    assert "Up " in reading.text
    assert "Session list not readable" in reading.text


def test_a_timed_out_command_degrades_each_reading() -> None:
    """The acceptance criterion end to end: a hung command fails, never blocks."""

    def timed_out(command):
        return CommandResult(ok=False, error=f"`{command[0]}` took longer than 5s")

    for reading in (
        read_free_space(runner=timed_out),
        read_load_and_top(runner=timed_out),
        read_uptime_health(runner=timed_out),
    ):
        assert reading.ok is False
        assert "took longer than" in (reading.error or "")


def test_no_reading_raises_on_any_documented_failure() -> None:
    """The turn must never see an exception from a reading."""
    failures = [
        CommandResult(ok=False, error="exit status 1"),
        CommandResult(ok=False, error="`df` is not available on this system"),
        CommandResult(ok=False, error="`ps` took longer than 5s"),
        CommandResult(ok=True, stdout=""),
        CommandResult(ok=True, stdout="\x00 garbage"),
    ]

    for failure in failures:
        for read in (read_free_space, read_load_and_top, read_uptime_health):
            reading = read(runner=lambda _command, reply=failure: reply)
            assert isinstance(reading, Reading)
            assert reading.ok is False


def test_failed_reading_helper_shape() -> None:
    reading = Reading.failed("a reading", "because")

    assert reading.ok is False
    assert reading.error == "because"
    assert reading.data == {}


def test_commands_are_documented_for_the_v04_inventory() -> None:
    """The call inventory is a v0.4 deliverable; keep it honest as we go."""
    assert len(COMMANDS) >= 5
    joined = " ".join(COMMANDS)
    for tool in ("df", "sysctl", "ps", "who"):
        assert tool in joined
