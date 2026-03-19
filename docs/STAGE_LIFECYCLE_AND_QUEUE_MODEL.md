# Hermes Stage Lifecycle And Queue Model

## 1. Purpose

This document defines the missing runtime model between:

- pipeline activation/deactivation
- per-stage stop/resume control
- queue visibility
- provenance visibility

Current Hermes behavior is pipeline-centric.

Today:

- `activate_pipeline()` starts a pipeline activation
- `deactivate_pipeline()` stops the latest running activation
- stage `is_enabled` is a configuration flag, not a runtime control

This is not enough for NiFi-like operator behavior.

Operators need to:

- stop a specific stage
- let upstream work accumulate
- inspect queue depth
- inspect provenance while stopped
- resume processing later

## 2. Problem Statement

The current model conflates three different concerns:

1. Pipeline lifecycle
   - whether a pipeline activation exists and is running

2. Stage configuration
   - whether a stage is enabled in the recipe/pipeline definition

3. Stage runtime control
   - whether a specific stage is currently accepting input, processing, draining, or stopped

Today Hermes only has:

- pipeline activation status
- static stage enable/disable
- work-item status

It does not have:

- stage runtime lifecycle
- stage queue state as a first-class concept
- queue-aware stop/resume semantics

## 3. Design Goals

Hermes should support the following operator workflows:

1. Pipeline running, specific process stage stopped
2. Collector continues producing work
3. Work accumulates before the stopped stage
4. Operator can inspect queue depth and item age
5. Operator can inspect provenance / item state
6. Operator resumes the stage
7. Queue drains

This must be distinct from:

- pausing the whole pipeline
- disabling a stage in the definition

## 4. Core Model

### 4.1 Pipeline Activation

Pipeline activation remains the top-level runtime envelope.

Suggested statuses:

- `STARTING`
- `RUNNING`
- `DRAINING`
- `STOPPING`
- `STOPPED`
- `ERROR`

Meaning:

- `RUNNING`: pipeline activation is live
- `DRAINING`: no new intake, existing queued work still being processed
- `STOPPING`: controlled shutdown in progress

### 4.2 Stage Runtime State

Add a stage runtime state separate from `is_enabled`.

Suggested statuses:

- `RUNNING`
- `STOPPED`
- `DRAINING`
- `BLOCKED`
- `ERROR`

Definitions:

- `RUNNING`
  - stage accepts input and processes work

- `STOPPED`
  - stage does not process new work
  - upstream may still produce queue backlog depending on topology

- `DRAINING`
  - stage is finishing already assigned/in-flight work
  - no new work should be assigned

- `BLOCKED`
  - stage cannot progress because downstream is stopped or queue/backpressure threshold is hit

- `ERROR`
  - stage runtime encountered a failure and is not healthy

### 4.3 Stage Definition Flag vs Runtime State

Keep these separate:

- `is_enabled`
  - design-time configuration
  - persisted as part of pipeline/stage config
  - disabled stages are skipped entirely

- `runtime_state`
  - operational control
  - mutable while pipeline is active
  - does not rewrite pipeline definition

Example:

- `is_enabled=false`
  - stage is effectively absent from execution

- `is_enabled=true` and `runtime_state=STOPPED`
  - stage exists but is intentionally paused by operator

## 5. Queue Model

### 5.1 Queue As A First-Class Runtime Concept

Hermes should expose stage queues explicitly.

Suggested entity:

- `StageQueueSnapshot`

Fields:

- `pipeline_activation_id`
- `stage_id`
- `queue_name`
- `queued_count`
- `queued_bytes` if meaningful
- `oldest_item_age_seconds`
- `newest_item_age_seconds`
- `in_flight_count`
- `blocked_by_stage_id` optional
- `backpressure_state`

### 5.2 Queue Positions

At minimum, operators need to reason about:

- queue before process stage
- queue before export stage

Conceptually:

- collector output queue
- process input queue
- export input queue

Hermes does not need to imitate NiFi connection objects exactly, but it must expose equivalent operational visibility.

### 5.3 Backpressure States

Suggested states:

- `NORMAL`
- `PAUSED`
- `STOPPED`

Meaning:

- `NORMAL`
  - queue below thresholds

- `PAUSED`
  - producer slowed / intake reduced

- `STOPPED`
  - producer halted due to hard queue limit

