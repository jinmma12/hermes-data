# Hermes Stream Roadmap

> Last updated: 2026-03-19
> Current priority: Integrity-first runtime hardening
> Current state: strong prototype, not yet production-trustworthy

---

## Vision

**Hermes Stream** is a lightweight data pipeline platform for operators who need:

- non-developer-friendly configuration from the web
- per-item provenance and execution history
- recipe/version management
- first-class replay and reprocessing
- NiFi-style observability without NiFi's operational weight

The long-term product direction remains:

- **.NET Engine** = runtime source of truth
- **Python API** = management/query facade and migration/reference layer
- **React UI** = operator console

That split is not optional. If runtime semantics live in Python tests/docs but not in
the .NET engine, Hermes will look more complete than it actually is.

---

## Product Truths

These are the rules that shape all roadmap decisions.

### 1. Integrity before breadth

Hermes is intended for real internal operational use. That means:

- duplicate collection behavior must be understood
- restart behavior must be deterministic
- retry and DLQ behavior must be explicit
- recipe snapshots must be reproducible
- replay/reprocess must be auditable

Adding more connectors before these guarantees are solid is a liability.

### 2. Runtime truth belongs to the .NET engine

The .NET engine must own:

- activation/deactivation semantics
- collect/process/export execution
- dedup/checkpointing
- retry/backoff/circuit breaker
- snapshot capture and replay
- provenance event generation
- cluster coordination and reassignment
- Kafka delivery semantics

Python may provide:

- CRUD APIs
- read/query APIs
- admin/auth/websocket façade
- migration parity tests
- plugin/reference utilities

### 3. Support level must be explicit

A connector or feature is only `Production-Ready` when it has:

1. deterministic restart behavior
2. explicit failure classification
3. metrics/logging/alert surfaces
4. integration tests against a real service or deterministic harness
5. documented operating limits

UI presence or mock-only coverage is not enough.

---

## Stage Model

| Stage | Purpose | Examples |
|---|---|---|
| **Collect** | Read or detect data from a source | File Watcher, FTP/SFTP, Kafka Consumer, REST API, DB Query |
| **Process** | Transform, validate, enrich, analyze, route | Transformer, Dedup, Router, Anomaly Detector |
| **Export** | Deliver to a destination | Kafka Producer, DB Writer, File Output, S3 Upload, Webhook |

---

## Support Levels

Hermes uses four support levels in this roadmap.

| Level | Meaning |
|---|---|
| **Production-Ready** | Integrity guarantees and real integration coverage exist |
| **Beta** | Functionally usable but still missing some operational guarantees |
| **Prototype** | Demo/reference quality, not yet safe for trusted workloads |
| **Planned** | Design intent only |

---

## What Is Actually Required for v1

Hermes does not need every connector category to be complete before it becomes useful.
It does need one coherent, trustworthy operating slice.

### v1 trustworthy slice

1. File Watcher Collect
2. FTP/SFTP Collect
3. Kafka Consumer Collect
4. REST API Collect
5. Basic Process chain
6. Kafka Producer Export
7. DB Writer Export
8. File Output Export
9. Replay/Reprocess
10. Provenance and monitoring

Everything else can come later.

---

## Current Assessment

### Strong

- product concept and differentiation
- UI direction and operator workflow thinking
- recipe/versioning model
- provenance/reprocess intent
- breadth of documented scenarios

### Weak

- runtime/documentation mismatch
- too much implied support from UI and docs
- insufficiently explicit support-level boundaries
- connector breadth outpacing integrity guarantees
- cluster claims ahead of runtime hardening
- Python reference layer still richer than some .NET runtime paths

### Immediate Risks

1. engine stub mode can hide missing runtime connectivity
2. FTP/SFTP dedup appears process-local instead of persisted
3. connector capability promises exceed current runtime enforcement
4. cluster failover semantics are not yet closed
5. mock-heavy tests can overstate runtime safety

---

## Current Progress Snapshot

This section is the practical answer to "where are we now?"

### Delivered recently

- Hermes rebrand across major docs and UI surfaces
- roadmap refocused around integrity-first delivery
- connector editor moved to a 3-layer model:
  - `process_settings`
  - `connection_config`
  - `runtime_policy`
  - `recipe_config`
- core connector UI moved to manifest-driven configuration instead of hardcoded-only forms
- FTP/SFTP operator docs, examples, presets, help content, and path-preview UX landed
- connector config contract and capability-mismatch discussions are now explicit in docs
- stage lifecycle and queue model are now documented
- backend tests now lock in the distinction between:
  - pipeline deactivate
  - stage stop/resume
  - queue backlog visibility

