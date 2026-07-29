# Roadmap — CytoblastOS

Nine self-contained versions, built in order: **v0** prototype (monitoring, minimal search, and the generation SDLC — disposable) → **v1** foundation (store, orchestrator, event listener, macOS adapter) → **v2** monitoring → **v3** search and view → **v4** policy layer (the gate) → **v5** management → **v6** configuration → **v7** Linux port → **v8** the universal shell. Versions are numbered from 0; phases inside a version are numbered `vA.B` (A = version, B = phase), e.g. `v4.3`. Each phase lists a **Goal**, a short description, a **Tasks** list, and a **Definition of Done (DoD)**, and ships with the automated tests that encode its DoD (see [ARCHITECTURE.md](ARCHITECTURE.md) §Testing and CI).

Arc of the two axes: the agent's reach grows read-only observation → read-only retrieval → gated writes to files and processes → gated writes to system state → a second platform; the surface grows a bare chat (v0) → dashboards (v2) → search portal with a viewer (v3) → review feed (v5) → generations diff view (v6) → one shell hosting all of it (v8). The **orchestrator above** and the **adapter contract below** are fixed in v1 and never move. Complexity is added only by version, never all at once.

Three structural decisions this order encodes. **Prototype before foundation** — v0 is a thin vertical slice whose integration code is disposable by declaration, so v1 builds the foundation from evidence rather than guesses. **The gate is its own version** — v4 sits between the read modules and the first write module, and is verified on a disposable VM before any real write exists. **One platform at a time, but the boundary from v1** — macOS through v6, Linux in v7, with the adapter contract laid down long before the second platform, because a boundary retrofitted after the fact is a rewrite.

*Scope note:* the Ukrainian source spec calls the four-module product **«v1»**. In this roadmap that scope is **v0–v6**; the Linux port (v7) and the universal shell (v8) come after it. Where the source spec says "v1", read "v0–v6".

**Versioning (`A.B.C`).** `A` = roadmap version (v0→0 … v8→8), `B` = phase within it (`v4.3` → `4.3.0`), `C` = a post-release fix on that phase. Roadmap phase `vA.B` → semver `A.B.0`; a fix after it bumps `C`. Releases are cut per phase, recorded in `VERSION` and `RELEASE.txt` (newest first). Never bump the version without explicit confirmation.

---

## v0 — Prototype: monitoring, minimal search, and the generation SDLC

A thin vertical slice on macOS that tests the product's core hypothesis on live code — that an LLM generates reusable code which actually runs as an application — before frozen contracts make change expensive. Direct calls, no contracts, no gate, no writes to the system. **The integration code of this version is declared disposable up front**: what survives into v1 is the UI, the scenarios, and the findings; everything that talks to the system directly is thrown away. The invariants in VISION §Principles switch on in v1 — a prototype is exempt by design. Depends on: nothing.

The hypothesis has two halves and this version tests both. **That the agent can answer** (v0.1–v0.3, monitoring and minimal search). **That the agent can extend itself** (v0.4) — the generation lifecycle end to end: intent → spec → generate → validate → store → run → iterate. The second half is the one nothing else in the product substitutes for, and it is the least understood: [ARCHITECTURE.md](ARCHITECTURE.md) deliberately does not yet fix a runtime for generated code, because v0.4 is what earns that decision. That same phase closes the version — converting what was learned into the lists v1 is designed against, and freezing the prototype.

### v0.1 — Chat and system status

**Goal:** a chat in the terminal that answers two or three questions about the state of the machine.

Stand up the project skeleton and a chat loop that calls a model, with a handful of direct macOS calls behind it (free disk space, load, top processes). No abstraction, no routing, no store — the point is to see the whole path from question to answer working once.

**Tasks:**
- Repo skeleton, `pyproject.toml` (ruff + pytest), `.env` loading for the model key.
- A chat loop with scrollable history and exit handling.
- Three direct system readings: free space, load and top consumers, uptime/basic health.
- A model call that turns a raw reading into an answer in the user's language.

**DoD:** "how much free space is left" and "why is it slow" get useful answers in the terminal.

**Tests:** integration — one turn from question to answer against a mocked model (no paid call); unit — each reading parses its command output, including the empty and error cases.

### v0.2 — First generated dashboard

**Goal:** the intent → code → it runs loop, proven once.

Collect two or three metrics on a timer and let the agent generate a dashboard definition on request, which the app then renders. This is the hypothesis under test: that generated code becomes a working capability rather than a snippet the user must finish.

**Tasks:**
- A metric loop for two or three series (CPU, memory, disk), held in memory or a flat file.
- A generation call: user intent → dashboard definition (JSON) with a fixed schema.
- A renderer for that definition (panel or terminal chart).
- Store the definition on disk so it survives a restart.