This aligns with existing backpressure-oriented tests already present in the reference layer.

## 6. Stop Semantics

### 6.1 Stop Pipeline

`deactivate_pipeline()` should mean:

- stop new intake
- stop or drain stage workers according to shutdown mode
- mark activation `STOPPING` then `STOPPED`

This is whole-pipeline control.

### 6.2 Stop Stage

Add explicit stage control:

- `stop_stage_runtime(pipeline_activation_id, stage_id)`
- `resume_stage_runtime(pipeline_activation_id, stage_id)`

`stop_stage_runtime` should:

- set stage runtime state to `STOPPED` or `DRAINING`
- prevent dispatch of new work into that stage
- preserve queued items upstream or in the stage input queue

It must not:

- rewrite pipeline definition
- mark pipeline itself `PAUSED`
- kill provenance/history visibility

### 6.3 Drain Mode

Recommended stop modes:

- `IMMEDIATE`
- `DRAIN`

`IMMEDIATE`

- stop assigning and interrupt where possible
- use carefully

`DRAIN`

- no new work assigned
- in-flight work completes
- queued work remains visible

For first implementation, `DRAIN` is safer and more operator-friendly.

## 7. Provenance Model

### 7.1 What Operators Need

When a stage is stopped, operators still need to see:

- items waiting before the stage
- last successfully processed item
- failed item history
- queue growth over time

### 7.2 Minimum Provenance Additions

Hermes already has work-item/execution/provenance concepts.

Add operational visibility for:

- `queued_before_stage`
- `stalled_at_stage`
- `blocked_by_stage`
- `resumed_from_stage`

This can initially be represented through:

- work-item statuses
- execution event logs
- queue snapshots

without inventing a totally separate provenance store.

## 8. API Model

Suggested endpoints:

- `POST /pipelines/{pipeline_id}/activate`
- `POST /pipelines/{pipeline_id}/deactivate`
- `POST /activations/{activation_id}/stages/{stage_id}/stop`
- `POST /activations/{activation_id}/stages/{stage_id}/resume`
- `GET /activations/{activation_id}/queues`
- `GET /activations/{activation_id}/stages`
- `GET /activations/{activation_id}/work-items?status=DETECTED`

Suggested response additions:

- activation status
- per-stage runtime state
- queue summaries
- backlog counts

## 9. UI Model

### 9.1 Pipeline-Level Controls

- Activate
- Deactivate
- Drain + Stop

### 9.2 Stage-Level Controls

Per stage:

- `Stop`
- `Resume`
- `Drain`

This is different from:

- `Enabled/Disabled` in the configuration editor

### 9.3 Queue Visualization

For each stage:

- queued count
- in-flight count
- oldest queued age
- empty queue indicator
- blocked/downstream stopped warning

### 9.4 Provenance View

Operators should be able to:

- click a stage
- inspect queued items
- inspect failed items
- inspect recent event log

## 10. Minimal Implementation Scope

Do not try to build full NiFi immediately.

Phase 1 should implement:

1. stage runtime state model
2. stop/resume API for stage runtime
3. queue depth view per stage
4. stage stop tests
5. queue accumulation tests

Not required in Phase 1:

- byte-accurate queue accounting
- visual graph edge queues
- advanced queue replay tooling
- full content browsing

## 11. Test Implications

The following behaviors must be tested:

1. pipeline deactivate stops whole activation
2. stage stop does not pause whole pipeline
3. stopped process stage accumulates upstream queue
4. resumed process stage drains queue
5. export stopped causes backlog before export
6. provenance remains visible while stage is stopped
7. empty queue detection works after drain
8. disabled stage and stopped stage have different behavior

## 12. Current Gap Summary

Current Hermes supports:

- pipeline activation/deactivation
- static stage enable/disable
- work-item status counting
- some provenance concepts

Current Hermes does not yet support:

- per-stage runtime stop/resume
- queue as first-class runtime API
- NiFi-like operational queue inspection
- stop-a-stage-and-watch-backlog behavior

## 13. Recommended Claude Follow-Up

Claude should use this document as the source design for:

1. stage lifecycle implementation planning
2. queue state API design
3. backend test additions
4. UI stop/resume and queue visibility planning

Claude should not assume:

- `deactivate_pipeline()` is equivalent to stage stop
- `is_enabled` is equivalent to runtime pause