### Delivered, but still not "closed"

- stage stop/resume currently exists as a service/model/test contract, not yet as fully enforced runtime dispatch control
- queue visibility currently exists as derived queue summaries, not yet as a first-class API/UI runtime surface
- FTP/SFTP operator UX is much stronger, but .NET runtime parity is still incomplete
- connector UI is manifest-driven, but runtime capability enforcement is still ahead of some actual implementations
- local draft behavior exists, but final persistence-mode contract and production restrictions still need tightening

### Practical phase estimate

If we map the real state to this roadmap:

- Phase 0: complete
- Phase 1: complete
- Phase 2: in progress, with meaningful progress on contract definition and tests
- Phase 3: started, but not yet at trustworthy runtime level
- Phase 4: started on FTP/SFTP operator UX only
- Phase 5: still mostly design/test territory, not runtime-complete

Short version:

- product concept and operator UX direction: far along
- runtime integrity: mid-build
- production trust: not there yet
- distributed trust: early

---

## Phase 0: Design and Prototype Foundation ✅ COMPLETE

Delivered:

- architecture and collection design docs
- plugin protocol and initial runtime split
- Python prototype backend
- React operator UI
- .NET engine foundation
- pipeline/recipe/provenance domain model

Key outputs:

- `docs/ARCHITECTURE.md`
- `docs/DATA_COLLECTION_DESIGN.md`
- `docs/TEST_STRATEGY.md`
- `docs/CLUSTER_DESIGN.md`
- `backend/`
- `engine/`
- `webapp/`

---

## Phase 1: Functional Prototype ✅ COMPLETE

Delivered:

- definitions, instances, pipelines, recipes
- activation and processing model
- initial collect/process/export flow
- reprocess model
- operator UI with pipeline and recipe surfaces
- initial built-in connector set

This phase proves the product idea.
It does **not** by itself prove operational trust.

---

## Phase 2: Integrity Track 🔥 CURRENT PRIORITY

This phase matters more than adding more connector count.

### 2A. Runtime Contract Hardening

- [ ] Mark `.NET Engine` as the runtime authority in docs and code comments
- [ ] Prevent production startup from silently using EngineClient stub mode
- [ ] Surface engine transport health in `/api/v1/health` and system status
- [ ] Define and document delivery guarantees per connector
- [ ] Define supported replay semantics per stage

Acceptance criteria:

1. A disconnected engine cannot look healthy in production mode
2. Runtime ownership of collect/process/export is documented and testable
3. Operator-facing health surfaces expose degraded transport state

### 2B. Checkpoint and Dedup Safety

- [ ] Persist monitor checkpoints outside process memory
- [ ] Persist dedup identity for collect sources
- [ ] Document dedup key strategy by source type
- [ ] Add restart recovery tests for file, FTP/SFTP, and Kafka
- [ ] Add replay tests proving no accidental recollect on restart

Acceptance criteria:

1. process restart does not blindly recollect already-accepted data
2. dedup key calculation is documented and asserted in tests
3. checkpoint ownership survives normal restarts

### 2C. Replay and Snapshot Correctness

- [ ] Verify execution snapshots are immutable and replay-safe
- [ ] Verify reprocess from step N reuses prior successful state correctly
- [ ] Verify `use_latest_recipe` and `use_original_recipe` behavior
- [ ] Add audit/log coverage for manual and bulk replay

Acceptance criteria:

1. replay intent is visible in DB and UI
2. snapshot hash changes only when config meaningfully changes
3. replay from later stages does not silently rerun earlier stages unless requested

### 2D. Failure Classification Framework

- [ ] Standardize error categories: transient, permanent, throttled, unknown
- [ ] Standardize retry policy contract by connector category
- [ ] Standardize DLQ payload and replay metadata
- [ ] Expose retry/DLQ counters in metrics

Acceptance criteria:

1. every connector failure path maps to a known class
2. DLQ entries preserve source identity and failure reason
3. retry behavior is deterministic and configurable

### 2E. Stage Lifecycle and Queue Semantics

This item was elevated because the current system was too pipeline-centric for actual operator use.

- [x] Document the distinction between pipeline deactivate and stage stop/resume
- [x] Add backend service/model support for per-stage runtime state
- [x] Add queue summary tests for stopped-stage backlog and resume/drain flows
- [ ] Enforce stage runtime state in real worker/orchestrator dispatch
- [ ] Expose stage runtime state via API and UI
- [ ] Expose queue visibility as an operator-facing runtime surface
- [ ] Add provenance views tied to stopped-stage backlog inspection
- [ ] Add migration and deploy-safe schema rollout for `stage_runtime_states`