**DoD:** "show me a temperature graph for the day" produces a dashboard definition that renders and is still there after restart.

**Tests:** unit — the generated definition validates against the schema, and an invalid one is rejected with the reason; integration — generate → persist → render against a mocked model.

### v0.3 — Flat file search

**Goal:** find a file by name, date, and type.

The minimum second module, present only to expose what search will actually need: no ontology, no facets, no connectors. Just enough to make the shape of the problem visible.

**Tasks:**
- Search over configured paths by name, mtime, and extension.
- Natural-language query → search parameters via the model.
- Result list with previews (path, size, date, first lines for text).
- A simple journal file: what was asked, what was generated, what ran.

**DoD:** "find the file I edited yesterday" returns a usable result list; every turn so far leaves a journal line.

**Tests:** unit — query → parameter mapping for the date/type/name cases; integration — a search over a fixture tree returns expected hits and the journal grows by one record per turn.

### v0.4 — App extension: prototyping the generation SDLC

**Goal:** the agent generates a small application from an intent, it runs, and it can be changed — the whole lifecycle walked once, end to end.

The core mechanism of the product, prototyped before anything depends on it. v0.2 proved a *definition* can be generated (a dashboard is data the app renders); this phase proves an *application* can be — code with an entry point, parameters, and a runtime, which the user invokes by name afterwards. What is being prototyped is not the app but the **lifecycle around it**: how an intent becomes a spec, how the generated artifact is shaped, what "it works" is checked against before it is kept, how it is invoked later, and what happens on the second request that changes it. Deliberately unpoliced — there is no gate until v4, so validation here is mechanical (does it run) rather than a policy review. Keep the app small and non-destructive: something read-only or writing only inside its own output directory.

The runtime questions this phase exists to answer, none of which are decided in advance: one file or a directory; standard library only or dependencies allowed; in-process or subprocess; how parameters are declared and validated; where output goes; how failure surfaces to the user.

**Tasks:**
- **Intent → spec.** Before generating, the agent writes a short spec of what the app does, its inputs, and its outputs — confirmed with the user. This is the seed of the library's intent metadata (v1.5).
- **Generate to a defined shape.** An artifact with an entry point, declared parameters, declared system reads, and a description — one authored template the generator fills, not free-form output.
- **Validate before keeping.** A mechanical gate: it parses, it imports, it survives a smoke run on sample parameters. Broken code is regenerated with the error as context, never stored.
- **Store with metadata.** Intent, parameters, what it reads, and a version, next to the code — the seed of the v1.1 frontmatter.
- **Run by name.** Invoke a stored app from chat with parameters; output and errors come back into the conversation.
- **Iterate.** "Change it so that…" produces a new version; the previous one stays recoverable. Record whether regeneration or patching worked better — a real input to v1.5.
- **Find before generating.** A crude match on the stored intents, so a repeated request runs the existing app instead of writing a second one.
- Journal each step of the lifecycle (spec, generation, validation result, run, iteration), so the closing findings rest on evidence rather than recollection.

**Closing the prototype** — the same phase, once the lifecycle has been walked at least a few times. This is where v0 stops being a demo and becomes the design input for v1, and where the prototype is declared dead:

- **Call inventory** — every system call the prototype made, with how often and in what shape; the seed of the adapter contract (v1.2).
- **Metadata gaps** — what the generated artifacts lacked to be findable and reusable; the seed of the library frontmatter (v1.1).
- **Event wishlist** — every moment something wanted to react to a change; the seed of the event listener (v1.4).
- **SDLC findings** — what this phase earned: the artifact shape, the runtime decision (single file vs directory, in-process vs subprocess, dependencies), what validation actually caught, and whether iteration is better as regeneration or patching. The input to the library (v1.5), to code review (v4.2), and to the ARCHITECTURE §Generated-code runtime section, which is written from this rather than guessed.
- A short verdict on the hypothesis: where generation worked, and where it produced code that had to be finished by hand.
- Freeze the prototype in its own branch or directory. Nothing is copied forward by default — only scenarios and findings cross into v1, never files.

**DoD:** an intent like "a tool that sorts my screenshots by month" produces an app that runs from chat with parameters; a follow-up change request produces a new version while the old one remains recoverable; a repeat of the original intent runs the stored app instead of generating a second one; code that fails the smoke run is never kept. And, closing the version: the four lists exist in the repository and are specific enough to design v1 against, the runtime decision is written down with the evidence behind it, and the prototype branch is frozen.

**Tests:** unit — the artifact shape validates and a malformed one is rejected with the reason; the smoke-run gate rejects non-parsing, non-importing, and crashing code (fixture apps for each). Integration — the full lifecycle intent → spec → generate → validate → store → run → iterate against a mocked model, asserting the previous version survives the iteration and the repeat intent resolves to reuse.

---

## v1 — Foundation: store, orchestrator, event listener, macOS adapter

