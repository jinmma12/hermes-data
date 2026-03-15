# Hermes - Architecture & Design Specification

> **Hermes**: A lightweight, user-friendly data processing platform with
> per-item tracking, visual recipe management, and first-class reprocessing.
>
> "Data flows through Hermes like cargo through a ship —
> every item tracked, every journey recorded, every route configurable."

---

## 1. Project Identity

| Item | Value |
|---|---|
| **Name** | Hermes |
| **Tagline** | "Carry your data. Track every item." |
| **License** | Apache 2.0 |
| **Position** | Between NiFi (heavy/powerful) and Singer (lightweight/limited) |
| **Target User** | Non-SW engineers who need to configure data collection & processing |

### 1.1 What Hermes Is NOT

- NOT a replacement for NiFi — can use NiFi as an execution backend
- NOT a DAG orchestrator (Airflow/Dagster territory)
- NOT a streaming platform (Kafka territory)
- NOT limited to any industry domain

### 1.2 Why Hermes Exists

| Existing Tool | Gap Hermes Fills |
|---|---|
| Apache NiFi | Too heavy (JVM 2GB+), complex UI, Java-only plugins |
| Airbyte | EL only (no algorithm/processing), Docker-per-connector overhead |
| n8n | Not designed for high-volume data processing, no item-level tracking |
| Airflow/Dagster | Developer-centric (Python code), no per-item tracking |
| Benthos | No UI, no item tracking, Go-only plugins |
| Singer/Meltano | No UI, no orchestration, quality inconsistency |

**Hermes's unique value**: NiFi-grade per-item tracking + n8n-grade visual UI + first-class reprocessing — in a lightweight package.

---

## 2. Core Design Principles

```
1. NON-DEVELOPER FIRST
   → SW 개발자가 아닌 운영자가 Web UI에서 모든 설정 가능

2. EVERY ITEM TRACKED
   → 개별 Job 단위로 수집-처리-전송 전 과정 추적

3. RECIPE AS FIRST CLASS
   → Algorithm 파라미터, 수집 설정 모두 버전 관리되는 Recipe

4. REPROCESS ANYTHING
   → 실패 건, 특정 건, 특정 Step부터 재처리 가능

5. PLUGIN EVERYTHING
   → Collector, Algorithm, Transfer 모두 플러그인으로 교체 가능

6. NiFi-FRIENDLY, NOT NiFi-DEPENDENT
   → NiFi가 있으면 활용, 없으면 자체 실행
```

---

## 3. High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                        VESSEL WEB UI (React)                        │
│                                                                     │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────┐ ┌────────────────┐  │
│  │ Pipeline     │ │ Recipe      │ │ Monitor   │ │ Job       │  │
│  │ Designer     │ │ Editor      │ │ Dashboard │ │ Explorer       │  │
│  │              │ │             │ │           │ │                │  │
│  │ n8n-style    │ │ Form-based  │ │ Real-time │ │ Search/Filter  │  │
│  │ visual flow  │ │ param edit  │ │ status    │ │ Reprocess      │  │
│  │ drag & drop  │ │ versioned   │ │ heartbeat │ │ Detail/Log     │  │
│  └─────────────┘ └─────────────┘ └───────────┘ └────────────────┘  │
│                                                                     │
│  ┌─────────────┐ ┌─────────────┐ ┌───────────────────────────────┐ │
│  │ Plugin      │ │ Definition  │ │ System                        │ │
│  │ Marketplace │ │ Manager     │ │ Settings & Health             │ │
│  └─────────────┘ └─────────────┘ └───────────────────────────────┘ │
└────────────────────────────┬────────────────────────────────────────┘
                             │ REST API + WebSocket (live updates)
