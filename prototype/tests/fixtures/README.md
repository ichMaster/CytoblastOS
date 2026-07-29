# Reading fixtures

Real output from a macOS machine, captured once so the parsers are tested against
what the commands actually print rather than against a guess. The suite runs
entirely from these files — **no subprocess is spawned in CI**.

| File | Command | Kept because |
|---|---|---|
| `df_root.txt` | `df -k /` | the ordinary case |
| `df_data.txt` | `df -k /System/Volumes/Data` | the volume where user files live |
| `df_map_auto_home.txt` | `df -k /System/Volumes/Data/home` | filesystem name **contains a space** (`map auto_home`), which breaks naive column splitting |
| `loadavg.txt` | `sysctl -n vm.loadavg` | the `{ 1.23 4.56 7.89 }` shape |
| `ps.txt` | `ps -Ao pid,pcpu,pmem,comm` | COMM is a path **with spaces and parentheses**; includes a 99.6% CPU row, a bare `/sbin/launchd`, and single-digit pids |
| `boottime.txt` | `sysctl -n kern.boottime` | `{ sec = …, usec = … }` followed by a human date |
| `who.txt` | `who` | multiple sessions for one user |

Two edits were made to the raw capture, both deliberate:

- **The username is replaced with `alice`** in `ps.txt` and `who.txt`. This is a
  public repository and the parsers care about structure, not identity.
- **`ps.txt` and `who.txt` are trimmed** to a representative slice rather than the
  full ~1000-line process list, which would have committed the machine's entire
  installed-application inventory.

Everything else is byte-for-byte as the command printed it.