The shared base every module plugs into, designed against what v0 actually needed. Everything cross-cutting lands here — the store and journal format, the orchestrator, the single event listener, the OS adapter boundary with its contract tests, and the code library with reuse-before-generation — and the prototype's scenarios are re-landed on top of it. From this version on, the invariants hold: every write leaves a trace, reuse precedes generation, one store, one listener, no platform command outside an adapter. Depends on: v0 (the three lists).

### v1.1 — Shared store and journal format

**Goal:** one git-backed markdown store, with the journal format set before the first write operation exists.

The code library, the audit journal, and the knowledge base as one repository of flat linked files. The journal format lands now, long before there is anything to audit, so the trace invariant never has to be retrofitted.

**Tasks:**
- Repository layout and frontmatter schema (`intent`, `type`, `platform`, `version`, `links`).
- `JournalRecord` shape and its append path; git commit per record batch.
- Store access module: read, write, link resolution — the only path to the store.
- Flat search over frontmatter plus full text (the interim reuse mechanism until v3.6).

**DoD:** an artifact and a journal record can be written, found, and read back; the store's history is inspectable in git.

**Tests:** contract — the artifact frontmatter and journal record shapes (pinned here); unit — link resolution, and a `type: job` artifact without `undo` is rejected.

### v1.2 — OS adapter contract and the macOS adapter

**Goal:** the OS boundary, implemented once for macOS and pinned by a suite any future adapter must pass.

The MCP tool contract from the v0.4 call inventory: metrics, logs, files, processes, network. Platform-independent names and result shapes; a macOS implementation behind them; `denied` and `unsupported` as ordinary results because SIP and TCC make them routine.

**Tasks:**
- Define the tool contract (names, argument schemas, result shapes with explicit status).
- macOS adapter: metrics, unified logging, filesystem, processes, network reads.
- The contract test suite — one scenario set, adapter-agnostic.
- A fake adapter for CI, able to return `denied` and `unsupported` on demand.

**DoD:** every prototype system call is available through the contract; the macOS adapter passes the full suite; no caller references a macOS command directly.

**Tests:** contract — the whole suite against the macOS adapter and the fake; unit — `denied`/`unsupported` propagate as results, never exceptions.

### v1.3 — Orchestrator

**Goal:** one chat that routes to a module and holds shared context.

Routing plus context, with the trust-mode split already in the routing decision even though no write module exists yet — so v5 plugs into a seam rather than changing one.

**Tasks:**
- Routing: request → module, with the read/write mode on the route.
- Shared context across turns and modules; every turn journaled.
- Model tier routing: cheap for read, strong for generation (config value).
- A module registration interface so v2 and v3 attach without touching the orchestrator.

**DoD:** a request reaches the right module through the orchestrator, context survives across turns, and each turn's tier choice is visible in the journal.

**Tests:** unit — routing decisions per request type, tier selection; contract — the orchestrator → module interface; integration — a two-turn conversation retains context against a mocked model.

### v1.4 — Event listener

**Goal:** one process for resource thresholds, system-log lines, and file events.

Sources come through the adapter, so the subscription API is identical on Linux later. Consumers arrive in v2, v3, and v5; the listener never learns who they are.

**Tasks:**
- One process with a subscription API and a single `Event{kind, source, payload, ts}` shape.
- Sources through the adapter: resource thresholds, unified logging, FSEvents.
- Backpressure: a slow consumer drops events with a journaled gap, never stalls the source.
- A push channel to chat, used by the first consumer in v2.

**DoD:** a threshold crossing, a matching log line, and a file change each reach a subscriber as the same event shape; a stalled subscriber does not block the others.

**Tests:** unit — subscription/fan-out, backpressure with a journaled gap; contract — the event shape; integration — a synthetic threshold reaches a test subscriber.

### v1.5 — Code library, reuse, and the prototype scenarios re-landed

**Goal:** generation goes through the library — and everything v0 demonstrated works again, on the foundation.

Reuse-before-generation becomes real here, with the flat search from v1.1. Then the three prototype scenarios are rebuilt on the orchestrator, the adapter, and the store — which is how this version proves itself.

**Tasks:**
- Library API: store an artifact with intent metadata and a platform tag; search by intent before generating.
- The generation path: search → reuse or generate → store → journal, with the reuse decision recorded.
- Re-land the v0 scenarios (system status, generated dashboard, file search) on the foundation.
- Decide and record the model hosting and cheap/strong routing rule.

**DoD:** all three v0 scenarios work again — through the orchestrator, the adapter, and the store, each leaving a journal record; a repeated intent resolves to the stored artifact instead of generating a new one; the macOS contract suite is green.

**Tests:** integration — the three scenarios end to end against mocks; unit — reuse resolution for same/similar/different intents; contract — the store and adapter suites still green.

---

