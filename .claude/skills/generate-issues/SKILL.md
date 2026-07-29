---
name: generate-issues
description: Decompose a ROADMAP phase into a per-phase GitHub-issues file at specification/roadmap/implementation/, ready for /upload-issues.
---

# Skill: Generate Version Issues

Decompose one ROADMAP **phase** (`vA.B`, e.g. `v0.3`) into a fine-grained,
dependency-ordered **issues file**, written to
`specification/roadmap/implementation/`. The output is the input to
`/upload-issues` (which pushes it to GitHub) and then `/execute-issues` (which
implements it).

## Usage

```
/generate-issues <phase>
```

- `/generate-issues 0.2` — decompose ROADMAP phase **v0.2** → `specification/roadmap/implementation/v0.2-issues.md`
- `/generate-issues v1.4` — phase **v1.4** → `…/v1.4-issues.md`

One file per **phase** (`vA.B`). IDs (`CYTO-xxx`) are **globally sequential**
and continue across phase files.

## Instructions

### Step 0: Read inputs

1. Normalize the phase to `vA.B` (e.g. `0.2` → `v0.2`).
2. Read [specification/ROADMAP.md](../../../specification/ROADMAP.md) §`A.B` —
   the phase's **Goal**, description, **Tasks**, **DoD**, and **Tests**, plus
   the parent version's intro paragraph (its scope and `Depends on:` line).
3. Read [specification/ARCHITECTURE.md](../../../specification/ARCHITECTURE.md)
   for the contracts and components the phase touches, and
   [specification/VISION.md](../../../specification/VISION.md) for the binding
   principles — read before write, every write leaves a trace, reuse before
   generation, one store, one event listener, no platform command outside an
   adapter, untrusted content may only ask.
4. Read `CLAUDE.md` for code conventions and the current module map.
5. **Find the next free `CYTO-xxx` id:** scan existing
   `specification/roadmap/implementation/v*-issues.md`; continue from the
   highest id used. If none exist yet, start at `CYTO-001`.
6. If `…/v{A.B}-issues.md` already exists, ask whether to overwrite or append.

### Step 1: Decompose the phase

Turn the phase's **Tasks** into a small set of issues (typically **3–7**), each
a coherent, independently shippable slice:

- Size each **S** (1–2 d) / **M** (3–5 d) / **L** (5–8 d).
- Order by dependency; the first issue is usually the **gate** (the seam or
  structure everything else builds on).
- Map each issue to part of the phase Tasks; together they must satisfy the
  phase **DoD**.
- **Bake tests into every issue** (CytoblastOS mocks the model and the OS
  adapter — never a paid call, never a real system mutation in CI): unit for
  pure logic, contract for any seam, an integration pass where relevant.
- A contract change (the adapter tool surface, the gate contract, the library
  artifact shape, the journal record, the event shape, `Job`, `Generation`)
  carries a `specification/ARCHITECTURE.md` update **and** its contract test in
  the **same** issue.
- Stay **within the phase** — don't pull later versions' scope in early. A
  write-path issue in a pre-v4 phase is a scope error: the gate does not exist
  yet.

### Step 2: Write the issues file

Write `specification/roadmap/implementation/v{A.B}-issues.md` using **exactly**
this format:

````markdown
# v{A.B} — GitHub Issues

Issues for phase **v{A.B} — {phase title}** (version **v{A} — {version title}**),
derived from the per-phase Tasks in [ROADMAP.md](../../ROADMAP.md) (§{A.B}) and
the contracts in [ARCHITECTURE.md](../../ARCHITECTURE.md) ({the relevant §
sections}). This file is scoped to a single phase; IDs continue from the
previous phase (CYTO-{prev} → **CYTO-{first}…{last}**).

{1–3 sentences: what the phase does, the seams it extends, why now.}

## Issues Summary Table

| # | ID | Title | Size | Area | Phase | Dependencies |
|---|----|-------|------|------|-------|--------------|
| 1 | CYTO-{first} | {title} | M | core | v{A.B} | -- |
| 2 | CYTO-{…} | {title} | S | adapters | v{A.B} | CYTO-{first} |
| … | … | … | … | … | … | … |

**Size legend:** S = 1–2 days, M = 3–5 days, L = 5–8 days
**Areas:** core · adapters · modules · policy · events · store · ui · tests

---

## Dependency Tree

```
CYTO-{first} ({gate})
  |
  +-- CYTO-{…} (…) --+
  |                  |
  +-- CYTO-{…} (…) --+
                     |
          CYTO-{…} (…)  => {phase DoD}
```

**Parallelization hints:** {which gate first; what runs in parallel after}.

---

## v{A.B} — {phase title}

### CYTO-{id} — {Title}

**Description:**
{1–3 sentences. Note which component(s) it touches: core/, adapters/macos/, modules/monitoring/, policy/, events/, store/, ui/.}

**What needs to be done:**
- {bullet}
- {bullet}

**Dependencies:** {CYTO-ids, or None}

**Expected result:**
{one sentence}

**Acceptance criteria:**
- [ ] {functional criterion}
- [ ] **Contract test:** {seam pinned} — *(only if a contract changes)*
- [ ] **Unit test:** {pure logic} against **mocks** (no paid call, no real system mutation)
- [ ] **Trace check:** the operation leaves a journal record / restore point — *(write paths only, v5+)*
- [ ] {ties to the phase DoD}

---

{repeat the `### CYTO-{id} …` block per issue}

## v{A.B} scope notes

**Total effort:** {rough estimate}.
**Critical path:** CYTO-{…} → … → CYTO-{…}.
**Phase DoD (ROADMAP §{A.B}):** {restate the DoD}.
**Contracts pinned this phase:** {the seams + their tests}.
**Mock note:** the model and the OS adapter are **mocked** in tests — never a
paid call, never a real system mutation in CI. Destructive paths run against the
disposable VM outside CI (ARCHITECTURE §Testing and CI).
**Companion documents:**
- [ROADMAP.md](../../ROADMAP.md) — phase Goal/Tasks/DoD/Tests (§{A.B}).
- [ARCHITECTURE.md](../../ARCHITECTURE.md) — {the relevant § sections}.
- Generated on upload: `v{A.B}-github-report.md` (CYTO-xxx → GitHub #), then `v{A.B}-execution-report.md`.
````

### Step 3: Report

Show the user: the file path, the issue count, the `CYTO-xxx` id range, and the
critical path. Suggest the next step:

```
/upload-issues @specification/roadmap/implementation/v{A.B}-issues.md
```

(Do **not** create GitHub issues here — that's `/upload-issues`. This skill only
writes the local issues file.)

## Important Rules

- **One file per phase** (`vA.B`) at `specification/roadmap/implementation/v{A.B}-issues.md`.
- **IDs are globally sequential** (`CYTO-xxx`), continuing across phase files — never reset per phase.
- **Tests in every issue.** Acceptance criteria include the unit/contract/integration tests; the model and the adapter are mocked, never called live, and CI never mutates the real system.
- **Contract = ARCHITECTURE + test together.** Any seam change lands its `specification/ARCHITECTURE.md` update and contract test in the same issue.
- **Scope to the phase.** Map issues to the phase's Tasks/DoD; honor the version's stated scope — don't pull later versions in early, and never open a write path before v4 exists.
- **Honor the DoD.** The issues together must satisfy the phase DoD in ROADMAP §A.B.
- **Ask on ambiguity.** If the phase's Tasks are unclear or under-specified, ask the user before inventing scope. The ROADMAP §Open decisions list is the first place to check.
- **Don't touch GitHub.** This skill writes only the local file; `/upload-issues` pushes it.
