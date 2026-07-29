# Architecture — CytoblastOS

## Overview

Two independent axes. **The agent's reach** grows: read-only observation → read-only retrieval → gated writes to files and processes → gated writes to system state. **The surface** grows separately: a chat over one module (v0), then per-module interfaces — dashboards (v2), a search portal with a viewer (v3), a review feed (v5), a diff view over generations (v6) — and eventually a single shell hosting all of it (v8). They are bound by two seams that never move: the **orchestrator** above the modules, and the **MCP adapter contract** below them. Every module speaks to the OS through the adapter, so the second platform (v7) is a port, not a rewrite.

## Components

- **Orchestrator.** The chat entry point. Routes a request to one module, holds shared context across modules and turns, and applies the trust-mode split (§Trust modes): a read request goes straight to its module, a write request is routed through the gate. It knows nothing about how a module renders itself.
- **Four modules.** Monitoring and search are **read** (v2, v3); management and configuration are **write** (v5, v6). Each owns its interface, its generated-artifact kind, and its configuration. A module never calls the OS directly and never starts its own event listener.
- **Policy layer (from v4).** The gate in front of every write: review of generated code before it enters the library, capability checks and confirmation at execution, and an audit record on every pass — including refusals. See §Policy layer.
- **Shared store.** One git-backed markdown repository holding the code library, the audit journal, and the knowledge base as flat linked files. Written by the policy layer, indexed and read by search, used by management for reuse. See §Shared store.
- **Event listener.** One process over resource thresholds, the system log, and file events. Feeds push alerts to monitoring (v2), incremental reindexing to search (v3), and job triggers to management (v5). Cross-cutting: it belongs to no module. See §Event listener.
- **MCP adapters.** MCP servers are the drivers between the modules and the system, and that same contract is the OS abstraction boundary. macOS adapter from v1, Linux adapter from v7. See §OS abstraction layer.
- **Code library.** Generated artifacts with intent metadata, stored in the shared store, searched before anything new is generated. Flat frontmatter search in v1, semantic search from v3.6. See §Code library and reuse.
- **Interfaces.** Per-module surfaces (dashboards, search portal, review feed, diff view), plus chat everywhere. Thin: no module logic lives in an interface. Each offers the **bidirectional panel** action — "explain / do" from any graph, result, or job, returning that context to the orchestrator.

## The four modules

| Module | Interface | Generated artifact | Configuration → specification | Mode |
|---|---|---|---|---|
| **Monitoring** (v2) | Dashboards and graphs; alerts pushed to chat | Dashboards as code (JSON), alert rules, custom metric exporters | Metric sources, thresholds and alert channels, collection schedule | read |
| **Search & view** (v3) | Search bar with facets and result previews; viewer for own formats | Indexer connectors, saved named queries, format extractors | Source and path list, reindex schedule, facet schemas | read |
| **Management** (v5) | Review-style feed: plan → diff → confirm → execute → rollback | Parameterized jobs, each paired with an undo script | Job catalog, per-job autonomy level, snapshot retention | write |
| **Configuration** (v6) | Diff view "current vs desired" with generation history and rollback | Declarative modules per intent ("office VPN", "nightly backup") | The system config repository — here the config *is* the specification | write |

## Trust modes

- **Read (monitoring, search).** A cheap fast model, no confirmations, no gate. The worst outcome is a wrong answer, which the next turn corrects.
- **Write (management, configuration).** A stronger model behind the policy gate. Confirmation is mandatory for anything irreversible, and rollback must exist before the operation runs.

The split is enforced at the orchestrator (routing) and again at the gate (execution). There is no bypass path, including for debugging.

## OS abstraction layer

The MCP tool contract — tool name, argument schema, and result semantics — is platform-independent; a per-OS **adapter** implements it. **macOS only through v6; Linux from v7.** The boundary is laid down in **v1**, with the first adapter, because a boundary added after a second platform appears is a rewrite: by then the specifics have grown into four modules, the library, and the event listener.

Four rules:

- **No platform command outside an adapter.** `launchctl`, `brew`, `systemctl`, `apt` exist only inside adapter code. Enforced by review — the policy layer's first control point (v4) checks generated code for this.
- **One contract-test suite, every adapter passes it.** Written in v1 alongside the macOS adapter. This is what makes v7 a port.
- **Library artifacts carry a platform tag.** `macos` | `linux` | `any` in frontmatter; reuse search honors it, so a macOS job is never proposed on Linux.
- **Refusal is a result, not an error.** "Permission denied" and "unsupported on this platform" return as ordinary outcomes the gate can render, never as an exception.

| Capability | macOS (v0–v6) | Linux (v7) |
|---|---|---|
| File events | FSEvents | inotify |
| System logs | unified logging (`log`) | journald |
| Schedules and autostart | launchd | systemd (units, timers) |
| Packages | Homebrew | apt / dnf / pacman |
| Network | `networksetup`, `scutil` | NetworkManager |
| Power and display | `pmset` | logind, DE-specific |
| Restore points | APFS local snapshots (`tmutil`) | btrfs / ZFS snapshots, timeshift |
| System settings | `defaults`, plists, profiles | config files, dconf, declarative managers |

Two consequences of starting on macOS:

- **Rollback guarantees are weaker here.** The contract is "create a restore point" / "roll back to it", but a full volume rollback on macOS goes through Recovery. At job granularity the **undo script is the load-bearing mechanism** and the snapshot is insurance. On Linux with btrfs or ZFS the same contract is honest. This is a difference in guarantees, not only in implementation, and it must be reflected in what the system promises the user.
- **SIP and TCC qualify "full rights".** SIP closes system paths even as root; TCC requires user consent for Documents, Photos, and Desktop. Part of the isolation the design assigns to the policy layer is absorbed by the OS — welcome in itself — but TCC prompts break unattended jobs, so the capability model (v4) treats a denial as an expected state.

## Shared store

One git repository of markdown files, flat with links, holding three things that are one entity:

- **Code library** — generated artifacts with intent metadata.
- **Audit journal** — every gate pass, every write, every refusal.
- **Knowledge base** — what the system has learned and what the user has written.

The policy layer writes it, search indexes and reads it, management reads it for reuse. Kept as one store deliberately: three stores would need synchronizing, and the reuse path would be the first thing to rot. Git gives history and rollback for the artifacts themselves, distinct from the system-state rollback in §Rollback and traces.

## Code library and reuse

Before generating code the agent searches the library for an artifact matching the intent; a duplicate instead of a reuse is a defect. Search quality grows in two steps: **flat frontmatter and full-text matching in v1** (enough to make reuse real while monitoring is the only generator), then **semantic search over intent from v3.6**, once the indexer and ontology exist. Every artifact carries intent, type, platform tag, version, and links to what it depends on.

## Event listener

One process, three consumers, no ownership:

- **Sources.** Resource thresholds, the system log, file events — all through the adapter, so the sources differ per platform while the subscription API does not.
- **Consumers.** Monitoring takes alerts and pushes them to chat (v2); search takes file events for incremental reindexing (v3.4); management takes triggers for jobs marked auto (v5.4).
- **Direction of proactivity is configured, not hardcoded.** Schedules and triggers are set in the configuration module (v6.6); the listener fires them, monitoring and management act on them.

## Policy layer

Two control points, one audit trail. Built as its own version (v4) between the read modules and the first write module, and verified on a disposable macOS VM before any real write operation exists.

- **First control point — generation.** Generated code is reviewed before it enters the library: is there an undo path, does it touch anything outside its declared capabilities, does it call a platform command outside the adapter.
- **Second control point — execution.** The capability model checks what the operation is allowed to touch; anything irreversible requires explicit confirmation; a restore point is taken first.
- **Plan, diff, dry-run.** Consequences are shown before execution, not narrated after.
- **Audit.** Every pass through the gate lands in the shared store, refusals included. A refusal that leaves no record is a hole in the ledger.
- **Untrusted input.** Content fetched from the web or read from a user file may *request* an action; the request enters the gate as a proposal and is never executed on its own authority.

