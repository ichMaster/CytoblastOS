# Vision — CytoblastOS

## In one sentence

CytoblastOS is an agentic interface to the operating system — one chat over four modules (monitoring, search, management, configuration) that grows its own capabilities by generating reusable code instead of installing applications.

## What we are building

An OS shell where every function has two paths: the familiar click, or a request to the agent for anything complex. Four modules cover what a person expects from an operating system — **monitoring** (what is happening), **search and view** (where things are), **management** (do something), **configuration** (how the system should be). Each module has its own interface, its own kind of generated artifact, and its own configuration that gradually becomes that module's specification.

The nearest analogy is ChromeOS — an operating system reduced to a shell over a hidden kernel — with two dimensions of its own. **LLM control instead of clicks**: complex intent goes to the agent, routine action stays a button. **Code generation instead of installation**: the user describes an intent, the agent generates a module, stores it in the library, and the capability begins to exist. The OS grows its own functions on demand.

The generated artifact gets closer to the system itself as the build order advances: dashboards and alert rules (monitoring) → indexer connectors (search) → jobs paired with undo scripts (management) → declarative system modules (configuration).

The name is from cell biology: *cyto-* (cell, vessel) + *-blast* (sprout, growth point) — the system as a germ cell that grows its own functions.

## For whom

The owner of a single personal machine, on their own system, with the agent holding full rights to it. Not a mass-market product, not a managed fleet, not a hosted service: one agent, one machine, one person's data. macOS at first (v0–v6); Linux from v7. *(The source spec does not state an audience explicitly — this is what its full-privilege, single-machine premise implies.)*

## Principles

- **Read before write.** The build order — monitoring → search → management → configuration — runs from the lowest to the highest cost of a mistake. It is a deliberate risk gradient, not a backlog ordering.
- **Prototype before foundation.** v0 is a thin vertical slice that answers what the foundation must actually support; its integration code is declared disposable up front. v1 then builds the shared foundation from evidence rather than from guesses.
- **Two trust modes.** Read functions (monitoring, search) run on a cheap fast model with no confirmations. Write functions (management, configuration) sit behind the policy gate: a stronger model, mandatory confirmation for anything irreversible, rollback available.
- **Every write leaves a trace.** A snapshot, a generation, or a journal entry. An operation whose effect cannot be reconstructed and undone afterwards does not ship.
- **Reuse before generation.** Before writing new code the agent searches the library for an existing artifact and reuses it. A duplicate instead of a reuse is a defect, not a detail.
- **One store, not three.** The audit ledger, the generated-code library, and the knowledge base are a single git-backed markdown repository (flat files with links, Obsidian-style). Splitting them creates synchronization problems, not separation of concerns.
- **One event listener.** A single process feeds alerts to monitoring, incremental reindexing to search, and job triggers to management. A module subscribes to it; it never starts its own.
- **The config is the specification.** Each module's configuration — metric sources, index sources, job catalog, system config repo — is the durable statement of what that module does. Nowhere is this more literal than in configuration, where the config repository *is* the spec.
- **Platform specifics live only in the adapter.** No module, orchestrator, or generated job calls a platform command directly. The MCP tool contract is the OS boundary; a per-OS adapter implements it. This holds from v1, long before the second platform exists.
- **Untrusted content may only ask.** Web pages, fetched documents, and generated apps never reach a privileged action directly — they request one, and the request goes through the gate like any other.
- **Complexity by version.** Each version is self-contained and ends in a scenario that works end to end without manual intervention. Nothing is built "for later".

## Non-goals

- **Not a sandbox.** This is ChromeOS inverted on access philosophy: hermeticism is traded for reach, and the policy layer — confirmation, audit, rollback — carries the weight that sandboxing carries in ChromeOS. On macOS the OS itself (SIP, TCC) takes back part of that reach; that is a constraint to design around, not the security model.
- **Not a browser written from scratch.** The universal shell (v8) is an embedded webview plus tabs and hosting for generated apps; surfing leans on Claude in Chrome over MCP.
- **The universal shell is not part of the four-module product.** By scale it is a separate product the size of v0–v6 combined; until then the search module ships a viewer for its own formats only.
- **Not a secrets store.** Secrets are delegated to the platform password manager; the agent requests access and never sees values.
- **No multi-machine fleet, no public service, no open sign-up.** One owner, one system.

## Glossary

- **Module** — one of the four functional groups (monitoring, search, management, configuration), each with its own interface, generated artifact, and configuration.
- **Orchestrator** — the chat on top: routes a request to a module and holds shared context across them.
- **Event listener** — the single cross-cutting process over resource thresholds, the system log, and file events; feeds alerts (v2), reindexing (v3), and job triggers (v5). Belongs to no module.
- **Policy layer (the gate)** — two control points: review of generated code before it is saved, and permissions at execution time. Active from the first write function (v5), built in v4.
- **Code library** — generated code stored with intent metadata and a platform tag, searched for reuse before anything new is generated.
- **Shared store** — the one git markdown repository holding the code library, the audit journal, and the knowledge base.
- **Adapter** — the per-OS implementation of the MCP tool contract; the only place platform commands may appear. macOS from v1, Linux from v7.
- **Contract tests** — the one scenario suite every adapter must pass; what makes v7 a port rather than a second implementation.
- **Job** — a parameterized management operation, always shipped paired with its undo script (v5).
- **Undo script** — the per-job inverse operation; the load-bearing rollback mechanism on macOS, where snapshots are insurance rather than a full revert.
- **Restore point** — the adapter-level snapshot taken before a write (APFS local snapshot on macOS; btrfs/ZFS on Linux).
- **Generation** — one applied state of the system configuration, kept in history so the previous one can be restored (v6).
- **Declarative module** — a generated configuration artifact describing an intent as desired state ("office VPN", "nightly backup") rather than as steps.
- **Ontology** — the semantic type system layered over files (content types and metadata) that turns search from full-text into meaning-based (v3).
- **Content portal** — what the search module grows into: document libraries instead of raw folders, versions, access rights, metadata, and widget-composed pages.
- **Bidirectional panel** — the "explain / do" action available from any graph, result, or job, which returns that context to the orchestrator.
- **Trace** — the record a write operation leaves (snapshot, generation, or journal entry) that makes it auditable and reversible.
- **Shell** — the embedded webview in three roles (browser, content viewer, host for generated apps), post-v6 (v8).