┌────────────────────────────▼────────────────────────────────────────┐
│                      VESSEL CORE (API Server)                       │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                    Pipeline Manager                           │   │
│  │  - CRUD pipelines, steps, recipes                            │   │
│  │  - Version control for all configurations                    │   │
│  │  - Pipeline validation                                       │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   Monitoring Engine                           │   │
│  │  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │   │
│  │  │ FileWatcher  │ │ APIPoller    │ │ DBChangeDetector     │ │   │
│  │  │ (inotify/    │ │ (cron-based  │ │ (polling /           │ │   │
│  │  │  polling)    │ │  HTTP call)  │ │  CDC trigger)        │ │   │
│  │  └──────┬───────┘ └──────┬───────┘ └──────────┬───────────┘ │   │
│  │         └────────────────┼────────────────────┘             │   │
│  │                          ▼                                   │   │
│  │              ConditionEvaluator                               │   │
│  │                    │                                         │   │
│  │                    ▼                                          │   │
│  │              Job Created                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                Processing Orchestrator                        │   │
│  │                                                               │   │
│  │  Job ──→ Snapshot ──→ Step Execution ──→ Result          │   │
│  │                                                               │   │
│  │  ┌─────────────────────────────────────────────────────────┐  │   │
│  │  │              Execution Dispatcher                        │  │   │
│  │  │                                                          │  │   │
│  │  │  ExecutionType:                                          │  │   │
│  │  │    PLUGIN    → In-process plugin (Python/C#)             │  │   │
│  │  │    SCRIPT    → Subprocess (any language)                 │  │   │
│  │  │    HTTP      → REST API call                             │  │   │
│  │  │    DOCKER    → Container execution                       │  │   │
│  │  │    NIFI_FLOW → Trigger NiFi process group                │  │   │
│  │  └─────────────────────────────────────────────────────────┘  │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                                                                     │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │                   Recipe Engine                               │   │
│  │  - JSON Schema-based parameter definition                    │   │
│  │  - Version history with diff/compare                         │   │
│  │  - Environment overrides                                     │   │
│  │  - Snapshot at execution time                                │   │
│  └──────────────────────────────────────────────────────────────┘   │
└────────────────────────────┬────────────────────────────────────────┘
                             │
                    ┌────────▼────────┐
                    │   PostgreSQL    │
                    │   (jsonb)       │
                    └─────────────────┘
```

---

## 4. System Layers (4-Layer Architecture)

### Layer 1: Definition Layer — "What CAN exist"

플랫폼이 제공하는 플러그인 타입 카탈로그.
운영자가 아닌 **개발자/관리자**가 등록.

```
┌─────────────────────────────────────────────────┐
│              DEFINITION LAYER                    │
│                                                  │
│  CollectorDefinition    "REST API 수집기"        │
│    └── Version 1.0                               │
│         ├── inputSchema:  { url, auth, interval }│
│         ├── uiSchema:     { field order, help }  │
│         ├── outputSchema: { response format }    │
│         └── executionType: PLUGIN                │
│                                                  │
│  AlgorithmDefinition    "이상치 탐지"             │
│    └── Version 1.0                               │
│         ├── inputSchema:  { threshold, method }  │
│         ├── uiSchema:     { slider, dropdown }   │
│         └── executionType: SCRIPT                │
│                                                  │
│  TransferDefinition     "S3 업로드"              │
│    └── Version 1.0                               │
│         ├── inputSchema:  { bucket, prefix }     │
│         └── executionType: PLUGIN                │
└─────────────────────────────────────────────────┘
```

**Key Design (inspired by Airbyte CDK)**:
- `inputSchema` (JSON Schema): 이 플러그인이 받는 파라미터 정의
- `uiSchema` (UI hints): Web UI에서 어떻게 렌더링할지 (slider, dropdown, password 등)
- `outputSchema`: 실행 결과 포맷 정의
- `executionType`: 어떤 런타임으로 실행하는지

### Layer 2: Instance Layer — "What IS configured"

운영자가 Web UI에서 실제 설정하는 레이어.
**Non-developer가 주로 작업하는 영역.**

```
┌──────────────────────────────────────────────────────────┐
│              INSTANCE LAYER                               │
│                                                           │
│  CollectorInstance "A사 주문 API 수집"                     │
│    ├── definition: REST API 수집기                        │
│    └── config (Recipe):                                   │
│         url: "https://vendor-a.com/api/orders"            │
│         auth: "Bearer ***"                                │
│         interval: "5m"                                    │
│         version: 3  ← 설정 변경 이력 추적                 │
│                                                           │
│  AlgorithmInstance "주문 데이터 이상치 검출"                │
│    ├── definition: 이상치 탐지                            │
│    └── config (Recipe):                                   │
│         threshold: 2.5                                    │
│         method: "z-score"                                 │
│         version: 1                                        │
│                                                           │
│  PipelineInstance "A사 주문 모니터링"                      │
│    ├── steps:                                             │
│    │   1. COLLECT  → CollectorInstance "A사 주문 API"      │
│    │   2. ALGORITHM → AlgorithmInstance "이상치 검출"      │
│    │   3. TRANSFER  → TransferInstance "S3 업로드"        │
│    └── monitoringType: API_POLL                           │
└──────────────────────────────────────────────────────────┘
```

**Key Design (inspired by n8n + NiFi Parameter Contexts)**:
- 모든 Instance의 config는 **Recipe**로 버전 관리됨
- Recipe 변경 시 이전 버전 보존 → diff/compare 가능
- UI에서 form-based 편집 (JSON Schema → auto-generated form)
- 비밀값은 `secretBindingJson`으로 분리 (환경변수 참조)

### Layer 3: Monitoring Layer — "What IS running"

파이프라인의 지속 실행 세션과 이벤트 감지.

```
┌──────────────────────────────────────────────────────┐
│              MONITORING LAYER                         │
│                                                       │
│  PipelineActivation                                   │
│    ├── pipeline: "A사 주문 모니터링"                   │
│    ├── status: RUNNING                                │
│    ├── startedAt: 2026-03-15 09:00:00                │
│    ├── lastHeartbeatAt: 2026-03-15 14:32:10          │
│    ├── lastPolledAt: 2026-03-15 14:30:00             │
│    │                                                  │
│    └── Detected Jobs:                            │
│         ├── Job #1001 (order_batch_20260315_001) │
│         ├── Job #1002 (order_batch_20260315_002) │
│         └── Job #1003 (order_batch_20260315_003) │
└──────────────────────────────────────────────────────┘
```

### Layer 4: Execution Layer — "What HAS happened"

Job 단위 처리 이력. **Hermes의 최대 차별점.**

```
┌──────────────────────────────────────────────────────────────┐
│              EXECUTION LAYER                                  │
│                                                               │
│  Job #1002                                               │
│    ├── sourceKey: "order_batch_20260315_002"                  │
│    ├── detectedAt: 2026-03-15 10:15:00                       │
│    ├── status: FAILED                                         │
│    │                                                          │
│    ├── Execution #1 (INITIAL)                                 │
│    │   ├── Step 1: COLLECT   ✅ 2.3s  (200 records fetched)  │
│    │   ├── Step 2: ALGORITHM ❌ 0.8s  (threshold error)      │
│    │   ├── Step 3: TRANSFER  ⏭️ skipped                      │
│    │   └── Snapshot: { threshold: 2.5, method: "z-score" }   │
│    │                                                          │
│    └── Execution #2 (REPROCESS)  ← Recipe 수정 후 재처리     │
│        ├── Step 2: ALGORITHM ✅ 1.1s  (threshold: 3.0)       │
│        ├── Step 3: TRANSFER  ✅ 0.5s  (uploaded to S3)       │
│        └── Snapshot: { threshold: 3.0, method: "z-score" }   │
│                                                               │
│  EventLog:                                                    │
│    14:15:00 COLLECT_START   "Fetching orders..."             │
│    14:15:02 COLLECT_DONE    "200 records"                    │
│    14:15:02 ALGORITHM_START "Running z-score..."             │
│    14:15:03 ALGORITHM_ERROR "Threshold 2.5 too aggressive"   │
│    14:32:00 REPROCESS_REQ   "User changed threshold to 3.0" │
│    14:32:01 ALGORITHM_START "Running z-score..."             │
│    14:32:02 ALGORITHM_DONE  "3 anomalies detected"          │
│    14:32:02 TRANSFER_START  "Uploading to S3..."             │
│    14:32:03 TRANSFER_DONE   "s3://bucket/results/1002.json" │
└──────────────────────────────────────────────────────────────┘
```

**Key Design (inspired by NiFi Provenance + Temporal Event History)**:
- 모든 실행은 ExecutionSnapshot 보존 → "당시 어떤 설정으로 돌았는지" 감사 가능
- EventLog는 append-only → 완전한 실행 히스토리
- 재처리 시 특정 Step부터 시작 가능 (Step 1 성공했으면 Step 2부터)

---

## 5. Data Model (ERD)

```
┌─────────────────────┐      ┌──────────────────────────┐
│ CollectorDefinition │      │ AlgorithmDefinition      │
│─────────────────────│      │──────────────────────────│
│ id              PK  │      │ id                   PK  │
│ code                │      │ code                     │
│ name                │      │ name                     │
│ description         │      │ description              │
│ category            │      │ category                 │
│ icon_url            │      │ icon_url                 │
│ status              │      │ status                   │
│ created_at          │      │ created_at               │
└────────┬────────────┘      └────────┬─────────────────┘
         │ 1:N                        │ 1:N
┌────────▼────────────┐      ┌────────▼─────────────────┐
│ CollectorDef        │      │ AlgorithmDef             │
│   Version           │      │   Version                │
│─────────────────────│      │──────────────────────────│
│ id              PK  │      │ id                   PK  │
│ definition_id   FK  │      │ definition_id        FK  │
│ version_no          │      │ version_no               │
│ input_schema    JSONB      │ input_schema         JSONB
│ ui_schema       JSONB      │ ui_schema            JSONB
│ output_schema   JSONB      │ output_schema        JSONB
│ default_config  JSONB      │ default_config       JSONB
│ execution_type      │      │ execution_type           │
│ execution_ref       │      │ execution_ref            │
│ is_published        │      │ is_published             │
│ created_at          │      │ created_at               │
└─────────────────────┘      └──────────────────────────┘

┌──────────────────────┐
│ TransferDefinition   │  (same structure as above)
│ TransferDefVersion   │
└──────────────────────┘

         ┌──────────────────────────┐
         │ CollectorInstance        │
         │──────────────────────────│
         │ id                   PK  │
         │ definition_id        FK  │◄── CollectorDefinition
         │ name                     │
         │ description              │
         │ status                   │
         │ created_at               │
         └────────┬─────────────────┘
                  │ 1:N
         ┌────────▼─────────────────┐
         │ CollectorInstance        │
         │   Version                │
         │──────────────────────────│
         │ id                   PK  │
         │ instance_id          FK  │
         │ def_version_id       FK  │◄── CollectorDefVersion
         │ version_no               │
         │ config_json          JSONB  ◄── THE RECIPE
         │ secret_binding_json  JSONB
         │ is_current               │
         │ created_by               │
         │ created_at               │
         │ change_note              │  ◄── "threshold 2.5→3.0으로 변경"
         └──────────────────────────┘

(AlgorithmInstance, TransferInstance — same pattern)

┌──────────────────────────────┐
│ PipelineInstance              │
│──────────────────────────────│
│ id                       PK  │
│ name                         │
│ description                  │
│ monitoring_type              │  ◄── FILE_MONITOR | API_POLL | DB_POLL | EVENT_STREAM
│ monitoring_config        JSONB  ◄── { path, interval, pattern, ... }
│ status                       │  ◄── DRAFT | ACTIVE | PAUSED | ARCHIVED
│ created_at                   │
│ updated_at                   │
└────────┬─────────────────────┘
         │ 1:N
┌────────▼─────────────────────┐
│ PipelineStage                  │
│──────────────────────────────│
│ id                       PK  │
│ pipeline_instance_id     FK  │
│ stage_order                   │  ◄── 1, 2, 3...
│ stage_type                    │  ◄── COLLECT | ALGORITHM | TRANSFER
│ ref_type                     │  ◄── COLLECTOR | ALGORITHM | TRANSFER
│ ref_id                   FK  │  ◄── → Instance ID
│ is_enabled                   │
│ on_error                     │  ◄── STOP | SKIP | RETRY
│ retry_count                  │
│ retry_delay_seconds          │
└──────────────────────────────┘

┌──────────────────────────────┐
│ PipelineActivation           │
│──────────────────────────────│
│ id                       PK  │
│ pipeline_instance_id     FK  │
│ status                       │  ◄── STARTING | RUNNING | STOPPING | STOPPED | ERROR
│ started_at                   │
│ stopped_at                   │
│ last_heartbeat_at            │
│ last_polled_at               │
│ error_message                │
│ worker_id                    │  ◄── which worker runs this
└────────┬─────────────────────┘
         │ 1:N
┌────────▼─────────────────────┐
│ Job                      │
│──────────────────────────────│
│ id                       PK  │
│ pipeline_activation_id   FK  │
│ pipeline_instance_id     FK  │  ◄── denormalized for query
│ source_type                  │  ◄── FILE | API_RESPONSE | DB_CHANGE | EVENT
│ source_key                   │  ◄── "equipment_A_20260315.csv"
│ source_metadata          JSONB  ◄── { size, modified_at, ... }
│ dedup_key                    │  ◄── 중복 방지 키
│ detected_at                  │
│ status                       │  ◄── DETECTED | QUEUED | PROCESSING | COMPLETED | FAILED
│ current_execution_id     FK  │
│ execution_count              │
│ last_completed_at            │
└────────┬─────────────────────┘
         │ 1:N
┌────────▼─────────────────────┐
│ JobExecution             │
│──────────────────────────────│
│ id                       PK  │
│ job_id             FK  │
│ execution_no                 │  ◄── 1, 2, 3...
│ trigger_type                 │  ◄── INITIAL | RETRY | REPROCESS
│ trigger_source               │  ◄── SYSTEM | USER:john | SCHEDULE
│ status                       │  ◄── RUNNING | COMPLETED | FAILED | CANCELLED
│ started_at                   │
│ ended_at                     │
│ duration_ms                  │
│ reprocess_request_id     FK  │  ◄── nullable, links to ReprocessRequest
└────────┬─────────────────────┘
         │ 1:N                          1:1
┌────────▼─────────────────────┐  ┌──────────────────────────┐
│ JobStepExecution        │  │ ExecutionSnapshot         │
│──────────────────────────────│  │──────────────────────────│
│ id                       PK  │  │ id                   PK  │
│ execution_id             FK  │  │ execution_id         FK  │
│ pipeline_stage_id         FK  │  │ pipeline_config      JSONB
│ stage_type                    │  │ collector_config     JSONB
│ stage_order                   │  │ algorithm_config     JSONB
│ status                       │  │ transfer_config      JSONB
│ started_at                   │  │ snapshot_hash            │
│ ended_at                     │  │ created_at               │
│ duration_ms                  │  └──────────────────────────┘
│ input_summary        JSONB   │
│ output_summary       JSONB   │
│ error_code                   │
│ error_message                │
│ retry_attempt                │
└──────────────────────────────┘

┌──────────────────────────────┐
│ ReprocessRequest              │
│──────────────────────────────│
│ id                       PK  │
│ job_id             FK  │
│ requested_by                 │  ◄── "operator:kim"
│ requested_at                 │
│ reason                       │  ◄── "Recipe threshold 변경 후 재처리"
│ start_from_step              │  ◄── nullable, 특정 step부터 재시작
│ use_latest_recipe            │  ◄── true: 최신 Recipe / false: 원래 Snapshot
│ status                       │  ◄── PENDING | APPROVED | EXECUTING | DONE | REJECTED
│ approved_by                  │
│ execution_id             FK  │  ◄── 생성된 JobExecution
└──────────────────────────────┘

┌──────────────────────────────┐
│ ExecutionEventLog             │
│──────────────────────────────│
│ id                       PK  │
│ execution_id             FK  │
│ step_execution_id        FK  │  ◄── nullable
│ event_type                   │  ◄── INFO | WARN | ERROR | DEBUG
│ event_code                   │  ◄── COLLECT_START, ALGORITHM_DONE, ...
│ message                      │
│ detail_json              JSONB  ◄── structured payload
│ created_at                   │
└──────────────────────────────┘
```

---

## 6. Plugin System

### 6.1 Plugin Protocol (inspired by Singer + Airbyte Protocol)

Hermes plugins communicate via **JSON messages over stdin/stdout**.
Any language can implement a plugin.

```
VESSEL PLUGIN PROTOCOL v1
─────────────────────────

Direction: Hermes Core → Plugin (stdin)
  { "type": "CONFIGURE", "config": {...}, "context": {...} }
  { "type": "EXECUTE",   "input": {...} }

Direction: Plugin → Hermes Core (stdout)
  { "type": "LOG",    "level": "INFO", "message": "..." }
  { "type": "OUTPUT", "data": {...} }
  { "type": "ERROR",  "code": "...", "message": "..." }
  { "type": "STATUS", "progress": 0.75 }
  { "type": "DONE",   "summary": {...} }

Exit codes:
  0 = success
  1 = error (check stderr/ERROR messages)
  2 = configuration error
```

### 6.2 Plugin Manifest

Each plugin ships with a `hermes-plugin.json`:

```json
{
  "name": "rest-api-collector",
  "version": "1.0.0",
  "type": "COLLECTOR",
  "description": "Collects data from REST APIs",
  "author": "hermes-community",
  "license": "Apache-2.0",
  "runtime": "python",
  "entrypoint": "main.py",
  "inputSchema": {
    "type": "object",
    "properties": {
      "url":      { "type": "string", "title": "API URL" },
      "method":   { "type": "string", "enum": ["GET", "POST"], "default": "GET" },
      "headers":  { "type": "object", "title": "HTTP Headers" },
      "interval": { "type": "string", "title": "Poll Interval", "default": "5m" },
      "auth_type": { "type": "string", "enum": ["none", "bearer", "basic", "api_key"] }
    },
    "required": ["url"]
  },
  "uiSchema": {
    "url":      { "ui:placeholder": "https://api.example.com/data" },
    "auth_type": { "ui:widget": "radio" },
    "headers":  { "ui:widget": "key-value-editor" },
    "interval": { "ui:widget": "duration-picker" }
  },
  "outputSchema": {
    "type": "object",
    "properties": {
      "records": { "type": "array" },
      "record_count": { "type": "integer" }
    }
  }
}
```

### 6.3 Execution Types

```
┌─────────────┬────────────────────────────────────────────────────┐
│ Type        │ How it works                                       │
├─────────────┼────────────────────────────────────────────────────┤
│ PLUGIN      │ Subprocess: hermes invokes entrypoint,             │
│             │ communicates via stdin/stdout JSON protocol         │
├─────────────┼────────────────────────────────────────────────────┤
│ SCRIPT      │ Run arbitrary script (bash, python, etc.)          │
│             │ Input/output via temp files or env vars             │
├─────────────┼────────────────────────────────────────────────────┤
│ HTTP        │ HTTP call to external service                      │
│             │ Request/response mapped to input/output schema     │
├─────────────┼────────────────────────────────────────────────────┤
│ DOCKER      │ Run plugin in isolated container                   │
│             │ stdin/stdout protocol, volume mounts for data      │
├─────────────┼────────────────────────────────────────────────────┤
│ NIFI_FLOW   │ Trigger NiFi process group via REST API            │
│             │ Poll for completion, retrieve output               │
├─────────────┼────────────────────────────────────────────────────┤
│ INTERNAL    │ Built-in executor (compiled into Hermes core)      │
│             │ For high-performance built-in collectors           │
└─────────────┴────────────────────────────────────────────────────┘
```

---

## 7. Recipe System (Non-Developer Configuration)

### 7.1 Concept

"Recipe"는 Hermes의 핵심 UX 개념.
**SW 개발자가 Definition(스키마)을 정의하면, 운영자가 Recipe(값)을 채운다.**

```
Developer defines:                    Operator fills in:
─────────────────                     ──────────────────
inputSchema: {                        Recipe (config_json): {
  "threshold": {                        "threshold": 3.0,
    "type": "number",                   "method": "z-score",
    "minimum": 0,                       "window_size": 100
    "maximum": 10,                    }
    "description": "이상치 판별 기준"
  },                                  → Web UI renders as:
  "method": {                         ┌─────────────────────────┐
    "type": "string",                 │ 이상치 판별 기준        │
    "enum": ["z-score", "iqr"]        │ [====●========] 3.0     │
  },                                  │                         │
  "window_size": {                    │ 분석 방법               │
    "type": "integer",                │ ● z-score  ○ iqr        │
    "default": 100                    │                         │
  }                                   │ 윈도우 크기             │
}                                     │ [ 100         ]         │
                                      └─────────────────────────┘
uiSchema: {
  "threshold": {
    "ui:widget": "range",
    "ui:help": "값이 클수록 느슨한 탐지"
  },
  "method": {
    "ui:widget": "radio"
  }
}
```

### 7.2 Recipe Versioning

```
CollectorInstance "A사 주문 API"
  └── Version 1 (2026-03-01) config: { interval: "10m", timeout: 30 }
  └── Version 2 (2026-03-10) config: { interval: "5m",  timeout: 30 }  ← current
  └── Version 3 (2026-03-15) config: { interval: "5m",  timeout: 60 }  ← draft

Web UI에서:
  ┌──────────────────────────────────────────────┐
  │  Recipe History                    [Compare] │
  │                                              │
  │  v3 (draft)   2026-03-15  "timeout 증가"     │
  │  v2 (current) 2026-03-10  "interval 단축"    │
  │  v1           2026-03-01  "초기 설정"        │
  │                                              │
  │  Diff v1 → v2:                               │
  │  - interval: "10m" → "5m"                    │
  └──────────────────────────────────────────────┘
```

### 7.3 Recipe at Execution Time

실행 시 Recipe가 ExecutionSnapshot으로 복사됨.
→ 나중에 Recipe를 바꿔도, "이 Job은 당시 어떤 설정으로 돌았는지" 추적 가능.

---

## 8. Web UI Design (n8n-inspired)

### 8.1 Pipeline Designer (Visual Flow Editor)

```
┌──────────────────────────────────────────────────────────────┐
│  Pipeline: A사 주문 모니터링                    [Save] [Run] │
│──────────────────────────────────────────────────────────────│
│                                                              │
│   ┌───────────┐     ┌───────────┐     ┌───────────┐        │
│   │  📥       │     │  🔬       │     │  📤       │        │
│   │ REST API  │────▶│ Anomaly   │────▶│ S3        │        │
│   │ Collector │     │ Detector  │     │ Upload    │        │
│   │           │     │           │     │           │        │
│   │ [Recipe]  │     │ [Recipe]  │     │ [Recipe]  │        │
│   └───────────┘     └───────────┘     └───────────┘        │
│                                                              │
│  Click [Recipe] to edit parameters ──────────────────────── │
│                                                              │
│  ┌─────────────────────────────────────────────────────┐    │
│  │ Recipe Editor: Anomaly Detector          v2 (draft) │    │
│  │─────────────────────────────────────────────────────│    │
│  │                                                      │    │
│  │ 이상치 판별 기준                                     │    │
│  │ [========●════════════] 3.0                          │    │
│  │ ℹ️ 값이 클수록 느슨한 탐지                           │    │
│  │                                                      │    │
│  │ 분석 방법                                            │    │
│  │ ● z-score  ○ IQR  ○ Modified Z-Score                │    │
│  │                                                      │    │
│  │ 윈도우 크기                                          │    │
│  │ [ 100          ]                                     │    │
│  │                                                      │    │
│  │ 변경 사유: [timeout 상향 조정          ]             │    │
│  │                                        [Save as v3]  │    │
│  └─────────────────────────────────────────────────────┘    │
└──────────────────────────────────────────────────────────────┘
```

### 8.2 Monitor Dashboard

```
┌──────────────────────────────────────────────────────────────┐
│  Active Pipelines                                            │
│──────────────────────────────────────────────────────────────│
│                                                              │
│  ● A사 주문 모니터링      RUNNING   ♥ 2s ago    1,247 items │
│  ● 설비B 파일 수집        RUNNING   ♥ 5s ago      892 items │
│  ○ ERP DB 동기화          PAUSED                    0 items │
│  ◉ 설비C 로그 수집        ERROR     ♥ 30m ago     56 items │
│                                                              │
│──────────────────────────────────────────────────────────────│
│  Recent Jobs                              [View All →] │
│                                                              │
│  #1003  order_batch_0315_003   ✅ COMPLETED  2.1s   14:30  │
│  #1002  order_batch_0315_002   ❌ FAILED     0.8s   14:15  │
│         └─ Algorithm step failed: threshold exceeded         │
│         └─ [Reprocess] [View Detail]                         │
│  #1001  order_batch_0315_001   ✅ COMPLETED  1.9s   14:00  │
└──────────────────────────────────────────────────────────────┘
```

### 8.3 Job Explorer

```
┌──────────────────────────────────────────────────────────────┐
│  Job #1002                                              │
│──────────────────────────────────────────────────────────────│
│  Source: order_batch_20260315_002                            │
│  Pipeline: A사 주문 모니터링                                 │
│  Detected: 2026-03-15 14:15:00                              │
│  Status: FAILED → COMPLETED (after reprocess)               │
│                                                              │
│  Execution History:                                          │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ #1 INITIAL (14:15:00)                                  │  │
│  │   COLLECT   ✅ 2.3s  "200 records fetched"             │  │
│  │   ALGORITHM ❌ 0.8s  "threshold 2.5 too aggressive"    │  │
│  │   TRANSFER  ⏭️ skipped                                 │  │
│  │   Recipe snapshot: { threshold: 2.5 }                   │  │
│  │                                                         │  │
│  │ #2 REPROCESS (14:32:00) by operator:kim                │  │
│  │   "Recipe threshold 2.5→3.0 변경 후 재처리"             │  │
│  │   ALGORITHM ✅ 1.1s  "3 anomalies detected"            │  │
│  │   TRANSFER  ✅ 0.5s  "uploaded to S3"                  │  │
│  │   Recipe snapshot: { threshold: 3.0 }                   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                              │
│  Event Log:                              [Download Full Log] │
│  14:15:00.000  INFO   COLLECT_START   "Fetching orders..."  │
│  14:15:02.312  INFO   COLLECT_DONE    "200 records"         │
│  14:15:02.315  INFO   ALG_START       "Running z-score"     │
│  14:15:03.102  ERROR  ALG_ERROR       "Threshold exceeded"  │
│  14:32:00.100  INFO   REPROCESS_REQ   "by operator:kim"    │
│  14:32:01.200  INFO   ALG_START       "Running z-score"     │
│  14:32:02.350  INFO   ALG_DONE        "3 anomalies"        │
│  14:32:02.355  INFO   TRANSFER_START  "Uploading to S3"    │
│  14:32:02.890  INFO   TRANSFER_DONE   "s3://bucket/1002"   │
└──────────────────────────────────────────────────────────────┘
```

---

## 9. NiFi Integration (Optional Backend)

Hermes은 NiFi 없이 독립 실행되지만, NiFi가 있으면 활용 가능.

```
┌──────────────────────────────────────────┐
│           VESSEL CORE                     │
│                                           │
│  ExecutionDispatcher                      │
│    │                                      │
│    ├── PLUGIN → Hermes plugin protocol    │  ◄── NiFi 없이 독립 실행
│    ├── SCRIPT → subprocess                │
│    ├── HTTP   → REST call                 │
│    │                                      │
│    └── NIFI_FLOW ──────────────────────── │ ─── NiFi 연동
│         │                                 │
│         │  NiFi REST API v1.9.x:          │
│         │  1. GET /process-groups/{id}    │
│         │  2. PUT /processors/{id}/run    │
│         │  3. GET /provenance             │
│         │  4. GET /flowfile-queues        │
│         │                                 │
└─────────┼─────────────────────────────────┘
          │
          ▼
┌─────────────────────────┐
│  Apache NiFi 1.9.x      │
│  (Separate deployment)   │
│                          │
│  - Clustering            │
│  - Backpressure          │
│  - 300+ Processors       │
│  - Data Provenance       │
│                          │
│  Hermes uses NiFi for:   │
│  - Heavy-duty collection │
│  - Complex routing       │
│  - Distributed execution │
└─────────────────────────┘
```

**NiFi 연동 시나리오**: 대량 파일 수집은 NiFi에게 맡기고, Hermes은 Job 추적 + Recipe 관리 + 재처리만 담당.

---

## 10. API Design

### 10.1 Definition APIs

```
# Collector Definitions
GET    /api/v1/definitions/collectors
POST   /api/v1/definitions/collectors
GET    /api/v1/definitions/collectors/{id}
GET    /api/v1/definitions/collectors/{id}/versions
POST   /api/v1/definitions/collectors/{id}/versions

# Algorithm Definitions (same pattern)
GET    /api/v1/definitions/algorithms
POST   /api/v1/definitions/algorithms
...

# Transfer Definitions (same pattern)
GET    /api/v1/definitions/transfers
...
```

### 10.2 Instance APIs

```
# Collector Instances
GET    /api/v1/instances/collectors
POST   /api/v1/instances/collectors
GET    /api/v1/instances/collectors/{id}
PUT    /api/v1/instances/collectors/{id}

# Instance Recipes (versioned config)
GET    /api/v1/instances/collectors/{id}/recipes
POST   /api/v1/instances/collectors/{id}/recipes           # new version
GET    /api/v1/instances/collectors/{id}/recipes/{version}
GET    /api/v1/instances/collectors/{id}/recipes/diff?from=1&to=2
POST   /api/v1/instances/collectors/{id}/recipes/{version}/publish
```

### 10.3 Pipeline APIs

```
# Pipelines
GET    /api/v1/pipelines
POST   /api/v1/pipelines
GET    /api/v1/pipelines/{id}
PUT    /api/v1/pipelines/{id}

# Pipeline Steps
GET    /api/v1/pipelines/{id}/steps
POST   /api/v1/pipelines/{id}/steps
PUT    /api/v1/pipelines/{id}/steps/{stepId}
DELETE /api/v1/pipelines/{id}/steps/{stepId}
PUT    /api/v1/pipelines/{id}/steps/reorder

# Pipeline Lifecycle
POST   /api/v1/pipelines/{id}/activate      # start monitoring
POST   /api/v1/pipelines/{id}/deactivate    # stop monitoring
GET    /api/v1/pipelines/{id}/activations    # history
GET    /api/v1/pipelines/{id}/status         # current state
```

### 10.4 Job APIs

```
# Jobs
GET    /api/v1/jobs                    # list with filters
GET    /api/v1/jobs/{id}
GET    /api/v1/jobs/{id}/executions
GET    /api/v1/jobs/{id}/executions/{execId}
GET    /api/v1/jobs/{id}/executions/{execId}/steps
GET    /api/v1/jobs/{id}/executions/{execId}/snapshot
GET    /api/v1/jobs/{id}/executions/{execId}/logs

# Reprocess
POST   /api/v1/jobs/{id}/reprocess
  Body: {
    "reason": "Recipe threshold 변경",
    "start_from_step": 2,
    "use_latest_recipe": true
  }

# Bulk operations
POST   /api/v1/jobs/bulk-reprocess
  Body: {
    "job_ids": [1002, 1005, 1008],
    "reason": "Algorithm 버그 수정 후 일괄 재처리"
  }
```

### 10.5 WebSocket (Real-time)

```
WS /api/v1/ws/pipeline/{id}/events
  → { "type": "WORKITEM_CREATED", "job": {...} }
  → { "type": "STEP_COMPLETED", "stepExecution": {...} }
  → { "type": "PIPELINE_HEARTBEAT", "activation": {...} }

WS /api/v1/ws/jobs/{id}/logs
  → { "type": "LOG", "event": {...} }  (live streaming)
```

---

## 11. Processing Flows

### 11.1 Monitoring Flow (Continuous)

```python
# Pseudocode: MonitoringEngine

async def run_monitoring(activation: PipelineActivation):
    pipeline = activation.pipeline_instance
    monitor = create_monitor(pipeline.monitoring_type, pipeline.monitoring_config)

    while activation.status == RUNNING:
        # 1. Check for events
        events = await monitor.poll()

        for event in events:
            # 2. Evaluate conditions
            if condition_evaluator.should_create_job(event):

                # 3. Dedup check
                dedup_key = generate_dedup_key(event)
                if not job_repo.exists(dedup_key):

                    # 4. Create Job
                    job = Job(
                        source_type=event.type,
                        source_key=event.key,
                        dedup_key=dedup_key,
                        status=DETECTED
                    )
                    job_repo.save(job)

                    # 5. Queue for processing
                    await processing_queue.enqueue(job.id)

        # 6. Update heartbeat
        activation.last_heartbeat_at = now()
        activation.last_polled_at = now()
        await activation_repo.update(activation)

        # 7. Wait for next poll
        await sleep(pipeline.monitoring_config.interval)
```

### 11.2 Processing Flow (Per Job)

```python
# Pseudocode: ProcessingOrchestrator

async def process_job(job_id: int, trigger: TriggerType,
                            start_from_step: int = 1,
                            use_latest_recipe: bool = True):
    job = job_repo.get(job_id)
    pipeline = pipeline_repo.get(job.pipeline_instance_id)
    steps = pipeline_stage_repo.get_ordered(pipeline.id)

    # 1. Create execution record
    execution = JobExecution(
        job_id=job.id,
        trigger_type=trigger,
        status=RUNNING
    )
    execution_repo.save(execution)

    # 2. Snapshot current configuration
    snapshot = snapshot_resolver.capture(pipeline, steps, use_latest_recipe)
    snapshot_repo.save(execution.id, snapshot)

    # 3. Execute steps in order
    previous_output = None
    for step in steps:
        if step.stage_order < start_from_step:
            # Use cached output from previous successful execution
            previous_output = get_cached_step_output(job, step)
            continue

        if not step.is_enabled:
            continue

        step_execution = JobStepExecution(
            execution_id=execution.id,
            pipeline_stage_id=step.id,
            stage_type=step.stage_type,
            status=RUNNING
        )
        step_execution_repo.save(step_execution)

        try:
            # 4. Dispatch to appropriate executor
            config = snapshot.get_config_for_step(step)
            result = await execution_dispatcher.execute(
                execution_type=config.execution_type,
                execution_ref=config.execution_ref,
                config=config.resolved_config,
                input_data=previous_output,
                context={
                    "job_id": job.id,
                    "stage_type": step.stage_type,
                    "execution_id": execution.id
                }
            )

            step_execution.status = COMPLETED
            step_execution.output_summary = result.summary
            previous_output = result.output

        except Exception as e:
            step_execution.status = FAILED
            step_execution.error_message = str(e)
            event_log.write(execution.id, step_execution.id, ERROR, str(e))

            if step.on_error == STOP:
                execution.status = FAILED
                break
            elif step.on_error == SKIP:
                continue
            elif step.on_error == RETRY:
                # retry logic with backoff
                ...

        finally:
            step_execution_repo.update(step_execution)

    # 5. Update final status
    if execution.status != FAILED:
        execution.status = COMPLETED
    execution.ended_at = now()
    execution_repo.update(execution)
    job.status = execution.status
    job_repo.update(job)
```

---

## 12. Technology Stack

```
┌─────────────────────────────────────────────────┐
│  VESSEL TECHNOLOGY STACK                         │
├─────────────────────────────────────────────────┤
│                                                  │
│  Backend API:                                    │
│    Python 3.12 + FastAPI                         │
│    OR                                            │
│    C# ASP.NET Core 8                             │
│    (both are first-class, choose per deployment) │
│                                                  │
│  Database:                                       │
│    PostgreSQL 15+ (jsonb for schemas/configs)    │
│                                                  │
│  ORM:                                            │
│    SQLAlchemy 2.0 (Python)                       │
│    OR EF Core 8 (C#)                             │
│                                                  │
│  Task Queue:                                     │
│    DB-based queue (prototype)                    │
│    → Redis/RabbitMQ (production)                 │
│                                                  │
│  Web UI:                                         │
│    React 18 + TypeScript                         │
│    React Flow (pipeline visual editor)           │
│    react-jsonschema-form (recipe editor)         │
│    TanStack Query (data fetching)                │
│    Tailwind CSS                                  │
│                                                  │
│  Plugin Runtime:                                 │
│    stdin/stdout JSON protocol (any language)     │
│    subprocess management                         │
│    Optional: Docker execution                    │
│                                                  │
│  Real-time:                                      │
│    WebSocket (pipeline events, live logs)         │
│                                                  │
│  NiFi Integration (optional):                    │
│    NiFi REST API client (1.9.x compatible)       │
│                                                  │
│  Deployment:                                     │
│    Docker Compose (development)                  │
│    Kubernetes Helm chart (production)             │
│    Single binary option (Go rewrite, future)     │
└─────────────────────────────────────────────────┘
```

---

## 13. Project Structure

```
hermes/
├── docs/
│   ├── ARCHITECTURE.md          ← this file
│   ├── PLUGIN_PROTOCOL.md       ← plugin development guide
│   └── API.md                   ← API reference
│
├── backend/                     ← Python FastAPI (primary)
│   ├── hermes/
│   │   ├── api/                 ← REST endpoints
│   │   │   ├── definitions.py
│   │   │   ├── instances.py
│   │   │   ├── pipelines.py
│   │   │   ├── jobs.py
│   │   │   └── websocket.py
│   │   ├── domain/              ← entities & business logic
│   │   │   ├── models/
│   │   │   │   ├── definition.py
│   │   │   │   ├── instance.py
│   │   │   │   ├── pipeline.py
│   │   │   │   ├── job.py
│   │   │   │   ├── execution.py
│   │   │   │   └── recipe.py
│   │   │   └── services/
│   │   │       ├── pipeline_manager.py
│   │   │       ├── recipe_engine.py
│   │   │       ├── monitoring_engine.py
│   │   │       ├── condition_evaluator.py
│   │   │       ├── processing_orchestrator.py
│   │   │       ├── snapshot_resolver.py
│   │   │       └── execution_dispatcher.py
│   │   ├── infrastructure/      ← DB, external integrations
│   │   │   ├── database/
│   │   │   │   ├── migrations/
│   │   │   │   └── repositories/
│   │   │   ├── nifi/            ← NiFi REST client
│   │   │   └── queue/           ← task queue
│   │   ├── plugins/             ← plugin runtime manager
│   │   │   ├── protocol.py      ← stdin/stdout protocol
│   │   │   ├── registry.py      ← plugin discovery
│   │   │   ├── executor.py      ← plugin subprocess mgmt
│   │   │   └── docker.py        ← Docker execution
│   │   └── workers/             ← background workers
│   │       ├── monitoring_worker.py
│   │       └── processing_worker.py
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
│
├── webapp/                      ← React frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── pipeline-designer/   ← React Flow visual editor
│   │   │   ├── recipe-editor/       ← JSON Schema form
│   │   │   ├── monitor-dashboard/
│   │   │   ├── workitem-explorer/
│   │   │   └── plugin-marketplace/
│   │   ├── api/                     ← API client
│   │   ├── hooks/
│   │   └── types/
│   ├── package.json
│   └── Dockerfile
│
├── plugins/                     ← built-in plugins
│   ├── collectors/
│   │   ├── rest-api/
│   │   │   ├── hermes-plugin.json
│   │   │   └── main.py
│   │   ├── file-watcher/
│   │   ├── db-query/
│   │   └── sftp/
│   ├── algorithms/
│   │   ├── passthrough/         ← default: no transformation
│   │   ├── json-transform/
│   │   └── csv-parser/
│   └── transfers/
│       ├── file-output/
│       ├── rest-api/
│       ├── db-insert/
│       └── s3-upload/
│
├── docker-compose.yml
├── README.md
├── LICENSE                      ← Apache 2.0
└── CLAUDE.md
```

---

## 14. Prototype Scope

### Phase 1: Core (MVP)
```
[x] PostgreSQL schema + migrations
[x] Definition CRUD (Collector, Algorithm, Transfer)
[x] Instance CRUD with Recipe versioning
[x] Pipeline CRUD with Step ordering
[x] Pipeline Activation (start/stop)
[x] Monitoring Engine (file watcher + API poller)
[x] Job creation + dedup
[x] Processing Orchestrator (sequential step execution)
[x] Execution Dispatcher (PLUGIN + SCRIPT types)
[x] ExecutionSnapshot capture
[x] EventLog recording
[x] ReprocessRequest (single + bulk)
[x] Basic Web UI (list/detail views, recipe form editor)
```

### Phase 2: Visual UX
```
[ ] Pipeline Designer (React Flow drag-and-drop)
[ ] Recipe Editor (react-jsonschema-form with custom widgets)
[ ] Monitor Dashboard (real-time WebSocket)
[ ] Job Explorer (search, filter, timeline view)
[ ] Recipe diff/compare view
```

### Phase 3: Production Features
```
[ ] NiFi integration (NIFI_FLOW execution type)
[ ] Docker plugin execution
[ ] Plugin marketplace (discovery + install)
[ ] Multi-worker support
[ ] Authentication & RBAC
[ ] Audit trail
[ ] Metrics & alerting (Prometheus)
```

### Phase 4: Scale
```
[ ] Distributed execution (Redis/RabbitMQ queue)
[ ] Kubernetes operator
[ ] Horizontal scaling
[ ] Plugin SDK (Python, C#, Go)
```

---

## 15. Competitive Positioning

```
                    Heavy / Complex
                         │
                    NiFi ●
                         │
              Kafka ●    │
             Connect     │     ● Airbyte
                         │
                         │
    Simple ──────────────┼──────────────── Rich UI
                         │
            Benthos ●    │         ● n8n
                         │
            Singer ●     │    ★ Hermes
                         │    (here)
           Telegraf ●    │
                         │
                    Lightweight
```

**Hermes's sweet spot**:
- Lighter than NiFi, richer UI than Benthos
- Per-item tracking that nobody else offers (except NiFi)
- Recipe management for non-developers
- Reprocessing as first-class citizen
- NiFi-friendly but NiFi-independent
