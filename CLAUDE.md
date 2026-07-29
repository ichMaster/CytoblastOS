# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Current state

Pre-implementation. The repository contains the specification set in [specification/](specification/), the build-workflow skills in [.claude/skills/](.claude/skills/), a stock Python `.gitignore`, and the MIT license. There is no source code, no dependency manifest, and therefore **no build, lint, or test commands yet** — do not assume any exist. When the first code lands (v0.1), add the real commands to this file.

The `.gitignore` is GitHub's Python template, which is the only signal about the intended backend stack. The spec names Tauri or Electron for the shell webview, so a second (JS/TS) toolchain is expected later; neither is set up.

## Source of truth

[specification/](specification/) is the spec set, in **English**, modeled on the lumi project's format: [VISION.md](specification/VISION.md) (one sentence, what/for whom, principles, non-goals, glossary), [ARCHITECTURE.md](specification/ARCHITECTURE.md) (components, contracts, data model, stack, testing), [ROADMAP.md](specification/ROADMAP.md) (versions, phases with Goal/Tasks/DoD/Tests). These three are authoritative — design against them, and keep them in English.

Read the relevant one before designing anything; the sections below are a map, not a replacement.

**Versioning.** `vA.B` → semver `A.B.0`; `C` is a post-release fix on that phase. Releases are cut per phase into `VERSION` + `RELEASE.txt` (newest first). Never bump the version without explicit confirmation.

## Build workflow

One ROADMAP phase per release, driven by skills in [.claude/skills/](.claude/skills/) (ported from the srotas project):

`/generate-issues vA.B` → `specification/roadmap/implementation/vA.B-issues.md` (3–7 `CYTO-xxx` issues, dependency-ordered) → `/upload-issues` → GitHub issues with `v{n}::` labels → `/execute-issues <label> --phase vA.B` → one commit per issue, pytest + ruff green, issue closed. `/run-phase vA.B` chains all three with a single confirmation. `/release-version A.B.0` is always separate and deliberate.

`CYTO-xxx` ids are globally sequential across phase files. The chain stops at the phase boundary and never releases on its own.

## Architecture

CytoblastOS is an agentic interface to the operating system: a chat orchestrator routes a request to one of four modules, and the agent extends itself by generating reusable code rather than by installing prebuilt apps.

### Four modules, built in this order

Monitoring → search → management → configuration. The order runs read-only to write, i.e. from the lowest to the highest cost of a mistake. It is a deliberate risk gradient, not a backlog ordering — do not reorder it.

[ROADMAP.md](specification/ROADMAP.md) expands this into nine versions: v0 prototype (monitoring, minimal search, and the generation SDLC — integration code explicitly disposable) → v1 foundation (store, orchestrator, event listener, macOS adapter + contract tests) → v2 monitoring → v3 search → v4 policy gate → v5 management → v6 configuration → v7 Linux port → v8 shell. Each phase closes on an end-to-end scenario, and the invariants act as acceptance conditions. Note the numbering collision: the Ukrainian spec's «v1» means the four-module product, which is **v0–v6** in the roadmap.

| Module | User interface | Generated artifact | Config that becomes spec |
|---|---|---|---|
| Monitoring | Dashboards/graphs (Grafana-like); alerts pushed to chat | Dashboards-as-code (JSON), alert rules, custom exporters | Metric sources, thresholds, alert channels, collection schedule |
| Search & view | Search bar with facets and previews (Spotlight/Recoll-like) | Indexer connectors, saved named queries, format extractors | Sources and paths, reindex schedule, facet schemas |
| Management | Review-style feed: plan → diff → confirm → execute → rollback | Parameterized jobs, each paired with an undo script | Job catalog, per-job autonomy level, snapshot retention |
| Configuration | Diff view "current vs desired" with generations and rollback | Declarative modules per intent ("office VPN", "nightly backup") | System config repo — here the config *is* the spec |

The generated artifact gets closer to the system itself as you move down the list: configs → connectors → jobs → declarative system modules.

### Cross-cutting elements (not modules)

- **Orchestrator** — chat on top; routes to a module and holds shared context.
- **Event listener** — a single one for all modules. Monitoring uses it for alerts, search for incremental reindexing, management for job triggers. It belongs to no module; do not duplicate it per module.
- **Policy layer** — two control points: code review at generation time (before saving) and permissions at execution time. Active from the management module onward.
- **Code library** — generated code stored with intent metadata. Before generating anything new, the agent must search the library and reuse.
- **Bidirectional panels** — every graph, result, or job offers "explain / do", returning context to the orchestrator.

### Two trust modes

Read functions (monitoring, search) use a cheap fast model and no confirmations. Write functions (management, configuration) sit behind the policy gate: stronger model, mandatory confirmation for anything irreversible, and rollback available. Rollback is an invariant, not a feature — **every write operation must leave a trace** (snapshot, generation, or journal entry) so it can be undone.

### Shared store

The audit ledger, the generated-code library, and the knowledge base are **one entity, not three stores**: a structured markdown repository under git, Obsidian-style flat files with links. The policy layer writes to it, search indexes and reads it, management uses it for code reuse. Splitting it causes synchronization problems.

### MCP as the driver layer, and the OS abstraction boundary

MCP servers sit between the web layer and the OS (read-only tools for logs/metrics/disks; shell for processes/packages; files for mail/disk/notes; browser). That same MCP contract **is** the OS abstraction boundary: tool name, schema, and result semantics are platform-independent; a per-OS adapter implements them.

**v1 targets macOS only. Linux arrives in phase 7** — but the boundary is laid down in phase 1, not deferred until the second platform exists. Concretely: no module, orchestrator, or generated job may call a platform command directly — `launchctl`, `brew`, `systemctl`, `apt` live only inside an adapter. Library artifacts carry a platform tag (`macos` / `linux` / `any`) in frontmatter, and reuse search honors it. Contract tests written alongside the macOS adapter are what make phase 7 a port rather than a second implementation.

### The central tradeoff, and the security constraint it implies

The shape is ChromeOS-like (a web shell over a hidden OS), but inverted on access philosophy: the agent has full system rights instead of a sandbox. Discipline in the policy layer — confirmation, audit, rollback — carries the weight that sandboxing carries in ChromeOS.

On macOS "full rights" is qualified: SIP closes system paths even as root, and TCC requires per-app user consent for Documents, Photos, and Desktop. Two consequences for v1 — the OS absorbs part of the isolation burden, and TCC prompts break unattended jobs, so an adapter must return "permission denied" and "unsupported on this platform" as ordinary results, not failures. Rollback is likewise weaker here: APFS local snapshots give a restore point, but full volume rollback goes through Recovery, so the per-job undo script stays the load-bearing mechanism and the snapshot is insurance.

Once the shell browses the open web, that becomes an attack channel into a fully privileged agent (prompt injection). Build these in from the start, do not retrofit:

- Untrusted web content has no direct channel to the privileged agent. Web content may only *request* an action; it goes through the policy layer and confirmation.
- Browsing, generated apps, and the core are isolated from each other.
- Generated apps get an explicitly granted, limited capability set — never full access by default.

### v1 scope boundary

The universal browser/shell (surfing + hosting generated apps in tabs) is the goal, **not part of v1** — it is a separate product roughly the size of the first four modules combined. In v1 the search module is limited to a viewer for the project's own formats. Build the rendering engine on an embedded webview (Tauri or Electron); the parts written from scratch are the ontology-based indexer and the search manager.
