---
name: execute-issues
description: Execute GitHub issues for a phase sequentially - implement, validate, commit, push, and generate a report.
---

# Skill: Execute GitHub Issues

Execute GitHub issues for a phase sequentially: implement, validate, commit,
push, and generate a report.

## Usage

```
/execute-issues <label> [--phase vA.B] [--issue CYTO-xxx] [--dry-run]
```

The `<label>` is the GitHub version label exactly as it appears (e.g., `v0::version:0`).

- `/execute-issues v0::version:0 --phase v0.2` -- execute all open issues of phase v0.2
- `/execute-issues v0::version:0 --issue CYTO-003` -- execute a single issue
- `/execute-issues v0::version:0 --phase v0.2 --dry-run` -- show the execution plan without changes

**CytoblastOS builds one phase per release (ROADMAP §Versioning): execute the
issues of ONE phase, then stop.** Without `--phase`, ask the user which phase to
run rather than executing everything under the version label.

## Instructions

### Step 0: Verify prerequisites

1. Confirm we are on the expected branch (e.g., `main` or the user's working branch)
2. Confirm working tree is clean (`git status`)
3. Confirm `gh` is authenticated
4. Parse the label/phase: label `v0::version:0` + `--phase v0.2` → phase `v0.2`
5. Fetch issues from GitHub:
   ```bash
   gh issue list --label "{label}" --state open --limit 100
   ```
   and filter to the phase (the `Phase:` field in each issue body / the issues file).
6. Read the phase issues file for detailed descriptions: `specification/roadmap/implementation/v{A.B}-issues.md`
7. If a GitHub report exists (`specification/roadmap/implementation/v{A.B}-github-report.md`), read the CYTO-to-GitHub# mapping
8. Read [specification/ROADMAP.md](../../../specification/ROADMAP.md) for the
   phase Goal/Tasks/DoD/Tests and the version's scope,
   [specification/ARCHITECTURE.md](../../../specification/ARCHITECTURE.md) for
   the contracts the issue must honor (§Contracts), and
   [specification/VISION.md](../../../specification/VISION.md) §Principles
   (binding). `CLAUDE.md` has the code conventions.

### Step 1: Build execution queue

From the GitHub issue list, build an ordered queue based on dependencies:
- Parse CYTO-xxx IDs from issue titles (format: `CYTO-xxx: {title}`)
- Determine dependency order from the issues file dependency tree
- Issues with no unmet dependencies go first
- Skip issues already closed on GitHub
- If `--issue CYTO-xxx` is specified, execute only that issue (but verify its dependencies are closed)

Show the user the execution plan and ask for confirmation.

### Step 2: Execute each issue (loop)

For each issue in the queue:

#### 2a. Assign and announce

Print: `--- Starting CYTO-xxx: {title} ---`

#### 2b. Read issue details

Read the full issue description from the issues file (the detailed section for
this CYTO-xxx).

#### 2c. Implement

Execute the tasks described in the issue. Follow the conventions in `CLAUDE.md`
and the principles in `specification/VISION.md`. Route by component:

- **Core** (`core/`): the orchestrator — routing, shared context, the model
  seam with its cheap/strong tiers. Read requests route past the gate, write
  requests through it; that split lives here and nowhere else.
- **Adapters** (`adapters/`): the **only** place a platform command may appear.
  `launchctl`, `brew`, `systemctl`, `apt` outside `adapters/` is a defect. Every
  call returns an explicit status including `denied` and `unsupported` — never an
  exception. A new capability lands with its entry in the contract test suite.
- **Modules** (`modules/`): monitoring, search, management, config. A module
  never calls the OS directly and never starts its own event listener — it goes
  through the adapter and subscribes to `events/`.
- **Policy** (`policy/`, from v4): the gate. Both control points (review at
  generation, permissions at execution), the capability model, restore points,
  plan/diff/dry-run, and an audit record on **every** pass including refusals.
- **Events** (`events/`): one process, one `Event{kind, source, payload, ts}`
  shape, fan-out to subscribers. Backpressure drops with a journaled gap; a slow
  consumer never stalls the source.
- **Store** (`store/`): the single git markdown repository — library, journal,
  knowledge base. A new kind of data extends this store; it never opens a second
  one.
- **Generated artifacts**: reuse before generation (search the library first),
  intent metadata plus a platform tag on everything, and — for `type: job` — an
  undo script, without which the artifact is rejected.
- **Contract changes:** any change to a stable seam (ARCHITECTURE §Contracts)
  updates `specification/ARCHITECTURE.md` **AND** its contract test, in the same
  commit.
- Follow existing style/patterns; keep each phase self-contained (don't pull
  later versions' concerns in early — VISION §Principles is binding).

#### 2d. Validate

Run validation checks (Python):

1. **Tests:** `pytest` (unit + the contract tests pinning the seams).
2. **Lint:** `ruff check {changed paths}` (and `ruff format --check` if configured).
3. **Syntax/import:** `python3 -m py_compile {changed_py_files}` and an import check for changed modules.
4. **Contract consistency:** the touched seams match `specification/ARCHITECTURE.md` §Contracts and their contract tests.
5. **Trace invariant** (write paths, v5+): every write exercised leaves a journal record and a restore point, and rolls back to the prior state.
6. **Acceptance criteria:** go through each criterion from the issue and verify against the phase DoD in `specification/ROADMAP.md`.

Record pass/fail for each check. **Tests are part of the work.** No paid calls
and no real system mutation in validation/CI: mock the model, use the fake
adapter. Destructive paths are exercised on the disposable VM, never on the
working machine.

#### 2e. Commit

```bash
git add {specific files created/modified}
git commit -m "$(cat <<'EOF'
CYTO-xxx: {title}

{1-2 sentence summary of what was implemented}

Closes #{github-issue-number}

Co-Authored-By: Claude Opus 5 (1M context) <noreply@anthropic.com>
EOF
)"
```

#### 2f. Push

```bash
git push
```

#### 2g. Close issue with summary

```bash
gh issue close {issue-number} --comment "$(cat <<'EOF'
## Implementation Summary

**Commit:** {commit-hash}
**Files changed:** {count}

### What was done
{bullet list of key changes}

### Validation
{pass/fail status for each check}

### Acceptance criteria
{checklist with pass/fail}
EOF
)"
```

#### 2h. Log progress

Append to the in-memory execution log: issue ID + title, commit hash, files
changed, validation results, status (success/partial/failed).

### Step 3: Handle failures

If implementation or validation fails for an issue:

1. Do NOT commit broken code
2. Revert changes: `git checkout -- .`
3. Add a comment to the GitHub issue explaining what failed
4. Log the failure
5. Ask the user: continue to next issue (if no dependency), or stop?

### Step 3b: Stop at the phase boundary; no auto-release

**When the phase's issues are all done, STOP.** Do not start the next phase —
the user reviews and launches it manually (ROADMAP §Versioning). **Do NOT bump
the version automatically.** Never change the version (VERSION file,
RELEASE.txt, or git tag) without explicit user confirmation; report completion
and let the user decide whether/when to release via `/release-version`.

Version notation `A.B.C`: `A` = roadmap version (v0→0), `B` = phase
(`v0.3`→B=3), `C` = post-release fix. Roadmap phase `vA.B` → semver `A.B.0`
(e.g. v0.3 → `0.3.0`). If some issues failed or were skipped, do NOT release —
note in the report that the phase is incomplete.

### Step 4: Generate execution report

After all issues are processed (or on stop), generate
`specification/roadmap/implementation/v{A.B}-execution-report.md`:

```markdown
# Phase v{A.B} -- Execution Report

**Date:** {date}
**Branch:** {branch name}
**Label:** {label}
**Target release:** {A.B.0}
**Executed by:** Claude Code

## Summary

| Status | Count |
|--------|-------|
| Completed | {n} |
| Failed | {n} |
| Skipped | {n} |
| Remaining | {n} |

## Issues

| # | CYTO ID | Title | Phase | Status | Commit | Files | Tests |
|---|---------|-------|-------|--------|--------|-------|-------|
| 1 | CYTO-001 | ... | v0.1 | completed | a1b2c3d | 4 | pass |

## Detailed Results

### CYTO-001: ...
**Status:** completed · **Commit:** a1b2c3d
**Validation:** [x] pytest · [x] ruff · [x] contracts · [x] acceptance

## Next Steps
{remaining issues + dependencies; or "phase complete — awaiting user review and /release-version A.B.0"}
```

Commit and push the report (`CYTO`-style message, with the Co-Authored-By
trailer).

## Important Rules

- **One issue at a time.** Never work on multiple issues simultaneously.
- **One phase at a time.** Execute only the given phase's issues; stop at the phase boundary — the user launches the next phase.
- **Dependency order.** Never start an issue whose dependencies are not closed.
- **Clean commits.** Each issue = one commit. No mixing work across issues.
- **No broken code.** Only commit code that passes validation (pytest + ruff).
- **Tests ship with the feature.** Mock the model and the OS adapter; never a paid call and never a real system mutation in CI.
- **Scope discipline.** VISION §Principles is binding: read before write, no write path before the gate exists (v4), no stubs or config flags for later versions.
- **The invariants are acceptance conditions.** Every write leaves a trace; reuse precedes generation; one store; one event listener; no platform command outside an adapter.
- **Contracts stay stable.** A seam change updates `specification/ARCHITECTURE.md` and its contract test in the same commit.
- **Ask on ambiguity.** If an issue description is unclear, ask the user rather than guessing.
- **Progress updates.** Print a short status line after each issue completes.