## v2 — Monitoring: dashboards, alerts, exporters

The first full module, on the cheapest cost of error: read-only, no gate. It completes what the prototype sketched — real metric collection, dashboards as generated code, alert rules pushed to chat through the event listener — and it is where the code library first carries real weight. Depends on: v1 (all of it).

### v2.1 — Metric collectors and sources

**Goal:** metrics collected on a schedule from configured sources.

**Tasks:**
- `MetricSource{id, kind, adapter_call, schedule, thresholds[]}` as configuration, not code.
- A collector loop driven by the schedule, reading through the adapter.
- A time series store for collected values, with retention.
- Source health: a failing source degrades its series, never the loop.

**DoD:** configured sources collect on schedule and survive a restart; a broken source is visible without taking the others down.

**Tests:** unit — schedule computation, retention trimming, a failing source isolated; contract — the `MetricSource` shape.

### v2.2 — Dashboards as code

**Goal:** the agent generates a dashboard from an intent, and the panel renders it.

**Tasks:**
- Dashboard definition schema (panels, series, ranges) and its renderer.
- Generation from intent, through the v1.5 library path (reuse first).
- The dashboard list as a surface: open, edit, delete.
- The bidirectional panel action — "explain / do" from a graph returns its context to the orchestrator.

**DoD:** "show me disk usage over the week" produces a dashboard that renders and is reused verbatim on a repeat request; an "explain" from a graph continues in chat with that graph's context.

**Tests:** unit — schema validation and rejection with a reason; integration — generate → store → render → reuse against a mocked model.

### v2.3 — Alert rules and push to chat

**Goal:** the system tells you about what matters, without being asked.

**Tasks:**
- `AlertRule{id, source_id, condition, channel}` as generated and configured artifacts.
- Rules evaluated against the event listener's threshold events (v1.4).
- Push into chat, with the rule and the reading that fired it.
- Rate limiting and quiet hours, so alerts stay signal.

**DoD:** a disk-space threshold fires an alert into chat on its own, with enough context to act; a flapping source does not flood the channel.

**Tests:** unit — condition evaluation, rate limiting, quiet hours (injected clock, no real sleeps); integration — synthetic threshold → alert in chat.

### v2.4 — Custom exporters and diagnostics

**Goal:** the agent extends what can be measured, and answers "why did it crash".

**Tasks:**
- Generated metric exporters for sources the built-ins do not cover.
- Log reading and diagnosis through the adapter: "why did it crash", "what happened at 3am".
- Disk health and process inspection as first-class readings.
- Reuse in earnest: an exporter written for one intent is found and reused for the next.

**DoD:** monitoring answers the full read list — status, what consumes resources, running processes, log diagnosis, disk health, push alerts; the reuse rate is visible in the journal.

**Tests:** integration — a generated exporter is stored, found by a later intent, and reused; unit — log query construction and the empty-result path.

---

## v3 — Search and view: ontology, connectors, viewer

The second read module, and the upgrade that makes reuse-by-intent real: this is where searching the library stops being substring matching. The indexer and search manager are written in-house — that is where the value is. The viewer is limited to the project's own formats; surfing and app hosting wait for v8. Depends on: v1; v2 for the artifacts worth searching.

### v3.1 — Indexer and ontology

**Goal:** an index with a semantic type system over files, not just a filename table.

**Tasks:**
- `IndexEntry{path, content_type, facets, ontology_refs, mtime, indexed_at}` and the index store.
- Content types and metadata over raw files — the ontology, authored and extensible.
- A full pass over configured paths, resumable and restartable.
- Index the shared store itself: journal, library, knowledge base as first-class objects.

**DoD:** a full index over configured sources exists, entries carry content types rather than just extensions, and the store's own artifacts are in it.

**Tests:** unit — content-type resolution, facet extraction, resumability; contract — the `IndexEntry` shape.

### v3.2 — Search manager: facets and saved queries

**Goal:** search with facets, previews, and named queries that persist.

**Tasks:**
- Query path: natural language → structured query → ranked results.
- Facets (type, date, source, ontology class) with counts.
- Saved named queries as generated artifacts in the library.
- Result previews and the bidirectional "explain / do" action per result.

**DoD:** "where is the document I edited last week" returns previewed, facet-filtered results, and a saved query re-runs by name.

**Tests:** unit — query construction and ranking; integration — search over a fixture corpus, save and re-run a named query.

### v3.3 — Connectors and format extractors

**Goal:** the agent indexes sources it was not written for.

**Tasks:**
- The connector interface: a source becomes indexable by supplying enumeration plus extraction.
- Generated connectors for new sources (mail, notes, and similar), through the library path.
- Generated format extractors (PDF, documents, images) feeding content and metadata.
- Source configuration: paths, credentials via the password manager, schedule.

