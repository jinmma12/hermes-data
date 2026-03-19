# Hermes Stage Lifecycle Test Scenarios

## 1. Purpose

This document lists the test scenarios required to validate the stage lifecycle and queue model described in:

- `docs/STAGE_LIFECYCLE_AND_QUEUE_MODEL.md`

The goal is not theoretical completeness.
The goal is to give Claude a concrete implementation and test target.

## 2. Priority

### P0

Must exist before calling stage stop/resume operationally usable.

1. pipeline deactivate stops entire activation
2. stage stop does not deactivate whole pipeline
3. stopped process stage accumulates backlog
4. resume drains backlog
5. queue summary reflects queued/in-flight/empty states

### P1

6. stopped export stage accumulates backlog before export
7. provenance remains visible while stopped
8. stop mode `DRAIN` preserves in-flight completion
9. disabled stage differs from stopped stage

### P2

10. backpressure state exposed in queue summary
11. stage stop across reactivation/failover
12. multi-stage blocking propagation

## 3. Core Scenarios

### Scenario 1. Pipeline Deactivate Stops Whole Activation

Intent:

- confirm current top-level lifecycle remains valid

Expected:

- activation changes to `STOPPED`
- pipeline changes to `PAUSED`
- no new work intake

### Scenario 2. Stage Stop Does Not Pause Pipeline

Intent:

- stage runtime control must not equal pipeline deactivate

Expected:

- pipeline activation remains `RUNNING`
- target stage runtime state becomes `STOPPED`
- other stages remain operational if topology allows

### Scenario 3. Process Stage Stop Creates Backlog

Topology:

- collect -> process -> export

Steps:

1. activate pipeline
2. stop process stage
3. continue collector intake
4. inspect queue before process

Expected:

- activation still `RUNNING`
- process stage `STOPPED`
- queued items count increases before process
- export receives no new completed items

### Scenario 4. Resume Process Stage Drains Queue

Steps:

1. build backlog before process
2. resume process stage
3. worker processes accumulated items

Expected:

- queued count decreases
- completed count increases
- queue eventually becomes empty

### Scenario 5. Export Stage Stop Creates Backlog Before Export

Topology:

- collect -> process -> export

Steps:

1. activate pipeline
2. stop export stage
3. allow collect/process to continue

Expected:

- items complete processing
- queue before export grows
- export output count remains unchanged

### Scenario 6. Drain Stop Preserves In-Flight Work

Intent:

- verify `DRAIN` semantics

Expected:

- in-flight item completes
- new assignments stop
- remaining queue preserved

### Scenario 7. Provenance Visible While Stage Stopped

Expected:

- operator can still query work items
- operator can identify items stalled before stopped stage
- recent execution/provenance is not lost

### Scenario 8. Empty Queue Detection

Expected:

- once resumed and drained, queue summary marks empty state
- no stale queued count remains

### Scenario 9. Disabled Stage vs Stopped Stage

Intent:

- distinguish config semantics from runtime semantics

Expected:

- disabled stage is skipped by pipeline design/runtime
- stopped stage remains present with visible queue and stoppable/resumable runtime state

### Scenario 10. Failover / Reactivation Boundary

Expected:

- stage stop state handling is explicitly defined across activation boundaries
- either:
  - stop state resets on new activation
  - or stop state is persisted intentionally

This behavior must be tested, not implied.

## 4. Suggested Test Files

### Backend service / integration

- `backend/tests/test_stage_runtime_lifecycle.py`
- `backend/tests/test_stage_queue_visibility.py`
- `backend/tests/test_stage_stop_resume.py`

### E2E

- `backend/tests/e2e/test_stage_stop_backlog_flow.py`
- `backend/tests/e2e/test_stage_resume_drains_queue.py`
- `backend/tests/e2e/test_pipeline_deactivate_vs_stage_stop.py`

## 5. Suggested First Test Implementations

### 5.1 `test_pipeline_deactivate_vs_stage_stop`

Verify:

- `deactivate_pipeline()` sets activation `STOPPED`
- future `stop_stage_runtime()` keeps activation `RUNNING`

### 5.2 `test_process_stage_stop_accumulates_queue`

Verify:

- collector keeps creating work
- process stage stopped
- queued count before process increases

### 5.3 `test_resume_drains_backlog`

Verify:

- backlog present before resume
- backlog decreases after resume
- queue becomes empty

### 5.4 `test_export_stop_preserves_processed_backlog`

Verify:

- process succeeds
- export stage stopped
- queue before export grows

### 5.5 `test_disabled_stage_not_equal_stopped_stage`

Verify:

- disabled stage is omitted/ignored
- stopped stage remains observable

## 6. Minimal Assertions Required

Every new test should assert at least:

- pipeline activation status
- stage runtime status
- queued count
- in-flight count if relevant
- work-item counts by status

If provenance/event logs exist in scope, also assert:

- last stage reached
- stopped/blocking event visibility

## 7. Current Baseline Tests To Reuse

Claude should reuse and extend:

- `backend/tests/test_pipeline_composition.py`
- `backend/tests/test_pipeline_step_scenarios.py`
- `backend/tests/test_monitoring_engine.py`
- `backend/tests/e2e/test_activation_failover.py`
- `backend/tests/e2e/test_operator_pipeline_flow.py`

These already cover:

- activation/deactivation
- queue depth counting
- on_error stop
- monitor stop/resume

They do not yet cover:

- per-stage runtime stop/resume with backlog semantics

## 8. Recommended Claude Follow-Up

Claude should not start with UI work.

First:

1. encode lifecycle semantics in tests
2. decide the state model
3. implement the smallest backend/runtime changes needed
4. only then expose UI controls