Acceptance criteria:

1. stage stop is distinct from pipeline deactivate in both model and runtime behavior
2. stopped stages actually block new dispatch, not just report state
3. operators can inspect backlog and provenance before resume
4. queue/runtime state survives normal deployment and schema rollout

---

## Phase 3: Core Connectors to Production-Ready

This phase is about making the essential connectors safe enough to trust.

### 3A. Collect Connectors

| Connector | Target | Current | Notes |
|---|---|---|---|
| File Watcher | Production-Ready | Beta | Must close checkpoint/restart semantics |
| FTP/SFTP Collector | Production-Ready | Beta | Highest industrial priority |
| Kafka Consumer | Production-Ready | Beta | Must close offset, rebalance, replay semantics |
| REST API Collector | Production-Ready | Beta | Must close pagination/retry/idempotency behavior |
| Database Query / CDC | Beta | Prototype | Narrow scope before broad DB promise |

#### FTP/SFTP work

- [ ] host key verification and key-based auth support
- [ ] FTPS/TLS error handling and certificate behavior
- [ ] completion checks: marker-file and size-stable
- [ ] post-actions: keep/delete/move/rename
- [ ] persisted discovery state
- [ ] large directory traversal limits and safeguards
- [ ] real FTP/SFTP integration tests

Acceptance criteria:

1. restart-safe collection behavior
2. no silent duplicate collection after normal restart
3. real FTP and real SFTP integration coverage
4. documented handling for partial files, renamed files, deleted files

#### Kafka Consumer work

- [ ] explicit manual commit timing
- [ ] define default guarantee: at-least-once
- [ ] partition rebalance handling
- [ ] poison message strategy
- [ ] retry and DLQ behavior
- [ ] restart/resume tests
- [ ] real Kafka integration tests

Acceptance criteria:

1. commit point is explicit and tested
2. rebalance does not lose observability
3. poison messages do not deadlock the pipeline
4. duplicate handling strategy is documented

### 3B. Export Connectors

| Connector | Target | Current | Notes |
|---|---|---|---|
| File Output | Production-Ready | Beta | Needs stronger failure and idempotency guarantees |
| Kafka Producer | Production-Ready | Prototype | Must land in this phase |
| DB Writer | Production-Ready | Prototype | Narrow scope: PostgreSQL and SQL Server only |
| S3 Upload | Beta | Prototype | Useful, but not ahead of Kafka/DB |
| Webhook | Beta | Prototype | Useful after core export guarantees are clear |

#### Kafka Producer work

- [ ] keying and partition strategy
- [ ] acks and retry policy
- [ ] idempotent producer support where feasible
- [ ] ordering expectations documentation
- [ ] produce-failure visibility and metrics

Acceptance criteria:

1. operator can explain when a message is considered delivered
2. producer errors surface clearly in execution logs and metrics
3. retry and duplicate expectations are documented

#### DB Writer work

- [ ] insert/upsert modes
- [ ] schema mismatch classification
- [ ] transaction and rollback behavior
- [ ] deadlock retry behavior
- [ ] integration tests for PostgreSQL and SQL Server

Acceptance criteria:

1. upsert semantics are explicit
2. failure modes are observable and replayable
3. DB writer behavior is covered for both supported providers

---

## Phase 4: Operator UX and Trust Surfaces

Once runtime behavior is trustworthy, the UI can become a real operating console.

- [ ] support-level badges in UI: Production-Ready/Beta/Prototype
- [~] connector capability pages with operating notes
- [~] test-connection and preview behavior aligned with runtime reality
- [ ] replay UX showing original vs latest recipe clearly
- [ ] DLQ explorer and replay queue UX
- [ ] cluster health and connector health dashboards

Acceptance criteria:

1. UI does not imply unsupported runtime capability
2. operator can distinguish preview success from production runtime readiness
3. replay intent and connector support level are obvious

Progress note:

- FTP/SFTP now has a real operator-help slice:
  - help content
  - examples/presets
  - selection summary
  - local path preview
- This is useful progress, but it is still connector-specific and not yet a complete trust-surface system.

---

## Phase 5: Distributed Runtime

Distributed execution is important, but it must come after single-node integrity is real.

- [ ] coordinator/worker lease model
- [ ] split-brain prevention
- [ ] failover without duplicate collection
- [ ] checkpoint ownership transfer
- [ ] worker crash recovery for in-flight executions
- [ ] cluster-aware provenance and logs