**DoD:** a source not anticipated in v3.1 becomes searchable through a generated connector, and a repeat request for a similar source reuses it.

**Tests:** unit — the connector interface contract and a failing connector isolated; integration — generate a connector against a fixture source, index, and search it.

### v3.4 — Incremental reindexing on events

**Goal:** the index tracks the filesystem instead of being rebuilt.

**Tasks:**
- Subscribe to the v1.4 file events; map an event to the affected entries.
- Debouncing and batching for noisy directories.
- A reconciliation pass on schedule, to catch what events missed.
- Reindex status surfaced: what is stale, what is current.

**DoD:** a changed file is searchable with its new content shortly after the change, without a full pass; a burst of changes does not saturate the machine.

**Tests:** unit — debouncing and event-to-entry mapping (injected clock); integration — modify a fixture file, observe the index update.

### v3.5 — Viewer and the content portal

**Goal:** open and read results in place — the module's own surface.

**Tasks:**
- Viewer for markdown, PDF, and images; the knowledge base reads natively.
- Document-library framing over raw folders: collections, versions, metadata.
- Semantic queries that use the ontology: "documents related to the migration I haven't opened in a month".
- Agent and system action history as a searchable surface.

**DoD:** a result opens and reads inside the product; an ontology-based query that no filename match could answer returns the right documents.

**Tests:** integration — open each supported format; unit — semantic query resolution through ontology relations.

### v3.6 — Semantic reuse for the code library

**Goal:** the library is searched by intent, not by substring — closing the gap opened in v1.

**Tasks:**
- Index library artifacts by intent, with the platform tag as a filter.
- Replace flat frontmatter matching in the reuse path with semantic search.
- A similarity floor: below it, generate rather than force a poor reuse.
- Reuse rate as a reported metric (ARCHITECTURE §Observability).

**DoD:** an artifact generated in v2 is found from a differently-worded intent describing the same task; a `linux`-tagged artifact is never proposed on macOS.

**Tests:** unit — intent matching above and below the floor, platform filtering; integration — a v2 dashboard intent resolves to reuse through the new path.

---

## v4 — Policy layer: the gate before the first write

A version with no user-facing feature. Its value is that the two versions after it cannot be built undisciplined. Both control points, the capability model, restore points, plan/diff/dry-run, and the audit trail land here, and they are verified on a disposable macOS VM **before any real write operation exists**. Depends on: v1 (store, adapter); v3 for the library search the review path uses.

### v4.1 — Capability model and permissions

**Goal:** an operation declares what it may touch, and the gate enforces it.

**Tasks:**
- `Capability{name, scope, granted_to, granted_at}` and the grant store.
- `evaluate(operation) -> {allowed, requires_confirmation, capabilities, restore_point}`.
- Irreversibility classification: what always requires explicit confirmation.
- TCC/SIP denials as expected states, surfaced with what would unblock them.

**DoD:** an operation outside its declared capabilities is refused; an irreversible operation cannot execute without confirmation; a TCC denial is rendered, not thrown.

**Tests:** contract — the gate contract; unit — capability scoping, irreversibility classification, denial rendering.

### v4.2 — Code review at generation

**Goal:** the first control point — generated code is reviewed before it enters the library.

**Tasks:**
- The review pass: undo path present, capabilities declared, no platform command outside an adapter.
- Rejection with a reason recorded, and the intent kept for the next attempt.
- The platform-tag check (an artifact touching system paths must be tagged).
- Reviewer output journaled, approvals and rejections alike.

**DoD:** generated code calling a platform command directly is rejected with the reason; a `job` without an undo script never reaches the library.

**Tests:** unit — each rejection rule against fixture code; integration — a rejected generation leaves the library unchanged and the journal complete.

### v4.3 — Restore points

**Goal:** a write can be undone, through the adapter, on the platform's own mechanism.

**Tasks:**
- `snapshot.create` / `snapshot.restore` in the adapter contract; APFS local snapshots on macOS.
- `RestorePoint{id, created_at, mechanism, scope, expires_at}` and retention.
- Honest scope reporting: what a restore point covers on this platform and what it does not.
- Restore-point creation wired into the gate, before execution.

**DoD:** a write operation is preceded by a restore point; the product's stated rollback guarantee matches what the mechanism actually delivers on macOS.

**Tests:** contract — the snapshot calls in the adapter suite; unit — retention and expiry; VM — create and restore for real, outside CI.

### v4.4 — Plan, diff, and dry-run

**Goal:** consequences are shown before execution, not narrated after.

**Tasks:**
- Plan generation for an operation: steps, affected objects, reversibility per step.
- Diff rendering: what changes, from what to what.
- Dry-run through the adapter where the platform supports it, simulated where it does not.
- Confirmation UX: the plan and diff are what the user confirms.

**DoD:** every write operation can show a plan and a diff before it runs, and the confirmation is against that diff.