## Rollback and traces

Rollback is an invariant, not a feature: every write operation must leave a trace that makes it reversible. Three mechanisms, by module:

- **Undo script (management, v5).** Each job ships paired with its inverse. A job without an undo script is not accepted into the catalog.
- **Restore point (both write modules, v4).** Taken through the adapter before execution; retention is configured per job.
- **Generation (configuration, v6).** Each applied configuration state is kept in history, so rollback is switching back to the previous generation rather than reversing steps.

## Search, ontology, and the content portal

The search module is written in-house — the indexer with its ontology and the search manager — because that is where the product's value is; the rendering engine is not. It grows past plain file search into a managed content portal: document libraries rather than raw folders, versions and access rights, metadata and content types over files (the ontology's job), and pages composed from widgets. Search becomes semantic rather than full-text: "all documents related to the migration that I haven't opened in a month". In v3 the viewer is limited to the project's own formats — markdown, PDF, images; surfing and hosting generated apps arrive with the shell (v8).

## The shell (v8)

The search module's surface eventually becomes a single OS window in three roles: **browser** (external pages), **content viewer** (documents from the store), and **host for generated apps** (an app is a tab, not an installation). Technically one embedded webview (Chromium via Tauri or Electron); only the page source differs. Surfing leans on Claude in Chrome over MCP — the work is the shell, the tabs, and the hosting.

Its blocking precondition is isolation. The moment the window reaches the open internet it becomes an attack path into a fully privileged agent (prompt injection), and the design has no sandbox by intent. Required before the version starts: untrusted web content has no direct channel to the privileged agent (it may only request, through the gate); surfing, generated apps, and the core are isolated from each other; a generated app receives only an explicitly granted, limited capability set.

## Contracts

The stable seams. Changing one must change its contract test.

- **OS adapter (v1).** The platform-independent tool surface: `metrics.*`, `logs.*`, `files.*`, `processes.*`, `packages.*`, `network.*`, `events.subscribe`, `snapshot.create` / `snapshot.restore`. Every result carries an explicit status including `denied` and `unsupported`.
- **Orchestrator → module.** `route(request, context) -> module_response`; a write response always carries a plan and a diff before it can be executed.
- **Gate.** `evaluate(operation) -> {allowed, requires_confirmation, capabilities, restore_point}` and `audit(record)`. No write path may reach an adapter without passing through it.
- **Library artifact.** Frontmatter `{intent, type, platform, version, links, undo?}` — `undo` is required for `type: job`.
- **Journal record.** `{ts, actor, module, operation, plan_ref, diff_ref, decision, restore_point?, outcome}`.
- **Job.** `{id, name, params, autonomy: auto|confirm, undo_ref, retention, platform}`.
- **Generation (v6).** `{id, applied_at, modules[], previous_id, diff_ref}`.
- **Event.** `{kind, source, payload, ts}` — one shape for thresholds, log lines, and file events.

## Data model

- `Artifact{id, intent, type: dashboard|alert|exporter|connector|extractor|query|job|module, platform, version, body_ref, links[], created_at}` — one generated artifact in the library.
- `JournalRecord{ts, module, operation, decision: allowed|denied|confirmed, plan_ref, diff_ref, restore_point?, outcome}` — one pass through the gate.
- `Job{id, name, params_schema, autonomy, undo_ref, retention, platform, triggers[]}` — a management operation.
- `RestorePoint{id, created_at, mechanism: apfs|btrfs|zfs|file_copy, scope, expires_at}`.
- `Generation{id, applied_at, config_refs[], previous_id, diff_ref}` — one applied configuration state.
- `IndexEntry{path, content_type, facets{}, ontology_refs[], mtime, indexed_at}` — one indexed object.
- `MetricSource{id, kind, adapter_call, schedule, thresholds[]}` and `AlertRule{id, source_id, condition, channel}`.
- `Capability{name, scope, granted_to, granted_at}` — what an operation or generated app may touch.

Everything durable lives in the shared store as markdown with frontmatter; only indices and metric series need a real database (§Stack).

