"""Three direct macOS readings: free space, load with top consumers, uptime.

**Deliberately no adapter.** ROADMAP §v0 specifies direct calls and no
abstraction; the OS boundary is laid down in v1.2 from the v0.4 call inventory.
Every command this module runs is listed in `COMMANDS` below, which is the seed
of that inventory.

Two rules hold throughout:

- **A reading never raises.** No output, malformed output, a non-zero exit, a
  missing binary, and a command that overruns its time bound all produce a
  `Reading` with `ok=False` and a message the chat can print (ARCHITECTURE
  §Error handling and resilience). A silently wrong number is worse than an
  admitted failure.
- **Parsing is separate from running.** Every parser is a pure function over a
  string and returns `None` when it cannot make sense of its input, so the whole
  suite runs against committed fixtures with no subprocess in CI.

Everything here is read-only. The gate does not exist until v4, and a write path
in this package would be a scope error.
"""

from __future__ import annotations

import re
import subprocess
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

#: Every command this prototype runs, with why. Seed of the v0.4 call inventory,
#: which is what v1.2's adapter contract is designed against.
COMMANDS: dict[str, str] = {
    "df -k <path>": "capacity, used, and available space for one mount point",
    "sysctl -n vm.loadavg": "1, 5, and 15 minute load averages",
    "ps -Ao pid,pcpu,pmem,comm": "every process with its CPU and memory share",
    "sysctl -n kern.boottime": "boot time, from which uptime is derived",
    "who": "logged-in sessions",
}

#: A hung command must not wedge a turn. Generous for `ps` on a busy machine,
#: short enough that the chat stays answerable.
COMMAND_TIMEOUT_SECONDS = 5.0

#: Mount points worth reporting on. `/` is the sealed system volume and
#: `/System/Volumes/Data` is where the user's files actually live; on modern APFS
#: they share one container, so both report the same available space.
DEFAULT_MOUNTS: tuple[str, ...] = ("/", "/System/Volumes/Data")

#: How many processes to report per dimension.
TOP_N = 5

_KB_PER_GB = 1024 * 1024


@dataclass(frozen=True)
class CommandResult:
    """The outcome of one command: output, or a reason there is none."""

    ok: bool
    stdout: str = ""
    error: str | None = None


@dataclass(frozen=True)
class Reading:
    """One system reading.

    Attributes:
        name: Stable identifier, used by the turn to name what it asked for.
        ok: False when the reading could not be taken.
        data: The structured result, empty when `ok` is False.
        text: The rendering handed to the model — or, on failure, a plain
            statement of what could not be read.
        error: The failure reason when `ok` is False.
    """

    name: str
    ok: bool
    text: str
    data: dict[str, object] = field(default_factory=dict)
    error: str | None = None

    @classmethod
    def failed(cls, name: str, reason: str) -> Reading:
        """Build a degraded reading that says what went wrong."""
        return cls(
            name=name,
            ok=False,
            text=f"The {name} reading could not be taken: {reason}",
            error=reason,
        )


Runner = Callable[[Sequence[str]], CommandResult]