**Tests:** unit — plan/diff generation for fixture operations; integration — dry-run changes nothing observable on the fake adapter.

### v4.5 — Audit and the safe stand

**Goal:** every pass through the gate is on the record — and the whole gate is proven on a machine that can be destroyed.

**Tasks:**
- Audit records into the shared store for allow, deny, and confirm alike.
- A disposable macOS VM as the standing test environment, with a reset path.
- The destructive suite: deliberately dangerous operations, run against the VM.
- The trace invariant as an automated check across every write path.

**DoD:** on the VM, a deliberately dangerous operation is stopped by the gate and leaves an audit record; a permitted one runs, leaves a restore point, and rolls back to the prior state.

**Tests:** the destructive suite on the VM; unit — audit completeness (no gate path exits without a record); contract — the journal shape under refusals.

---

## v5 — Management: jobs, review feed, triggers

The first function that changes the system — behind an already-built gate. Operations are parameterized jobs, each shipped paired with its undo script, and the interface is a review feed: plan → diff → confirm → execute → rollback. Reuse runs on the semantic search from v3.6. Depends on: v4 (all of it); v3.6 for reuse.

### v5.1 — Job contract and the catalog

**Goal:** a job is a first-class artifact — parameterized, tagged, and never without its inverse.

**Tasks:**
- `Job{id, name, params_schema, autonomy, undo_ref, retention, platform, triggers[]}`.
- The catalog: list, inspect, configure per-job autonomy (`auto` or `confirm`) and retention.
- Generated jobs through the library path, each with its undo script — rejected otherwise (v4.2).
- Platform tagging enforced; package operations go through the adapter (Homebrew on macOS), never from job code.

**DoD:** a generated job lands in the catalog with an undo script and a platform tag, or does not land at all.

**Tests:** contract — the `Job` shape and the undo requirement; unit — parameter validation, autonomy configuration.

### v5.2 — The review feed

**Goal:** the module's interface — every operation as a reviewable unit.

**Tasks:**
- The feed: plan → diff → confirm → execute → rollback, one row per operation.
- Rollback from the feed, using the undo script with the restore point as fallback.
- Execution status and the outcome journaled against the same row.
- The bidirectional "explain / do" action from any row.

**DoD:** "clean the caches" runs the full cycle from the feed and rolls back to the pre-run state.

**Tests:** integration — the full cycle against the fake adapter, including rollback; unit — feed state transitions, including a failed execution.

### v5.3 — The file and process operations

**Goal:** the module covers what management actually means day to day.

**Tasks:**
- Files: create, rename, move, copy; archive and unpack.
- Processes and apps: launch, close, terminate what is hung.
- Space: large files, duplicates, caches — each as a job with its undo.
- Packages: install, remove, update through the adapter.
- Backup and version restore as jobs, with retention.

**DoD:** the management read list from the source spec is covered by catalog jobs, each with an undo path and a restore point.

**Tests:** integration per job family against the fake adapter and the VM; unit — undo correctness for each destructive family.

### v5.4 — Triggers and autonomy

**Goal:** a job can fire from an event, without a person present — and still leave a trace.

**Tasks:**
- Job triggers subscribed to the v1.4 event listener.
- The `auto` autonomy path: no confirmation, but the same gate, restore point, and audit.
- Guardrails: `auto` is available only for jobs whose undo is proven, with rate limits and quiet hours.
- Unattended failure handling: rollback, then a push alert through the v2.3 channel.

**DoD:** a job marked `auto` fires from an event without user involvement, leaves a trace, and its failure rolls back and reports itself.

**Tests:** integration — synthetic event → auto job → journal record → rollback on induced failure; unit — the `auto` eligibility rule and rate limiting.

---

## v6 — Configuration: desired state, generations, rollback

The highest cost of error and the deepest access — the last module of the four. The interface is a diff of current versus desired state with a history of generations. This is where the configuration repository literally becomes the specification, and where the direction of proactivity (schedules, triggers) is set for the modules that execute it. On macOS the generations layer is written in-house: there is no NixOS-class declarative layer to lean on. Depends on: v4 (the gate); v5 (rollback machinery).

### v6.1 — The config repository and the current-state reader

**Goal:** the system's current configuration, read and represented as data.

**Tasks:**
- Readers through the adapter for network, sound, display, power, peripherals, locale, time, autostart.
- A normalized representation of current state, diffable and storable.
- The config repository in the shared store — the durable statement of desired state.
- Drift detection: current state read against the last applied desired state.

**DoD:** the current configuration is read into a normalized form, stored, and drift from the desired state is visible.

**Tests:** unit — normalization per domain, drift detection; contract — the config-state shape.

### v6.2 — Desired-versus-current diff view

**Goal:** the module's surface — see what would change before anything does.