Acceptance criteria:

1. coordinator failover does not create double collectors
2. worker crash does not orphan execution state invisibly
3. ownership transfer is observable and auditable

---

## Phase 6: Ecosystem and Enterprise Add-ons

- [ ] multi-tenancy
- [ ] plugin marketplace
- [ ] environment promotion
- [ ] Git-backed pipeline promotion
- [ ] documentation site
- [ ] CLI
- [ ] Terraform provider
- [ ] compliance/security hardening

These matter, but they are not more important than runtime integrity.

---

## Connector Acceptance Standard

No connector should be called `Production-Ready` until it passes all of the following.

### Required

1. configuration schema
2. test connection behavior
3. preview/discovery behavior
4. runtime execution path
5. explicit failure classification
6. retry or fail-fast policy
7. metrics/logging
8. restart behavior
9. replay/reprocess compatibility
10. real integration coverage or deterministic harness equivalent

### Source-specific requirements

#### Collect

1. dedup key strategy
2. checkpoint strategy
3. partial-read handling
4. source identity recorded in provenance

#### Process

1. deterministic step input/output summary
2. retry semantics
3. snapshot compatibility

#### Export

1. delivery success definition
2. duplicate tolerance or idempotency strategy
3. destination-side failure reporting

---

## Test Strategy Targets

The test goal is not just more tests. It is better trust calibration.

### Target mix

- unit tests for pure domain logic
- service tests for orchestration and snapshot behavior
- real integration tests for FTP/SFTP, Kafka, DB, and S3-compatible storage
- xfail contract tests for not-yet-closed operating behaviors
- soak tests for reconnect/retry/backpressure

### Required E2E contracts

1. operator creates and activates pipeline
2. source event creates one tracked work item
3. process/export success is visible in provenance
4. source or export failure enters retry/DLQ path visibly
5. replay from failed stage preserves audit history
6. restart resumes safely without silent duplication

See:

- `docs/CLAUDE_E2E_OPS_CONSULTING.md`
- `backend/tests/e2e/`
- `deploy/docker-compose.e2e.yml`

---

## What We Are Explicitly Not Doing Yet

These are intentionally not the current priority:

- connector count inflation for its own sake
- large cluster claims before single-node integrity is closed
- marketplace polish before runtime trust exists
- advanced enterprise features before core collect/process/export is trustworthy

---

## Development Workflow

### Branch policy

```
main
develop
feature/*
fix/*
test/*
docs/*
```

### PR checklist

```
□ runtime behavior matches docs/UI claims
□ tests added for the changed behavior
□ support level updated if capability changed
□ no silent fallback to stub/runtime bypass
□ restart/retry implications considered
□ ROADMAP.md updated if scope or support level changed
```

---

## Short-Term Execution Plan

### Next 2 weeks

1. block or expose stub mode in production
2. define persisted checkpoint and dedup strategy
3. connect stage runtime state to actual worker/orchestrator dispatch
4. close FTP/SFTP runtime gaps
5. define Kafka consumer commit semantics
6. land Kafka producer and DB writer MVP

### Next 4-6 weeks

1. real-service integration suite for FTP/SFTP/Kafka/PostgreSQL
2. replay/reprocess audit completion
3. support-level badges and capability surfaces in docs and UI
4. queue/runtime API exposure for stopped-stage inspection
5. restart and failover contract tests

### After that

1. operator UX refinement
2. cluster coordination hardening
3. broader connector ecosystem

---

## Changelog

### 2026-03-18

- roadmap refocused around integrity-first delivery
- made `.NET engine as runtime truth` explicit
- replaced connector-count-heavy planning with support-level and acceptance-gate planning
- moved distributed runtime after single-node integrity hardening
- elevated Kafka producer/consumer and FTP/SFTP to core trustworthy slice
- added connector acceptance standard and short-term execution plan

### 2026-03-19

- added progress snapshot section to distinguish delivered UX/design work from closed runtime guarantees
- reflected manifest-driven 3-layer connector configuration work
- reflected FTP/SFTP operator docs, presets, help, and preview UX progress
- added Stage Lifecycle and Queue Semantics to Phase 2
- clarified that stage stop/queue work is currently model/test-level, not yet fully enforced runtime dispatch behavior

### 2026-03-16

- Collect/Process/Export naming alignment
- recipe management UX expansion
- FTP/SFTP collector spec expansion
- broad connector expansion plan drafted