## Configuration and secrets

- **Configuration is explicit and switchable.** Model hosting and the cheap/strong routing rule, metric sources and thresholds, index sources and schedules, the job catalog with per-job autonomy, snapshot retention — all config, none of it hardcoded.
- **Model routing.** Read modules use the cheap fast tier; write modules and code generation use the strong tier. The routing rule is a config value, decided in v1.
- **Secrets are delegated.** The platform password manager (Keychain on macOS) holds values; the agent requests access and never receives the value into its context or the journal. Provider keys live in `.env`, never in the repo.

## Security and isolation

- **The central trade.** Full system rights instead of a sandbox; confirmation, audit, and rollback carry the weight isolation carries elsewhere. This is a deliberate inversion, and it is only sound while the gate is disciplined.
- **The OS pushes back (macOS).** SIP and TCC withhold part of that reach. Treated as expected results, surfaced to the user, never worked around.
- **Untrusted content.** Web pages, fetched documents, user files, and image metadata are data, never instructions. They may request actions; requests go through the gate.
- **Generated apps (v8).** No implicit privileges — only an explicitly granted, limited capability set.
- **Test stand.** Destructive operations are verified on a disposable macOS VM (v4), never on the working system.

## Error handling and resilience

- **A read failure degrades, never blocks.** A missing metric source, an unavailable log, an unreachable index each drop their contribution to the answer rather than failing the turn.
- **A write failure rolls back.** Any error after the restore point triggers the undo path; a failed undo is a loud, journaled incident, never a silent partial state.
- **Adapter refusals are ordinary.** `denied` / `unsupported` are rendered to the user with what would unblock them.
- **Generation failure is contained.** Code that fails review does not enter the library; the intent stays recorded so the next attempt has context.
- **The event listener never wedges a module.** A slow consumer drops events with a journaled gap, rather than stalling the source.

## Observability

- Structured logs keyed by turn and operation; every gate decision, restore point, and rollback is journaled into the shared store — the ledger and the logs are the same trail, at different granularity.
- Model latency, token usage, and tier (cheap/strong) recorded per turn — this is what makes the routing rule tunable rather than a guess.
- Reuse rate is a first-class metric: how often generation was avoided because the library already had the artifact.

## Stack and repository layout

```
/core           # orchestrator, routing, shared context, model seam (cheap/strong tiers)
/adapters       # OS abstraction: contract + macos/ (v1), linux/ (v7), contract test suite
/modules        # monitoring/ (v2), search/ (v3), management/ (v5), config/ (v6)
/policy         # gate: code review, capabilities, confirmation, audit (v4)
/events         # the single event listener: thresholds, system log, file events
/store          # shared store access: library, journal, knowledge base (git markdown)
/ui             # per-module surfaces; the shell arrives later (v8)
/tests          # unit, contract, integration; mocked model and fake adapter
/specification  # VISION.md, ARCHITECTURE.md, ROADMAP.md
```

Python for the core, with the same toolchain as the rest of this author's projects (`uv`, `ruff`, `pytest`) — consistent with the repository's Python `.gitignore`. The shell (v8) adds a JS/TS toolchain for Tauri or Electron; nothing before it needs one. Each directory is created as its version begins.

## Testing and CI

- **Contract tests pin the seams**: the adapter surface (the suite every platform must pass), the gate contract (no write path reaches an adapter without a decision record), the library artifact shape (a `job` without `undo` is rejected), and the journal record shape.
- **The trace invariant is a test, not a review note.** For every write operation exercised in the suite, a trace exists and a rollback restores the prior state.
- **Isolation tests** (from v4): untrusted content cannot produce a direct privileged action; a refusal is journaled; a denied capability never falls through.
- **Reuse tests**: a second request with the same intent resolves to the stored artifact instead of generating a new one.
- **Mock the model and the adapter in CI.** A fake adapter returns canned system state including `denied` and `unsupported`; no paid model calls, no real system mutation. Destructive paths run against the disposable VM outside CI.
- **CI** runs lint and the full suite on every push; `main` stays green to merge.