**Tasks:**
- The diff view over normalized state, per domain.
- Plan generation from a desired-state change (reusing v4.4).
- Confirmation against the diff, with irreversible entries marked.
- Partial application handling: an entry that fails leaves the rest coherent.

**DoD:** a desired-state change shows a diff, and confirmation is against that diff, not against a description of it.

**Tests:** unit — diff rendering per domain, partial-failure coherence; integration — plan → diff → confirm against the fake adapter.

### v6.3 — Generations and rollback

**Goal:** each applied state is a generation; the previous one is one action away.

**Tasks:**
- `Generation{id, applied_at, config_refs, previous_id, diff_ref}` and the history surface.
- Apply as a new generation; roll back by switching to the previous.
- Generation retention and pruning.
- The generations layer written over `defaults`, plists, profiles, and launchd (no declarative substrate on macOS).

**DoD:** applying a configuration change mints a generation, and rolling back restores the previous one as a whole rather than by reversing steps.

**Tests:** integration — apply → verify → roll back → verify on the VM; unit — generation chaining and pruning.

### v6.4 — Declarative modules

**Goal:** an intent becomes a declarative module the system can apply and re-apply.

**Tasks:**
- The declarative-module format: desired state per intent, idempotent by construction.
- Generation from intent through the library path ("office VPN", "nightly backup").
- Composition: modules combine into one desired state, with conflicts surfaced.
- Re-application as convergence, not as re-execution.

**DoD:** "set up the office VPN" produces a declarative module, applies as a generation, and re-applying converges without side effects.

**Tests:** unit — idempotence and conflict detection; integration — generate → apply → re-apply → identical state, on the VM.

### v6.5 — Secrets and access

**Goal:** secrets are used without being seen; security settings become part of desired state.

**Tasks:**
- Password-manager delegation (Keychain on macOS): the agent requests use, never the value.
- Security and access as configuration: sessions, users, permissions, security updates, encryption.
- Redaction as an invariant: no secret in the model context, the journal, or the diff.
- Capability grants for generated artifacts, configured here and enforced in v4.1.

**DoD:** a configuration needing a secret applies successfully while the secret appears in neither the model context nor the journal.

**Tests:** unit — redaction across context, journal, and diff paths; integration — a secret-dependent apply against a mock password manager, asserting no leak.

### v6.6 — Schedules and triggers

**Goal:** proactivity gets its direction — configured here, executed by monitoring and management.

**Tasks:**
- Schedules and triggers as configuration, applied through the adapter (launchd on macOS).
- Wiring configured triggers into the v1.4 listener, consumed by v2.3 alerts and v5.4 jobs.
- Quiet hours and rate limits as a system-wide policy rather than per-feature settings.
- The full proactivity picture surfaced: what fires, when, and what it may do unattended.

**DoD:** a schedule set in configuration fires a management job and a monitoring alert through the shared listener, under the shared quiet-hours policy. **This completes the four-module product.**

**Tests:** integration — configure a schedule, observe the job and the alert fire (injected clock); unit — quiet-hours precedence across consumers.

---

## v7 — Linux port

The second platform, as proof that the abstraction is real. If v1 was done honestly this version touches no module code — only a second adapter, the library's platform tags, and whatever the contract suite exposes as a genuine behavioral difference. Configuration (v6) does not merely port here; it gets stronger, because Linux offers declarative substrates macOS lacks. Depends on: v6 (the complete four-module product).

### v7.1 — The Linux adapter

**Goal:** a second implementation of the v1.2 contract.

**Tasks:**
- inotify, journald, systemd (units and timers), package manager, NetworkManager, power and display.
- Run the contract suite; record genuine behavioral differences in the contract rather than working around them in modules.
- Distribution variance (apt / dnf / pacman) handled inside the adapter.
- `denied` / `unsupported` semantics mapped to Linux realities.

**DoD:** the Linux adapter passes the full contract suite; no module file changed to make it pass.

**Tests:** the contract suite on Linux; unit — distribution dispatch and the difference cases added to the contract.

### v7.2 — Snapshots and honest rollback

**Goal:** the rollback guarantee the macOS mechanism could not give.

**Tasks:**
- btrfs / ZFS snapshots (or timeshift) behind `snapshot.create` / `snapshot.restore`.
- Scope reporting updated per platform: what a restore point covers here.
- Retention aligned with the v5 job catalog.
- The destructive suite (v4.5) re-run on a Linux VM.

**DoD:** rollback on Linux restores the covered scope as a whole; the product's stated guarantee is platform-accurate in both directions.

**Tests:** the destructive suite on the Linux VM; unit — scope reporting per mechanism.

### v7.3 — Library revision and the full sweep

**Goal:** the artifacts follow the platforms, and every scenario passes on both.