def run_command(command: Sequence[str], timeout: float = COMMAND_TIMEOUT_SECONDS) -> CommandResult:
    """Run a read-only command and capture its output.

    Returns a `CommandResult` in every case — a non-zero exit, a missing binary,
    and a timeout are ordinary outcomes here, not exceptions.
    """
    try:
        completed = subprocess.run(  # noqa: S603 - fixed, read-only argv; never shell
            list(command),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(ok=False, error=f"`{command[0]}` took longer than {timeout:g}s")
    except FileNotFoundError:
        return CommandResult(ok=False, error=f"`{command[0]}` is not available on this system")
    except OSError as exc:  # pragma: no cover - defensive
        return CommandResult(ok=False, error=f"`{command[0]}` could not be run: {exc}")

    if completed.returncode != 0:
        detail = (completed.stderr or "").strip() or f"exit status {completed.returncode}"
        return CommandResult(ok=False, error=detail)

    return CommandResult(ok=True, stdout=completed.stdout)


# --------------------------------------------------------------------------- #
# Parsers: pure, and None rather than an exception when the input makes no sense
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class Volume:
    """Space on one mount point, in 1024-byte blocks as `df -k` reports them."""

    mount: str
    total_kb: int
    used_kb: int
    available_kb: int
    capacity_pct: int

    @property
    def available_gb(self) -> float:
        return self.available_kb / _KB_PER_GB

    @property
    def total_gb(self) -> float:
        return self.total_kb / _KB_PER_GB


# A filesystem name may contain spaces (`map auto_home`), so it is matched
# non-greedily up to the first run of four numbers and a percentage.
_DF_ROW = re.compile(
    r"^(?P<fs>\S.*?)\s+(?P<total>\d+)\s+(?P<used>\d+)\s+(?P<available>\d+)\s+(?P<capacity>\d+)%"
)


def parse_df(output: str, mount: str) -> Volume | None:
    """Parse one `df -k <path>` data row. Returns None if there isn't one."""
    lines = [line for line in output.splitlines() if line.strip()]
    # First line is the header; a real row follows it.
    for line in lines[1:]:
        match = _DF_ROW.match(line)
        if match:
            return Volume(
                mount=mount,
                total_kb=int(match["total"]),
                used_kb=int(match["used"]),
                available_kb=int(match["available"]),
                capacity_pct=int(match["capacity"]),
            )
    return None


_LOADAVG = re.compile(r"\{\s*(?P<one>[\d.]+)\s+(?P<five>[\d.]+)\s+(?P<fifteen>[\d.]+)\s*\}")


def parse_loadavg(output: str) -> tuple[float, float, float] | None:
    """Parse `sysctl -n vm.loadavg`, which prints `{ 1.23 4.56 7.89 }`."""
    match = _LOADAVG.search(output)
    if not match:
        return None
    try:
        return (float(match["one"]), float(match["five"]), float(match["fifteen"]))
    except ValueError:  # pragma: no cover - the pattern already constrains this
        return None


@dataclass(frozen=True)
class Process:
    """One process and its share of the machine."""

    pid: int
    cpu_pct: float
    mem_pct: float
    name: str


def parse_ps(output: str) -> list[Process] | None:
    """Parse `ps -Ao pid,pcpu,pmem,comm`.

    COMM is the executable path and may contain spaces, so it is taken as
    everything after the third column. Returns None when no row parses; rows
    that individually fail to parse are skipped.
    """
    lines = [line for line in output.splitlines() if line.strip()]
    if not lines:
        return None

    processes: list[Process] = []
    for line in lines[1:]:  # skip the PID/%CPU/%MEM/COMM header
        parts = line.split(maxsplit=3)
        if len(parts) < 4:
            continue
        pid_text, cpu_text, mem_text, command = parts
        try:
            pid = int(pid_text)
            cpu = float(cpu_text)
            mem = float(mem_text)
        except ValueError:
            continue
        processes.append(
            # The basename is what a person recognises; the full path is noise
            # in a terminal answer.
            Process(pid=pid, cpu_pct=cpu, mem_pct=mem, name=Path(command.strip()).name or command)
        )

    return processes or None


_BOOTTIME = re.compile(r"sec\s*=\s*(?P<sec>\d+)")


def parse_boottime(output: str) -> int | None:
    """Parse the epoch seconds out of `sysctl -n kern.boottime`."""
    match = _BOOTTIME.search(output)
    if not match:
        return None
    return int(match["sec"])


def parse_who(output: str) -> list[tuple[str, str]] | None:
    """Parse `who` into (user, terminal) pairs. Returns None if nothing parses.

    An empty session list is a legitimate reading, not a failure, so blank input
    returns an empty list rather than None.
    """
    if not output.strip():
        return []

    sessions: list[tuple[str, str]] = []
    for line in output.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        sessions.append((parts[0], parts[1]))
    return sessions or None


def _format_uptime(seconds: int) -> str:
    """Render a duration the way a person would say it."""
    if seconds < 0:
        seconds = 0
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes = remainder // 60
    if days:
        return f"{days} day{'s' if days != 1 else ''}, {hours}h {minutes}m"
    if hours:
        return f"{hours}h {minutes}m"
    return f"{minutes}m"


# --------------------------------------------------------------------------- #
# Readings
# --------------------------------------------------------------------------- #

FREE_SPACE = "free space"
LOAD = "load and top consumers"
HEALTH = "uptime and health"


def read_free_space(
    runner: Runner = run_command, mounts: Sequence[str] = DEFAULT_MOUNTS
) -> Reading:
    """How much space is left, per mount point of interest."""
    volumes: list[Volume] = []
    problems: list[str] = []

    for mount in mounts:
        result = runner(["df", "-k", mount])
        if not result.ok:
            problems.append(f"{mount}: {result.error}")
            continue
        volume = parse_df(result.stdout, mount)
        if volume is None:
            problems.append(f"{mount}: df output could not be parsed")
            continue
        volumes.append(volume)

    if not volumes:
        return Reading.failed(FREE_SPACE, "; ".join(problems) or "no mount points were readable")

    lines = [
        f"{v.mount}: {v.available_gb:.1f} GB available of {v.total_gb:.1f} GB "
        f"({v.capacity_pct}% used)"
        for v in volumes
    ]
    if problems:
        # A partial reading is still useful; say what is missing rather than
        # dropping it silently.
        lines.append("Not readable: " + "; ".join(problems))

    return Reading(
        name=FREE_SPACE,
        ok=True,
        text="\n".join(lines),
        data={
            "volumes": [
                {
                    "mount": v.mount,
                    "total_kb": v.total_kb,
                    "used_kb": v.used_kb,
                    "available_kb": v.available_kb,
                    "capacity_pct": v.capacity_pct,
                }
                for v in volumes
            ],
            "unreadable": problems,
        },
    )


def read_load_and_top(runner: Runner = run_command, top_n: int = TOP_N) -> Reading:
    """Load averages plus the processes taking the most CPU and memory.

    `ps` reports CPU as an average over each process's lifetime rather than an
    instantaneous sample, so a process that was busy an hour ago can still rank
    high. Good enough to explain "why is it slow" in a prototype; a proper
    sampling collector is v2.1's job. (A finding for the v0.4 SDLC notes.)
    """
    load_result = runner(["sysctl", "-n", "vm.loadavg"])
    if not load_result.ok:
        return Reading.failed(LOAD, load_result.error or "load average was not readable")

    load = parse_loadavg(load_result.stdout)
    if load is None:
        return Reading.failed(LOAD, "load average output could not be parsed")

    ps_result = runner(["ps", "-Ao", "pid,pcpu,pmem,comm"])
    processes: list[Process] = []
    ps_problem: str | None = None
    if not ps_result.ok:
        ps_problem = ps_result.error or "process list was not readable"
    else:
        parsed = parse_ps(ps_result.stdout)
        if parsed is None:
            ps_problem = "process list output could not be parsed"
        else:
            processes = parsed

    by_cpu = sorted(processes, key=lambda p: p.cpu_pct, reverse=True)[:top_n]
    by_mem = sorted(processes, key=lambda p: p.mem_pct, reverse=True)[:top_n]

    lines = [f"Load averages: {load[0]:.2f} (1 min), {load[1]:.2f} (5 min), {load[2]:.2f} (15 min)"]
    if by_cpu:
        lines.append("Top CPU consumers:")
        lines += [f"  {p.name} (pid {p.pid}): {p.cpu_pct:.1f}% CPU" for p in by_cpu]
    if by_mem:
        lines.append("Top memory consumers:")
        lines += [f"  {p.name} (pid {p.pid}): {p.mem_pct:.1f}% memory" for p in by_mem]
    if ps_problem:
        lines.append(f"Process list not readable: {ps_problem}")

    return Reading(
        name=LOAD,
        ok=True,
        text="\n".join(lines),
        data={
            "load_average": {"one": load[0], "five": load[1], "fifteen": load[2]},
            "process_count": len(processes),
            "top_cpu": [{"pid": p.pid, "name": p.name, "cpu_pct": p.cpu_pct} for p in by_cpu],
            "top_memory": [{"pid": p.pid, "name": p.name, "mem_pct": p.mem_pct} for p in by_mem],
            "process_list_error": ps_problem,
        },
    )


def read_uptime_health(runner: Runner = run_command, now: float | None = None) -> Reading:
    """Boot time, uptime, and who is logged in."""
    boot_result = runner(["sysctl", "-n", "kern.boottime"])
    if not boot_result.ok:
        return Reading.failed(HEALTH, boot_result.error or "boot time was not readable")

    boot_epoch = parse_boottime(boot_result.stdout)
    if boot_epoch is None:
        return Reading.failed(HEALTH, "boot time output could not be parsed")

    reference = time.time() if now is None else now
    uptime_seconds = int(reference - boot_epoch)

    who_result = runner(["who"])
    sessions: list[tuple[str, str]] = []
    who_problem: str | None = None
    if not who_result.ok:
        who_problem = who_result.error or "session list was not readable"
    else:
        parsed = parse_who(who_result.stdout)
        if parsed is None:
            who_problem = "session list output could not be parsed"
        else:
            sessions = parsed

    users = sorted({user for user, _ in sessions})
    boot_text = time.strftime("%Y-%m-%d %H:%M", time.localtime(boot_epoch))

    lines = [
        f"Up {_format_uptime(uptime_seconds)} (booted {boot_text})",
    ]
    if users:
        lines.append(
            f"Logged in: {', '.join(users)} ({len(sessions)} session"
            f"{'s' if len(sessions) != 1 else ''})"
        )
    elif not who_problem:
        lines.append("Logged in: nobody")
    if who_problem:
        lines.append(f"Session list not readable: {who_problem}")

    return Reading(
        name=HEALTH,
        ok=True,
        text="\n".join(lines),
        data={
            "boot_epoch": boot_epoch,
            "uptime_seconds": uptime_seconds,
            "users": users,
            "session_count": len(sessions),
            "session_list_error": who_problem,
        },
    )