**Tasks:**
- Review `macos`-tagged artifacts: generalize to `any` or generate a Linux counterpart.
- Configuration on Linux: lean on declarative managers where they exist, deepening v6.
- Run every end-to-end scenario from v2–v6 on Linux.
- Reuse search verified across platforms (no cross-platform mismatches).

**DoD:** every v2–v6 scenario passes on Linux with no change to module code; the only additions are the adapter and platform-tagged artifacts.

**Tests:** the full integration suite on both platforms in CI (fake adapter) and on the VMs (real).

---

## v8 — The universal shell

By scale a separate product the size of v0–v6 combined, which is why it comes last and only after the platform work settles. One embedded webview in three roles — browser, content viewer, host for generated apps — where extension means a new tab rather than an installation. **v7 and v8 are independent; the order is not fixed.** Linux goes first because it validates what already exists, while the shell adds new surface. Depends on: v6 (the gate, the store, the search module); v4 for the request path untrusted content must use.

### v8.1 — Isolation first

**Goal:** the precondition, built before the window ever reaches the internet.

The blocking constraint of this version, and the reason it cannot be bolted on afterwards: the moment the window reaches the open web it becomes an attack path into a fully privileged agent, and this design has no sandbox by intent.

**Tasks:**
- Untrusted web content has no direct channel to the privileged agent — it may only request, through the v4 gate.
- Process and context isolation between surfing, generated apps, and the core.
- The capability grant model for generated apps: explicit, limited, revocable (v4.1, v6.5).
- Injection tests as a standing suite: a page instructing the agent produces a gated proposal at most.

**DoD:** a page carrying an injection attempt cannot cause a privileged action; at most it produces a proposal the user must confirm.

**Tests:** the injection suite against fixture pages; unit — capability grants for an app are explicit and revocable; contract — the untrusted-request path always enters the gate.

### v8.2 — Shell and content viewer

**Goal:** one window, tabs, and the store's documents readable in it.

**Tasks:**
- The shell on an embedded webview (Tauri or Electron), with tabs and session handling.
- The content viewer role: documents, PDFs, images, and knowledge-base markdown (absorbing v3.5).
- Widget-composed pages — the content-portal surface over search results and libraries.
- Surfing via Claude in Chrome over MCP rather than a browser written here.

**DoD:** the shell opens external pages, store documents, and search results in tabs, with isolation from v8.1 holding for each source.

**Tests:** integration — each of the three page sources renders under its isolation policy; unit — tab session and source classification.

### v8.3 — Generated apps as tabs

**Goal:** the growth mechanism completes — a described intent becomes an app that opens in a tab.

**Tasks:**
- Generated apps as web modules stored in the library with their capability requirements.
- Hosting: an app opens in a tab with only its granted capabilities.
- The app catalog as a surface, with grant review and revocation.
- Reuse across the whole library, so an app is generated once.

**DoD:** an intent produces an app that opens in a tab, holds only what it was granted, and is reused instead of regenerated on the next request.

**Tests:** integration — generate → grant → open → revoke; unit — an app exceeding its grant is stopped at the gate.

---

## Open decisions

Carried from the review of the source specification; each is listed against the version that forces the choice.

- **Panel: embed Grafana or write our own (v2.2).** The source spec's module table says "Grafana-like" while the diagram says "Grafana". Embedding saves a version; a custom panel fits the bidirectional "explain / do" action and the v8 shell better.
- **Telegram's scope (v2.3).** It appears in the source architecture diagram but nowhere in the text. Full interface or push channel only — this must be settled before the push channel is built.
- **Prototype survival (v0.4 → v1).** The single largest risk to the plan is that v0's integration code does not actually die. The closing half of v0.4 is the gate; since it is a DoD clause rather than a phase of its own, the freeze must be an explicit, dated act (a frozen branch) rather than an intention — otherwise the code crosses into v1 by inertia.
- **The reuse gap (v1.5 → v3.6).** Reuse switches on in v1 with flat frontmatter search; semantic intent search only arrives in v3.6. Duplicates are caught by hand at review in between.
- **Rollback wording (v4.3).** What the product promises with the word "rollback" must match the mechanism: on macOS the undo script carries it, with the snapshot as insurance; on Linux (v7.2) the snapshot itself is honest. Decide the wording once, per platform.
- **Password manager interface (v6.5, constrains v4.1).** Keychain is the obvious macOS choice; the open question is how the agent obtains use without obtaining values, and that shapes the capability model two versions earlier.
- **Configuration depth differs by platform (v6 vs v7.3).** macOS has no declarative substrate, so generations are written in-house; Linux does, so the module deepens there. Set expectations up front, or the difference reads as a regression.
- **Numbering discrepancy in the source spec.** The «Наскрізні елементи» section calls the policy layer active "from the second module (management)", though management is third in the build order. This roadmap reads it as active from the first *write* function — the gate (v4) precedes management (v5).
