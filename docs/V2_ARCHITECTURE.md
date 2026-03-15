# Hermes V2 — Architecture & Design Specification

> **Hermes V2**: Enterprise-grade, lightweight data processing platform with
> distributed execution, disk-based storage, and production-hardened reliability.
>
> "The .NET NiFi — NiFi's power, n8n's simplicity, in a package that actually ships."

---

## 1. V2 Vision

### 1.1 Position

Hermes V2 positions itself as **"The .NET NiFi"** — an enterprise-grade, lightweight
alternative to Apache NiFi, Airbyte, and Airflow for organizations that want:

- **NiFi-grade reliability** (back-pressure, content repository, exactly-once)
- **n8n-grade usability** (visual pipeline designer, form-based config)
- **Cloud-native deployment** (Kubernetes, Docker, horizontal scaling)
- **Polyglot plugins** (Python, .NET, Go, any language via gRPC or stdin/stdout)
- **.NET-native core** for teams invested in the Microsoft ecosystem

### 1.2 Target Market

| Segment | Pain Point | Hermes V2 Solution |
|---|---|---|
| **NiFi shops** | JVM 2GB+ footprint, complex UI, Java-only plugins | 10x lighter, modern React UI, any-language plugins |
| **Airflow/Dagster teams** | No per-item tracking, developer-centric | Job Explorer, operator-first UI |
| **Airbyte users** | EL-only, Docker-per-connector overhead | Full ELT+algorithm, lightweight plugin protocol |
| **n8n users** | Not built for high-volume, no item tracking | Production-grade engine with item-level provenance |
| **Benthos users** | No UI, no visual pipeline design | Full web UI with React Flow pipeline designer |
| **Custom pipeline teams** | Maintaining in-house scripts | Drop-in replacement with observability and reprocessing |

### 1.3 Exit Strategy Features

Features that make Hermes acquisition-worthy for enterprise buyers:

| Feature | Acquirer Appeal |
|---|---|
| Multi-tenancy with workspace isolation | SaaS-ready, platform play |
| Complete audit trail + data lineage | Compliance (SOC2, ISO27001, GDPR) |
| Plugin marketplace + ecosystem | Network effects, community moat |
| Git-based pipeline versioning | GitOps, enterprise workflow integration |
| Kubernetes operator + Helm charts | Cloud-native, easy enterprise adoption |
| RBAC + SSO + secrets management | Enterprise security requirements |
| Prometheus + OpenTelemetry + Grafana | Observability stack integration |
| NiFi migration bridge | Installed-base capture strategy |

### 1.4 V1 → V2 Gap Analysis

| Area | V1 State | V2 Target |
|---|---|---|
| **Deployment** | Single process | Distributed cluster (coordinator + workers) |
| **Data flow** | In-memory only | Disk-based Content Repository + memory-mapped I/O |
| **Failure handling** | Basic retry per step | DLQ, circuit breaker, poison pill detection, WAL |
| **Back-pressure** | None | Queue depth monitoring, soft/hard limits, disk overflow |
| **Schema** | Static JSON Schema in definitions | Dynamic schema registry, drift detection, evolution |
| **Observability** | WebSocket events + logs | Prometheus, OpenTelemetry, structured logging, alerting |
| **Security** | None (open access) | JWT/OIDC, RBAC, audit log, secrets management, TLS |
| **Large data** | Full payload in memory | Content-addressed storage, streaming, chunked transfer |
| **Exactly-once** | At-most-once | Checkpointing, idempotency keys, fencing tokens |
| **Pipeline topology** | Linear chain only | DAG with routing, fan-out, merge, conditional steps |

---

## 2. Distributed Architecture

### 2.1 Node Types

```
Hermes Cluster
├── Coordinator Node (1, or HA pair with active/standby)
│   ├── Pipeline Management
│   │   - Pipeline CRUD, Recipe storage, version control
│   │   - Pipeline validation and activation
│   │
│   ├── Work Distribution
│   │   - Work item assignment and load balancing
│   │   - Affinity rules enforcement
│   │   - Rebalancing on topology changes
│   │
│   ├── API Gateway
│   │   - REST API serving (all /api/v1/* endpoints)
│   │   - WebSocket hub for real-time events
│   │   - Web UI static asset serving
│   │
│   ├── Schema Registry
│   │   - Central schema storage and versioning
│   │   - Compatibility checking
│   │   - Drift detection and alerting
│   │
│   ├── Health Monitor
│   │   - Worker heartbeat tracking
│   │   - Pipeline activation health
│   │   - Cluster-wide metrics aggregation
│   │
│   └── Metadata Store
│       - PostgreSQL for all metadata
│       - Content Repository index
│       - WAL coordination
│
├── Worker Nodes (N, horizontal scale)
│   ├── Monitoring Execution
│   │   - FileWatcher, APIPoller, KafkaConsumer, DBChangeDetector
│   │   - Event detection → Job creation
│   │
│   ├── Job Processing
│   │   - Step-by-step execution (COLLECT → ALGORITHM → TRANSFER)
│   │   - Plugin/container/script invocation
│   │   - Local Content Repository partition
│   │
│   ├── Plugin Runtime
│   │   - gRPC plugin host (long-lived plugins)
│   │   - Subprocess launcher (stdin/stdout protocol)
│   │   - Docker executor (container-based plugins)
│   │
│   ├── Local State
│   │   - In-memory work queue (with disk swap)
│   │   - Content Repository local partition
│   │   - Cached pipeline configs (survive coordinator outage)
│   │
│   └── Heartbeat Agent
│       - Periodic heartbeat to coordinator (default 5s)
│       - Resource reporting (CPU, memory, disk, active items)
│       - Graceful shutdown coordination
│
└── Edge Nodes (optional, for remote/disconnected sites)
    ├── Local Collection
    │   - Runs monitors independently
    │   - Local Content Repository
    │   - Buffered forwarding to cluster
    │
    ├── Offline Operation
    │   - Continues collecting when disconnected
    │   - Local queue with configurable retention
    │   - Automatic sync on reconnect
    │
    └── Lightweight Footprint
        - Minimal dependencies (no PostgreSQL required)
        - SQLite for local metadata
        - Configurable resource limits
```

### 2.2 Leader Election & Coordination

#### Option A: PostgreSQL Advisory Locks (Recommended for simplicity)

```
Coordinator Election via PostgreSQL Advisory Locks
──────────────────────────────────────────────────

1. Each coordinator candidate attempts:
   SELECT pg_try_advisory_lock(hashtext('hermes-coordinator'))

2. Winner holds the lock for its session lifetime

3. Other candidates poll every 5 seconds:
   SELECT pg_try_advisory_lock(hashtext('hermes-coordinator'))

4. If active coordinator crashes, PostgreSQL releases the lock
   → next candidate acquires it within 5 seconds

Advantages:
  - No additional infrastructure (uses existing PostgreSQL)
  - Well-understood semantics
  - Automatic cleanup on process crash

Disadvantages:
  - Tied to PostgreSQL availability
  - Slightly higher failover time (~5-10s)
```

#### Option B: etcd (Recommended for large clusters)

```
Coordinator Election via etcd Lease
────────────────────────────────────

1. Each candidate creates a lease with TTL=10s
2. Candidates race to create key "/hermes/coordinator/leader"
   with their lease attached
3. Winner refreshes lease via KeepAlive stream
4. On crash, lease expires → key deleted → new election

etcd also provides:
  - Distributed configuration storage
  - Watch-based change notification
  - Consistent reads for cluster state
```

#### Split-Brain Prevention

```
Split-Brain Prevention Strategy
────────────────────────────────

1. FENCING TOKENS
   - Coordinator increments a monotonic fencing token on election
   - All writes to PostgreSQL include the fencing token
   - PostgreSQL trigger rejects writes with stale tokens

2. QUORUM REQUIREMENT
   - Coordinator requires connection to >50% of known workers
   - If isolated, coordinator demotes itself to standby

3. WORKER BEHAVIOR ON PARTITION
   - Workers cache last-known pipeline configs
   - Continue processing in-flight items
   - Stop accepting NEW work items
   - Buffer completed results locally
   - Reconcile with new coordinator on reconnect

4. RECONCILIATION PROTOCOL
   After partition heals:
   a. New coordinator collects worker state reports
   b. Identifies orphaned work items (PROCESSING but no worker)
   c. Identifies duplicate completions (same item, different workers)
   d. Applies last-writer-wins with fencing token tiebreak
   e. Re-queues orphaned items
```

### 2.3 Work Distribution

#### Assignment Algorithm

```
Work Distribution: Weighted Round-Robin with Affinity
─────────────────────────────────────────────────────

WorkAssigner
├── Input: new Job + pipeline context
├── Step 1: Filter eligible workers
│   - Worker status == HEALTHY
│   - Worker has required plugins/capabilities
│   - Worker not at capacity (queue_depth < max_queue)
│
├── Step 2: Apply affinity rules
│   - Pipeline affinity: "pipeline X always runs on worker group A"
│   - Data locality: prefer worker where source data is local
│   - Plugin affinity: prefer worker where plugin is already loaded
│   - Sticky session: same source_key → same worker (for state)
│
├── Step 3: Score eligible workers
│   score = (
│     w1 * (1 - cpu_usage) +          # CPU headroom
│     w2 * (1 - memory_usage) +       # Memory headroom
│     w3 * (1 - queue_depth/max) +    # Queue headroom
│     w4 * affinity_bonus +            # Affinity match
│     w5 * locality_bonus              # Data locality
│   )
│
├── Step 4: Assign to highest-scoring worker
│   - Optimistic assignment (no distributed lock needed)
│   - Worker can reject if over capacity (rare, triggers reassignment)
│
└── Step 5: Record assignment
    - job.assigned_worker_id = worker.id
    - job.assigned_at = now()
    - Emit WORKITEM_ASSIGNED event
```

#### Rebalancing

```
Rebalancing Triggers
────────────────────

1. WORKER JOIN
   - New worker registers with coordinator
   - Coordinator does NOT migrate existing items
   - New items preferentially routed to new worker (higher score due to empty queue)
   - Optional: "drain and rebalance" mode moves items from overloaded workers

2. WORKER LEAVE (graceful)
   - Worker sends DRAINING status
   - Coordinator stops assigning new items
   - Worker completes in-flight items
   - Worker sends STOPPED status
   - No rebalancing needed

3. WORKER CRASH (ungraceful)
   - Coordinator detects missing heartbeats (3 consecutive misses = 15s)
   - Marks worker as DEAD
   - Scans for items assigned to dead worker:
     - PROCESSING → re-queue as QUEUED (will be reassigned)
     - QUEUED → reassign to another worker
   - Emits WORKER_FAILED alert

4. LOAD IMBALANCE
   - Periodic check (every 60s)
   - If max_queue/min_queue > 2.0, trigger rebalance
   - Move QUEUED (not PROCESSING) items from overloaded to underloaded
```

#### Work Stealing

```
Steal-Based Work Queue
──────────────────────

When a worker's local queue is empty:
1. Worker requests work from coordinator
2. Coordinator checks other workers' queues
3. Steals QUEUED items from the most-loaded worker
4. Transfers item assignment to the requesting worker

This is lazy rebalancing — avoids unnecessary item movement
while naturally converging to balanced load.
```

### 2.4 Node Failure Handling

#### Worker Crash

```
Worker Crash Recovery
─────────────────────

Detection:
  - Coordinator: 3 missed heartbeats (15s default)
  - Other workers: gossip protocol detects peer absence

Recovery:
  1. Coordinator marks worker as DEAD
  2. Query: SELECT * FROM jobs
     WHERE assigned_worker_id = {dead_worker}
     AND status IN ('PROCESSING', 'QUEUED')
  3. For each orphaned item:
     a. If PROCESSING:
        - Check Content Repository for partial outputs
        - If checkpoint exists → resume from checkpoint on new worker
        - If no checkpoint → reset to QUEUED, increment retry_count
     b. If QUEUED:
        - Clear assigned_worker_id
        - Item re-enters assignment queue
  4. Emit WORKER_FAILED event with affected item count
  5. Update pipeline activation health scores

Safeguard:
  - Items with retry_count >= max_retries → route to DLQ
  - Prevents infinite retry loops from persistent failures
```

#### Coordinator Crash

```
Coordinator Crash Recovery
──────────────────────────

Detection:
  - Workers detect coordinator absence (heartbeat response timeout)
  - Standby coordinator detects leader lock release

Worker Behavior During Coordinator Outage:
  1. Workers continue processing in-flight items (no interruption)
  2. Workers cache last-known pipeline configs (immutable snapshots)
  3. Workers buffer completed results locally:
     - Write to local WAL
     - Update local state
  4. Workers stop accepting NEW monitoring events
     (or continue if configured for autonomous operation)
  5. Workers retry coordinator connection with exponential backoff

New Coordinator Election:
  1. Standby acquires leader lock (PostgreSQL advisory lock)
  2. New coordinator loads state from PostgreSQL
  3. Broadcasts COORDINATOR_ELECTED to all workers
  4. Workers reconnect and report:
     - Items completed during outage
     - Items still in progress
     - Local queue state
  5. Coordinator reconciles and resumes normal operation

Coordinator State Recovery:
  - All coordinator state is in PostgreSQL (stateless coordinator)
  - Pipeline configs, work items, executions — all persisted
  - In-memory caches rebuilt from DB on startup
  - No state loss on coordinator failover
```

#### Network Partition

```
Network Partition Handling (CAP: AP with Eventual Consistency)
─────────────────────────────────────────────────────────────

Partition Detected:
  Workers cannot reach coordinator but can reach data sources

Worker Autonomous Mode:
  1. Continue processing in-flight items
  2. Continue monitoring if configured (autonomous_monitoring=true)
  3. New work items queued locally with provisional IDs
  4. Results written to local Content Repository
  5. State changes written to local WAL

Partition Healed:
  1. Worker reconnects to coordinator
  2. Reconciliation protocol:
     a. Worker uploads local WAL entries
     b. Coordinator replays entries, resolving conflicts:
        - Duplicate work items → merge by dedup_key
        - ID conflicts → coordinator assigns canonical IDs
        - Status conflicts → latest timestamp wins
     c. Worker receives canonical state
     d. Worker purges local provisional data
  3. Normal operation resumes

Conflict Resolution Rules:
  - Work item status: higher-progress state wins
    (COMPLETED > FAILED > PROCESSING > QUEUED > DETECTED)
  - Recipe versions: coordinator version is authoritative
  - Content: content-addressed (SHA-256), so identical content auto-deduplicates
```

#### Poison Pill Detection

```
Poison Pill Detection & Quarantine
───────────────────────────────────

A "poison pill" is a work item that consistently crashes workers
or causes failures regardless of which worker processes it.

Detection:
  - Track failure count per job.dedup_key
  - If failures >= poison_threshold (default: 3):
    - Across different workers (not just retries on same worker)
    - Within a time window (default: 1 hour)
  → Mark as POISON

Response:
  1. Route item to Dead Letter Queue
  2. Emit POISON_PILL_DETECTED alert
  3. Include diagnostic context:
     - All error messages from failed attempts
     - Worker IDs that failed
     - Step that consistently fails
     - Input data snapshot (if available in Content Repository)
  4. Auto-pause pipeline if poison_rate > threshold (default: 10% of items)

Recovery:
  - Operator investigates via DLQ Explorer
  - Fix root cause (recipe change, plugin bug, data issue)
  - Replay from DLQ with corrected config
```

---

## 3. Storage Architecture (Disk-Based, NiFi-Inspired)

### 3.1 Content Repository

```
Problem:
  V1 flows all data through memory (JobContext carries data inline).
  This limits throughput to available RAM and causes OOM on large payloads.

Solution:
  Disk-based Content Repository with content-addressed storage,
  inspired by NiFi's Content Repository and Git's object store.

ContentRepository/
├── config.yaml                    — repository configuration
├── claims/                        — immutable content blobs
│   ├── aa/                        — first 2 chars of SHA-256
│   │   ├── bb/                    — next 2 chars
│   │   │   ├── aabb1234abcd...    — full SHA-256 hash as filename
│   │   │   └── aabb5678efgh...
│   │   └── cc/
│   │       └── ...
│   └── dd/
│       └── ...
├── index/                         — claim metadata (SQLite or LevelDB)
│   └── claims.db
│       Table: claims
│       ├── claim_id (SHA-256)     — primary key
│       ├── size_bytes             — content size
│       ├── mime_type              — content type
│       ├── ref_count              — reference count
│       ├── created_at             — creation timestamp
│       └── last_accessed_at       — for LRU eviction
│
├── journal/                       — write-ahead log
│   ├── wal-000001.log
│   ├── wal-000002.log
│   └── checkpoint-000001.dat
│
└── tmp/                           — in-progress writes
    └── write-{uuid}.tmp
```

#### Content Lifecycle

```
Content Write Flow
──────────────────

1. Writer opens tmp file: tmp/write-{uuid}.tmp
2. Data streamed to tmp file (no full-memory buffering)
3. SHA-256 computed incrementally during write
4. On completion:
   a. Compute final hash
   b. Check if claims/{hash} already exists (dedup)
   c. If new: atomic rename tmp → claims/{aa}/{bb}/{hash}
   d. If exists: delete tmp, increment ref_count
5. Return ClaimReference { claim_id, size, mime_type }

Content Read Flow
─────────────────

1. Caller provides claim_id (SHA-256)
2. Repository maps to file path: claims/{aa}/{bb}/{claim_id}
3. Return read stream (memory-mapped for files < 64MB, streaming for larger)
4. Update last_accessed_at (async, non-blocking)

Content Garbage Collection
──────────────────────────

Background process (runs every 5 minutes):
1. Scan index for claims with ref_count == 0
2. Grace period: only delete if last_accessed_at > 1 hour ago
3. Delete claim file
4. Remove index entry
5. Log deletion for audit

Reference Counting
──────────────────

Job → claim_id mapping maintained in PostgreSQL:
  Table: job_content_refs
  ├── job_id
  ├── stage_order
  ├── direction (INPUT | OUTPUT)
  ├── claim_id
  └── created_at

When Job is deleted/archived → decrement ref_count for all its claims
Content deduplication is automatic: same data → same hash → same claim
```

#### Memory-Mapped Access

```
Memory-Mapped I/O Strategy
──────────────────────────

For content < 64MB (configurable):
  - Use memory-mapped files (mmap)
  - OS manages page cache automatically
  - Near-zero copy overhead
  - Multiple readers share same physical pages

For content >= 64MB:
  - Streaming read with configurable buffer size (default 4MB)
  - Backpressure-aware: reader controls pace
  - Supports range requests (offset + length)

For content > 1GB:
  - Chunked storage: split into 256MB chunks
  - Each chunk is a separate claim
  - Manifest claim lists chunk claim_ids in order
  - Enables parallel read/write of chunks
```

### 3.2 Write-Ahead Log (WAL)

```
Write-Ahead Log Design
──────────────────────

Purpose:
  All state changes are written to WAL BEFORE applied to primary storage.
  On crash, replay WAL from last checkpoint to recover consistent state.

WAL Entry Format:
  ┌──────────────────────────────────────────────────┐
  │ magic: 0x5645 ("VE")           — 2 bytes         │
  │ version: 1                      — 1 byte          │
  │ entry_type: enum                — 1 byte          │
  │ timestamp: unix_ms              — 8 bytes         │
  │ sequence_no: monotonic          — 8 bytes         │
  │ payload_length: uint32          — 4 bytes         │
  │ payload: bytes                  — variable        │
  │ crc32: checksum                 — 4 bytes         │
  └──────────────────────────────────────────────────┘

Entry Types:
  CONTENT_CREATED    — new claim added to Content Repository
  CONTENT_DELETED    — claim removed from Content Repository
  WORKITEM_CREATED   — new work item detected
  WORKITEM_UPDATED   — work item status change
  STEP_STARTED       — step execution began
  STEP_COMPLETED     — step execution finished
  STEP_FAILED        — step execution failed
  QUEUE_ENQUEUED     — item added to processing queue
  QUEUE_DEQUEUED     — item removed from processing queue
  CHECKPOINT         — consistent snapshot marker

WAL Segments:
  - Each segment file: max 64MB (configurable)
  - Naming: wal-{sequence:06d}.log
  - Segments before last checkpoint can be deleted

Checkpoint Process (every 5 minutes or 10,000 entries):
  1. Flush all in-memory state to PostgreSQL
  2. Write CHECKPOINT entry to WAL
  3. Sync WAL to disk (fsync)
  4. Delete WAL segments before previous checkpoint
  5. Record checkpoint position in checkpoint file

Crash Recovery:
  1. On startup, find latest checkpoint file
  2. Open WAL segment containing checkpoint
  3. Skip to checkpoint position
  4. Replay all entries after checkpoint:
     a. CONTENT_CREATED → verify claim exists on disk
     b. WORKITEM_UPDATED → apply status change to PostgreSQL
     c. STEP_COMPLETED → verify output claim, update step status
     d. Skip entries already reflected in PostgreSQL (idempotent replay)
  5. Any STEP_STARTED without matching STEP_COMPLETED → mark as FAILED
  6. Resume normal operation
```

### 3.3 Swap Files (Queue Overflow)

```
Swap File System
────────────────

Problem:
  In-memory processing queues can grow unbounded during traffic spikes
  or when processing is slower than ingestion.

Solution:
  When queue exceeds memory threshold, transparently swap items to disk.

Configuration:
  queue:
    max_memory_items: 10000          # items held in memory
    max_memory_bytes: 512MB          # memory limit for queue
    swap_directory: /var/hermes/swap
    max_swap_bytes: 10GB             # disk limit for swap
    swap_batch_size: 1000            # items swapped per batch

Swap Trigger:
  if queue.memory_items > max_memory_items * 0.8:  # 80% soft limit
    swap oldest 20% of queue to disk

  if queue.memory_bytes > max_memory_bytes:         # hard limit
    swap until memory_bytes < max_memory_bytes * 0.6

Swap File Format:
  swap/
  ├── swap-{pipeline_id}-{timestamp}-{sequence}.dat
  └── swap-index.db (SQLite)
      Table: swap_entries
      ├── id
      ├── job_id
      ├── pipeline_id
      ├── priority
      ├── swap_file
      ├── offset
      ├── length
      └── swapped_at

Swap-In (when queue has capacity):
  1. Read highest-priority items from swap index
  2. Deserialize from swap file
  3. Add to in-memory queue
  4. Mark swap entries as consumed
  5. Periodically compact swap files (remove consumed entries)

Transparency:
  - Processing logic sees no difference between in-memory and swapped items
  - Queue interface: enqueue(), dequeue(), peek(), depth()
  - Swap is an implementation detail of the queue
```

### 3.4 State Store

```
Persistent State Store
──────────────────────

Purpose:
  Monitors and plugins need to persist state across restarts:
  - File positions (which files have been processed)
  - API cursors (last page/offset fetched)
  - Kafka offsets (consumer group positions)
  - Plugin-specific state (aggregations, windows, counters)

Storage:
  PostgreSQL table: component_state
  ├── component_type    — MONITOR | PLUGIN | PIPELINE
  ├── component_id      — unique identifier
  ├── scope             — CLUSTER | NODE:{worker_id}
  ├── state_key          — application-defined key
  ├── state_value        — JSONB
  ├── version            — optimistic locking version
  ├── updated_at         — last update timestamp
  └── expires_at         — optional TTL

API:
  interface IStateStore:
    get(component_id, key) → value
    put(component_id, key, value) → void
    delete(component_id, key) → void
    list(component_id, prefix) → [(key, value)]
    compare_and_swap(component_id, key, expected, new) → bool

Replication:
  - Cluster-scoped state: stored in PostgreSQL (replicated via PG replication)
  - Node-scoped state: stored locally (SQLite), synced to PostgreSQL async
  - On worker failover: node-scoped state loaded from PostgreSQL backup

Usage Examples:
  - FileWatcher: { "last_position": "/data/equip_a/2026-03-15/", "last_file": "run_042.csv" }
  - APIPoller: { "cursor": "page_token_abc123", "last_poll": "2026-03-15T14:30:00Z" }
  - KafkaConsumer: { "offsets": { "0": 15234, "1": 8921, "2": 12045 } }
  - AggregationPlugin: { "running_sum": 45231.5, "count": 1523 }
```

---

## 4. Back-Pressure System (P0)

### 4.1 Design Overview

```
Back-Pressure Architecture
──────────────────────────

Back-pressure prevents fast producers from overwhelming slow consumers.
Applied at every boundary in the system.

Pressure Points:
  Monitor → Queue → Step 1 → Queue → Step 2 → Queue → Step N
     ↑         ↑        ↑        ↑        ↑        ↑
     BP        BP       BP       BP       BP       BP

Each queue has independently configurable thresholds.
Pressure propagates BACKWARD: if Step 2 is slow, Step 1 queue fills,
which eventually causes Monitor to pause.
```

### 4.2 Queue Depth Monitoring

```
Per-Pipeline Queue Metrics
──────────────────────────

Each pipeline step has an input queue with these metrics:

  queue_depth           — current number of items in queue
  queue_bytes           — current memory usage of queued items
  enqueue_rate          — items/second entering queue (1m average)
  dequeue_rate          — items/second leaving queue (1m average)
  avg_processing_time   — average time per item in this step
  p99_processing_time   — 99th percentile processing time
  estimated_drain_time  — queue_depth * avg_processing_time

Derived metrics:
  pressure_ratio = enqueue_rate / dequeue_rate
    < 1.0  →  consumer keeping up
    1.0-1.5 → marginal (queue slowly growing)
    > 1.5  →  back-pressure needed
```

### 4.3 Threshold Configuration

```yaml
# Pipeline-level back-pressure configuration
backPressure:
  # Per-step queue thresholds
  defaults:
    softLimit:
      maxItems: 1000            # Start slowing down
      maxBytes: 256MB
    hardLimit:
      maxItems: 5000            # Stop accepting new items
      maxBytes: 1GB
    criticalLimit:
      maxItems: 10000           # Emergency: swap to disk
      maxBytes: 2GB

  # Step-specific overrides
  steps:
    collect:
      softLimit:
        maxItems: 500           # Collection step fills fast
    algorithm:
      softLimit:
        maxItems: 2000          # Algorithm step is CPU-heavy, needs bigger buffer

  # Monitor behavior when back-pressure active
  monitorPolicy:
    onSoftLimit: SLOW_DOWN      # Increase poll interval by 2x
    onHardLimit: PAUSE          # Stop monitoring entirely
    onCriticalLimit: PAUSE      # Pause + swap queue to disk
    resumeAt: 0.5               # Resume when queue drops to 50% of soft limit

  # Disk overflow
  diskOverflow:
    enabled: true
    directory: /var/hermes/swap
    maxDiskBytes: 10GB
    triggerAt: hardLimit         # Start swapping at hard limit
```

### 4.4 Pressure Propagation

```
Back-Pressure Propagation Chain
───────────────────────────────

Step 3 (Transfer) slows down
  → Step 3 input queue grows
  → Step 3 queue hits soft limit
  → Step 2 (Algorithm) output throttled (writes slow down)
  → Step 2 takes longer per item (blocked on output write)
  → Step 2 input queue grows
  → Step 2 queue hits soft limit
  → Step 1 (Collect) output throttled
  → Monitor detects back-pressure on Step 1
  → Monitor increases poll interval (or pauses)

When Step 3 catches up:
  → Step 3 queue drops below resume threshold (50% of soft)
  → Step 2 output unblocked
  → Step 2 queue drains
  → Step 1 output unblocked
  → Monitor resumes normal polling

Propagation is automatic and requires no manual intervention.
```

### 4.5 UI Indicators

```
Pipeline Designer — Back-Pressure Visualization
────────────────────────────────────────────────

  ┌───────────┐   ██░░░  ┌───────────┐   ████░  ┌───────────┐
  │ 📥        │   32%    │ 🔬        │   78%    │ 📤        │
  │ Collector │ ───────▶ │ Algorithm │ ───────▶ │ Transfer  │
  │   🟢      │          │   🟡      │          │   🔴      │
  │ 120/s     │          │ 45/s      │          │ 12/s      │
  └───────────┘          └───────────┘          └───────────┘

Legend:
  🟢 GREEN  — queue < 50% of soft limit (healthy)
  🟡 YELLOW — queue between soft limit and hard limit (warning)
  🔴 RED    — queue at or above hard limit (critical)

  Bar: ████░ — visual queue fill level
  Rate: items/second throughput

Tooltip on hover:
  ┌──────────────────────────────┐
  │ Algorithm Step               │
  │ Queue: 1,560 / 2,000 (78%)  │
  │ Memory: 189MB / 256MB       │
  │ Enqueue: 45/s               │
  │ Dequeue: 40/s               │
  │ Avg latency: 22ms           │
  │ Status: SOFT_LIMIT_ACTIVE   │
  │ Drain ETA: 39 seconds       │
  └──────────────────────────────┘
```

---

## 5. Dead Letter Queue (P0)

### 5.1 Architecture

```
Dead Letter Queue Design
────────────────────────

Each pipeline has its own DLQ (configurable destination).

Pipeline "Equipment Monitoring"
├── Normal Flow: Monitor → Collect → Algorithm → Transfer
└── DLQ: hermes_dlq.equipment_monitoring
    ├── Storage: PostgreSQL table + Content Repository
    ├── Retention: 30 days (configurable)
    └── Max size: 10,000 items (configurable)
```

### 5.2 Error Classification

```
Error Classification System
───────────────────────────

TRANSIENT errors (retryable):
  - Network timeout (connection refused, DNS failure)
  - Rate limiting (HTTP 429)
  - Resource exhaustion (disk full, OOM — temporary)
  - Lock contention (database deadlock)
  - Upstream service unavailable (HTTP 502, 503, 504)

PERMANENT errors (not retryable):
  - Validation failure (data doesn't match schema)
  - Authentication failure (invalid credentials)
  - Authorization failure (insufficient permissions)
  - Data corruption (checksum mismatch)
  - Business logic error (invalid state transition)
  - Plugin crash (segfault, unhandled exception)

UNKNOWN errors (classified by heuristic):
  - Default: treat as TRANSIENT for first N attempts
  - If fails N times with same error → reclassify as PERMANENT
  - Operator can manually reclassify via DLQ Explorer

Classification drives routing:
  TRANSIENT → retry with backoff → DLQ after max_retries
  PERMANENT → DLQ immediately (no retry)
  UNKNOWN → retry once → DLQ if fails again
```

### 5.3 DLQ Entry Structure

```
DLQ Entry
─────────

Table: dead_letter_entries
├── id                          — PK, auto-increment
├── pipeline_id                 — source pipeline
├── job_id                — original work item
├── failed_stage_order           — which step failed
├── failed_stage_type            — COLLECT | ALGORITHM | TRANSFER
│
├── error_classification        — TRANSIENT | PERMANENT | UNKNOWN
├── error_code                  — application-specific error code
├── error_message               — human-readable error message
├── error_stacktrace            — full stack trace (truncated to 10KB)
├── error_context               — JSONB: additional error context
│
├── attempt_count               — how many times processing was attempted
├── first_failed_at             — timestamp of first failure
├── last_failed_at              — timestamp of last failure
├── failure_history             — JSONB: array of all failure details
│
├── input_claim_id              — Content Repository claim for input data
├── partial_output_claim_id     — Content Repository claim for any partial output
│
├── recipe_snapshot             — JSONB: recipe config at time of failure
├── pipeline_snapshot           — JSONB: pipeline config at time of failure
├── worker_id                   — which worker last processed this
│
├── replay_status               — NULL | PENDING | REPLAYING | REPLAYED | REPLAY_FAILED
├── replayed_at                 — timestamp of replay
├── replayed_by                 — user who initiated replay
├── replay_job_id         — new work item created by replay
│
├── created_at                  — when entered DLQ
├── expires_at                  — when this entry will be auto-purged
└── tags                        — JSONB: user-assigned tags for filtering
```

### 5.4 DLQ Explorer (Web UI)

```
DLQ Explorer
────────────

┌──────────────────────────────────────────────────────────────────┐
│  Dead Letter Queue: Equipment Monitoring           23 items      │
│──────────────────────────────────────────────────────────────────│
│                                                                  │
│  Filters: [Pipeline ▼] [Error Type ▼] [Step ▼] [Date Range]    │
│           [🔍 Search error messages...]                          │
│                                                                  │
│  ┌─────┬──────────────────┬───────────┬──────────┬────────────┐ │
│  │  ☐  │ Source Key        │ Error     │ Step     │ Failed At  │ │
│  ├─────┼──────────────────┼───────────┼──────────┼────────────┤ │
│  │  ☐  │ equip_a_run_042  │ PERMANENT │ ALGORITH │ 2026-03-15 │ │
│  │     │ "Schema mismatch: │           │          │ 14:32:10   │ │
│  │     │  expected int..."  │           │          │            │ │
│  ├─────┼──────────────────┼───────────┼──────────┼────────────┤ │
│  │  ☐  │ equip_b_run_108  │ TRANSIENT │ TRANSFER │ 2026-03-15 │ │
│  │     │ "Connection refu- │           │          │ 14:28:45   │ │
│  │     │  sed: S3 endpoint" │           │          │            │ │
│  ├─────┼──────────────────┼───────────┼──────────┼────────────┤ │
│  │  ☐  │ equip_c_run_015  │ PERMANENT │ COLLECT  │ 2026-03-15 │ │
│  │     │ "File not found:  │           │          │ 14:15:22   │ │
│  │     │  /data/equip_c/..." │          │          │            │ │
│  └─────┴──────────────────┴───────────┴──────────┴────────────┘ │
│                                                                  │
│  Selected: 0 items                                               │
│  [Replay Selected] [Replay All TRANSIENT] [Delete Selected]     │
│  [Export CSV] [Bulk Tag]                                         │
└──────────────────────────────────────────────────────────────────┘

DLQ Entry Detail View
─────────────────────

┌──────────────────────────────────────────────────────────────────┐
│  DLQ Entry: equip_a_run_042                                      │
│──────────────────────────────────────────────────────────────────│
│                                                                  │
│  Error: Schema mismatch — expected integer for field "sensor_id" │
│         but received string "SENSOR_A_001"                       │
│                                                                  │
│  Classification: PERMANENT                                       │
│  Failed Step: ALGORITHM (step 2)                                 │
│  Attempts: 3                                                     │
│  First Failed: 2026-03-15 14:30:10                              │
│  Last Failed: 2026-03-15 14:32:10                               │
│                                                                  │
│  Tabs: [Error Detail] [Input Data] [Recipe Snapshot] [History]  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │  Stack Trace:                                             │   │
│  │  hermes.plugins.anomaly_zscore.execute() line 142         │   │
│  │    → int(row["sensor_id"])                                │   │
│  │  ValueError: invalid literal for int(): 'SENSOR_A_001'   │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  Recipe at failure:                                              │
│  { "threshold": 3.5, "targetColumn": "pressure" }              │
│                                                                  │
│  Actions:                                                        │
│  [Replay with Current Recipe]                                    │
│  [Replay with Modified Recipe...]                                │
│  [View Original Job]                                        │
│  [Delete from DLQ]                                               │
└──────────────────────────────────────────────────────────────────┘
```

### 5.5 DLQ Replay

```
Replay from DLQ
───────────────

1. Operator selects DLQ entries to replay
2. Operator chooses:
   a. Replay with ORIGINAL recipe (re-execute as-is)
   b. Replay with CURRENT recipe (use latest version)
   c. Replay with MODIFIED recipe (edit before replay)
3. System creates new Job with:
   - trigger_type: DLQ_REPLAY
   - Input data loaded from Content Repository (original claim_id)
   - start_from_step: failed step (skip already-succeeded steps)
4. New Job enters normal processing queue
5. DLQ entry updated: replay_status = REPLAYING
6. On success: replay_status = REPLAYED
7. On failure: replay_status = REPLAY_FAILED (item stays in DLQ)

Bulk Replay:
  - Select all TRANSIENT errors → replay with backoff
  - Select by date range → replay after system recovery
  - Select by error code → replay after bug fix deployed
```

### 5.6 DLQ Alerting

```yaml
# DLQ alerting configuration
dlq:
  alerting:
    # Alert when DLQ receives new items
    onNewEntry:
      channels: [email, slack, webhook]
      batchWindow: 5m          # Batch alerts within 5-minute windows
      minSeverity: PERMANENT   # Only alert on permanent errors

    # Alert when DLQ size exceeds threshold
    onSizeThreshold:
      warnAt: 100              # items
      criticalAt: 500          # items
      channels: [pagerduty]

    # Alert on DLQ growth rate
    onGrowthRate:
      threshold: 50            # items per hour
      channels: [slack]

    # Daily DLQ summary
    dailySummary:
      time: "09:00"
      timezone: "Asia/Seoul"
      channels: [email]
      includeStats: true       # total, by pipeline, by error type
```

---

## 6. Schema Registry & Evolution (P0)

### 6.1 Schema Discovery Protocol

```
Schema Discovery
────────────────

Plugins report their schemas during registration:

1. Plugin manifest (hermes-plugin.json) includes:
   - inputSchema: what the plugin accepts
   - outputSchema: what the plugin produces
   - configSchema: what configuration it needs

2. Runtime schema discovery:
   - Plugin receives DISCOVER command
   - Plugin inspects data source and returns actual schema
   - Example: CSV collector reads header row → returns column schema

3. Schema inference:
   - On first execution, capture actual output structure
   - Compare with declared outputSchema
   - Store inferred schema if no declared schema exists

Protocol:
  Hermes → Plugin: { "type": "DISCOVER", "context": { "source": "..." } }
  Plugin → Hermes: { "type": "SCHEMA", "schema": { "type": "object", ... } }
```

### 6.2 Central Schema Registry

```
Schema Registry (PostgreSQL)
────────────────────────────

Table: schema_registry
├── id                      — PK
├── subject                  — "{pipeline_id}.{stage_order}.{direction}"
│                              e.g., "pipeline-123.2.output"
├── version                  — monotonic version number
├── schema_json              — JSON Schema document (JSONB)
├── schema_hash              — SHA-256 of canonical schema
├── compatibility            — BACKWARD | FORWARD | FULL | NONE
├── source                   — DECLARED | INFERRED | MANUAL
├── created_at               — timestamp
├── created_by               — user or system
└── is_active                — soft delete flag

Table: schema_compatibility_checks
├── id                      — PK
├── subject                  — schema subject
├── from_version             — old schema version
├── to_version               — new schema version
├── result                   — COMPATIBLE | INCOMPATIBLE
├── breaking_changes         — JSONB: list of breaking changes
├── checked_at               — timestamp
└── auto_resolved            — boolean
```

### 6.3 Schema Versioning & Compatibility

```
Compatibility Modes
───────────────────

BACKWARD (default):
  New schema can read data written with old schema.
  Rule: new fields must have defaults, removed fields OK.
  Use case: consumer upgrades before producer.

FORWARD:
  Old schema can read data written with new schema.
  Rule: old fields preserved, new fields ignored by old consumers.
  Use case: producer upgrades before consumer.

FULL:
  Both backward and forward compatible.
  Rule: only additive changes with defaults allowed.
  Use case: gradual rollout, mixed versions.

NONE:
  No compatibility checking. Any change allowed.
  Use case: development/testing.

Compatibility Check Algorithm:
  1. Parse old and new JSON Schemas
  2. Compare properties:
     a. Removed required field → BREAKING (backward incompatible)
     b. Added required field without default → BREAKING (forward incompatible)
     c. Changed field type → BREAKING (both)
     d. Narrowed enum values → BREAKING (backward)
     e. Widened enum values → OK (backward), BREAKING (forward)
     f. Added optional field with default → OK (both)
  3. Return compatibility result + list of changes
```

### 6.4 Schema Drift Detection

```
Schema Drift Detection
──────────────────────

Runs automatically on every Job execution:

1. After each step execution, compare actual output against registered schema
2. Drift categories:
   a. NEW_FIELD      — output has field not in schema
   b. MISSING_FIELD  — schema has field not in output
   c. TYPE_CHANGE    — field type differs from schema
   d. VALUE_ANOMALY  — field value outside expected range/enum

3. Drift response based on policy:

   AUTO_PROPAGATE:
     - New schema version auto-created from actual output
     - Compatibility check runs against previous version
     - If compatible → new version activated silently
     - If incompatible → alert sent, manual review required
     - Best for: development, exploratory pipelines

   PAUSE_ON_CHANGE:
     - Pipeline pauses on any schema drift
     - Alert sent to operators
     - Operator reviews and approves/rejects new schema
     - Pipeline resumes after approval
     - Best for: production pipelines with strict contracts

   IGNORE:
     - Drift detected and logged but no action taken
     - Metrics updated (drift_count counter)
     - Best for: unstructured data, legacy pipelines

4. Drift alerting:
   - Immediate alert on first drift detection
   - Aggregate alert if drift persists (hourly summary)
   - Dashboard widget showing schema health per pipeline
```

### 6.5 Schema Validation Between Steps

```
Inter-Step Schema Validation
────────────────────────────

Pipeline: Step 1 (output: Schema A) → Step 2 (input: Schema B)

Validation at pipeline creation/modification:
  1. Load Step 1 outputSchema and Step 2 inputSchema
  2. Check that Step 1 output satisfies Step 2 input requirements
  3. Report mismatches:
     - Missing required fields
     - Type incompatibilities
     - Format mismatches (e.g., date format)
  4. Show validation results in Pipeline Designer UI

Runtime validation (optional, per-pipeline config):
  validate_between_steps: true | false (default: false for performance)
  If enabled:
    - After Step N completes, validate output against Step N+1 input schema
    - On validation failure: route to DLQ with error_code: SCHEMA_VALIDATION
```

---

## 7. Streaming & Large File Handling (P1)

### 7.1 Content Repository Integration

```
Large Data Flow with Content Repository
────────────────────────────────────────

V1 (in-memory):
  Step 1 output → JSON in memory → Step 2 input
  Problem: 500MB CSV causes OOM

V2 (Content Repository):
  Step 1 writes output → Content Repository → returns claim_id
  Step 2 receives claim_id → streams from Content Repository

Job between steps carries:
  {
    "contentRef": {
      "claim_id": "sha256:aabb1234...",
      "size": 524288000,
      "mime_type": "text/csv",
      "record_count": 5000000
    },
    "metadata": {
      "source": "file",
      "columns": ["timestamp", "value", "status"],
      "format": "csv"
    }
  }

Benefits:
  - Constant memory usage regardless of data size
  - Multiple steps can reference same content (dedup)
  - Content persists across restarts (crash recovery)
  - Content can be inspected via Job Explorer
```

### 7.2 gRPC Plugin Protocol (V2)

```
gRPC Plugin Protocol
────────────────────

V1 plugin protocol: JSON over stdin/stdout (simple but limited)
V2 adds: gRPC bidirectional streaming (for high-performance plugins)

service HermesPlugin {
  // Configuration and lifecycle
  rpc Configure(ConfigureRequest) returns (ConfigureResponse);
  rpc Discover(DiscoverRequest) returns (DiscoverResponse);

  // Execution with streaming
  rpc Execute(stream ExecuteRequest) returns (stream ExecuteResponse);

  // Health
  rpc HealthCheck(Empty) returns (HealthResponse);
}

message ExecuteRequest {
  oneof payload {
    ExecuteStart start = 1;       // Initial config + metadata
    DataChunk chunk = 2;          // Streamed input data chunk
    ExecuteEnd end = 3;           // Signal end of input
  }
}

message ExecuteResponse {
  oneof payload {
    StatusUpdate status = 1;      // Progress updates
    DataChunk chunk = 2;          // Streamed output data chunk
    LogEntry log = 3;             // Log messages
    ExecuteResult result = 4;     // Final result summary
    ErrorDetail error = 5;        // Error information
  }
}

message DataChunk {
  bytes data = 1;                 // Raw data bytes
  int64 sequence = 2;            // Chunk sequence number
  string content_type = 3;       // MIME type
  bool is_last = 4;              // Last chunk flag
}

Benefits over stdin/stdout:
  - Bidirectional streaming (input and output simultaneously)
  - Binary data without Base64 overhead
  - Multiplexed connections (multiple concurrent executions)
  - Built-in flow control (gRPC backpressure)
  - Language-agnostic (gRPC codegen for all major languages)
  - Health checking and graceful shutdown

Plugin can be:
  - Long-lived process (gRPC server, reused across executions)
  - Short-lived process (started per execution, stdin/stdout protocol)
  - Container (Docker, with gRPC or stdin/stdout)
```

### 7.3 Chunked Transfer

```
Chunked Transfer Protocol
─────────────────────────

For data > chunk_threshold (default 1MB):

1. SENDER (step output or Content Repository read):
   a. Open content stream
   b. Read chunk_size bytes (default 4MB)
   c. Send DataChunk { data, sequence=0, is_last=false }
   d. Wait for receiver ACK (backpressure)
   e. Repeat until EOF
   f. Send DataChunk { data, sequence=N, is_last=true }

2. RECEIVER (next step input or Content Repository write):
   a. Receive DataChunk
   b. Write to local buffer or tmp file
   c. Send ACK (ready for next chunk)
   d. On is_last=true: finalize content

3. FLOW CONTROL:
   - gRPC: built-in window-based flow control
   - stdin/stdout: explicit ACK messages
   - HTTP: chunked transfer encoding

4. ERROR HANDLING:
   - Sender crash mid-transfer → receiver discards partial content
   - Receiver crash → sender detects broken pipe, aborts
   - Network error → retry from last ACK'd chunk (if idempotent)
```

### 7.4 Memory-Mapped File I/O

```
Memory-Mapped I/O for Content Repository
─────────────────────────────────────────

For random-access reads of Content Repository claims:

Small files (< 64MB):
  - mmap entire file
  - Direct pointer access, zero-copy
  - OS manages page faults transparently

Medium files (64MB - 1GB):
  - mmap with sliding window (64MB window)
  - Window repositioned on access pattern

Large files (> 1GB):
  - Chunked storage (256MB chunks)
  - mmap individual chunks on demand
  - LRU eviction of mapped chunks

Configuration:
  content_repository:
    mmap:
      enabled: true
      small_file_threshold: 64MB
      window_size: 64MB
      max_mapped_bytes: 2GB      # Total mmap budget
      eviction_policy: LRU
```

---

## 8. Exactly-Once Processing (P1)

### 8.1 Checkpointing

```
Per-Step Output Checkpointing
─────────────────────────────

After each step completes successfully:
1. Write output to Content Repository → get claim_id
2. Record checkpoint in PostgreSQL (single transaction):
   INSERT INTO step_checkpoints (
     job_id, execution_id, stage_order,
     output_claim_id, status, completed_at
   )
3. Update job_step_execution status

On restart after crash:
1. Query: SELECT * FROM step_checkpoints
   WHERE execution_id = {last_execution}
   ORDER BY stage_order DESC LIMIT 1
2. Resume from step AFTER last checkpoint
3. Input for resumed step = output_claim_id from checkpoint

This guarantees:
  - No step is executed twice with the same input
  - Partial progress is preserved across crashes
  - Reprocessing starts from the exact failure point
```

### 8.2 Transactional State Updates

```
Transactional State Updates
───────────────────────────

All state changes within a step execution are wrapped in a single
PostgreSQL transaction:

BEGIN;
  -- 1. Update step execution status
  UPDATE job_step_executions
  SET status = 'COMPLETED', output_summary = {...}
  WHERE id = {step_exec_id};

  -- 2. Record checkpoint
  INSERT INTO step_checkpoints (...)
  VALUES (...);

  -- 3. Update work item status
  UPDATE jobs
  SET status = 'PROCESSING', current_step = {next_step}
  WHERE id = {job_id};

  -- 4. Update component state (if any)
  UPDATE component_state
  SET state_value = {...}, version = version + 1
  WHERE component_id = {id} AND version = {expected_version};

  -- 5. Write event log
  INSERT INTO execution_event_logs (...)
  VALUES (...);
COMMIT;

If any step fails → entire transaction rolls back → no partial state.
```

### 8.3 Idempotency Keys

```
Idempotency for Transfer Steps
──────────────────────────────

Transfer steps (writes to external systems) use idempotency keys
to prevent duplicate writes on retry:

Idempotency Key Format:
  {pipeline_id}:{job_id}:{execution_id}:{stage_order}

Usage:
  1. Before executing transfer step, check:
     SELECT * FROM idempotency_log
     WHERE idempotency_key = {key}
  2. If exists → skip execution, return cached result
  3. If not exists → execute transfer
  4. After success:
     INSERT INTO idempotency_log (
       idempotency_key, result_json, created_at, expires_at
     )
  5. Idempotency log entries expire after 7 days (configurable)

External system integration:
  - S3: use idempotency key as object metadata
  - HTTP API: send as X-Idempotency-Key header
  - Database: use as unique constraint on write
  - Kafka: use as message key + enable idempotent producer
```

### 8.4 Orphan Recovery

```
Orphaned Item Recovery on Startup
─────────────────────────────────

On coordinator/worker startup:

1. Scan for orphaned PROCESSING items:
   SELECT * FROM jobs
   WHERE status = 'PROCESSING'
   AND assigned_worker_id = {this_worker}  -- or any dead worker

2. For each orphaned item:
   a. Check step_checkpoints for last completed step
   b. If checkpoint exists:
      - Resume from next step
      - Create new execution with trigger_type = RECOVERY
   c. If no checkpoint:
      - Reset status to QUEUED
      - Increment retry_count
      - Re-enter assignment queue

3. Scan for orphaned executions:
   SELECT * FROM job_executions
   WHERE status = 'RUNNING'
   AND started_at < now() - interval '1 hour'  -- configurable timeout

4. For each orphaned execution:
   - Mark as FAILED with error_code = ORPHANED
   - Check if work item should be retried or sent to DLQ
```

### 8.5 Fencing Tokens

```
Fencing Tokens for Zombie Prevention
─────────────────────────────────────

Problem:
  Worker A starts processing item X, then experiences a long GC pause.
  Coordinator assumes A is dead, reassigns item X to Worker B.
  Worker A wakes up and tries to complete item X.
  Now both A and B think they own item X.

Solution: Fencing tokens

1. When coordinator assigns item to worker:
   fencing_token = atomic_increment(global_fencing_counter)
   UPDATE jobs SET
     assigned_worker_id = {worker},
     fencing_token = {fencing_token}
   WHERE id = {item_id}

2. Worker includes fencing_token in all state updates:
   UPDATE jobs SET status = 'COMPLETED'
   WHERE id = {item_id}
   AND fencing_token = {my_fencing_token}

3. If worker has stale token (item was reassigned):
   UPDATE affects 0 rows → worker knows it's been fenced out
   Worker discards its result and stops processing

4. External systems:
   Pass fencing_token as metadata in transfer steps
   External system can optionally validate token monotonicity
```

---

## 9. Observability (P1)

### 9.1 Prometheus Metrics

```
Prometheus Metrics Endpoint: GET /metrics
──────────────────────────────────────────

# Counters
hermes_jobs_total{pipeline, status}                    — total work items by status
hermes_job_executions_total{pipeline, trigger_type}    — total executions
hermes_step_executions_total{pipeline, stage_type, status}    — step execution count
hermes_dlq_entries_total{pipeline, error_class}              — DLQ entries
hermes_content_claims_total{operation}                       — content repo operations (write/read/delete)
hermes_plugin_invocations_total{plugin, status}              — plugin calls
hermes_schema_drift_total{pipeline, step, drift_type}        — schema drift events

# Histograms
hermes_job_duration_seconds{pipeline, stage_type}       — processing duration
hermes_plugin_execution_seconds{plugin}                      — plugin execution time
hermes_content_write_seconds{size_bucket}                    — content repo write latency
hermes_content_read_seconds{size_bucket}                     — content repo read latency
hermes_api_request_seconds{method, path, status}             — API response time

# Gauges
hermes_pipeline_queue_depth{pipeline, step}                  — current queue depth
hermes_pipeline_queue_bytes{pipeline, step}                  — current queue memory
hermes_pipeline_backpressure_active{pipeline, step}          — 1 if backpressure active
hermes_active_pipelines                                      — number of active pipelines
hermes_active_workers                                        — number of healthy workers
hermes_content_repository_bytes                              — total content repo size
hermes_content_repository_claims                             — total claim count
hermes_swap_file_bytes                                       — total swap file size
hermes_cluster_node_count{role}                              — nodes by role

# Summary
hermes_job_age_seconds{pipeline}                       — time since detection
```

### 9.2 OpenTelemetry Tracing

```
Distributed Tracing with OpenTelemetry
──────────────────────────────────────

Trace hierarchy:
  Trace: Job #1002 processing
  ├── Span: Pipeline "Equipment Monitoring" execution
  │   ├── Span: Step 1 — COLLECT (FileCollector)
  │   │   ├── Span: File discovery (/data/equip_a/*.csv)
  │   │   ├── Span: File read (run_042.csv, 1.2MB)
  │   │   └── Span: Content Repository write (claim aabb1234)
  │   │
  │   ├── Span: Step 2 — ALGORITHM (AnomalyDetector)
  │   │   ├── Span: Plugin execution (gRPC call)
  │   │   │   ├── Span: Data load from Content Repository
  │   │   │   ├── Span: Z-Score computation
  │   │   │   └── Span: Result serialization
  │   │   └── Span: Content Repository write (output claim)
  │   │
  │   └── Span: Step 3 — TRANSFER (S3Upload)
  │       ├── Span: Content Repository read (output claim)
  │       └── Span: S3 PutObject (external call)
  │
  └── Span attributes:
      job.id = 1002
      job.source_key = "equip_a_run_042"
      pipeline.id = "equipment-monitoring"
      pipeline.name = "Equipment Monitoring"
      worker.id = "worker-03"

Configuration:
  opentelemetry:
    enabled: true
    exporter: otlp                    # otlp | jaeger | zipkin
    endpoint: http://otel-collector:4317
    sample_rate: 1.0                  # 1.0 = trace everything
    propagation: w3c                  # w3c | b3 | jaeger
    resource_attributes:
      service.name: hermes
      service.version: 2.0.0
      deployment.environment: production
```

### 9.3 Structured Logging

```
Structured Logging (Serilog-compatible format)
──────────────────────────────────────────────

Log Format (JSON):
{
  "timestamp": "2026-03-15T14:32:10.123Z",
  "level": "Information",
  "message": "Step completed: ALGORITHM in 2.1s",
  "properties": {
    "pipeline_id": "equipment-monitoring",
    "pipeline_name": "Equipment Monitoring",
    "job_id": 1002,
    "execution_id": 4521,
    "stage_order": 2,
    "stage_type": "ALGORITHM",
    "duration_ms": 2100,
    "worker_id": "worker-03",
    "trace_id": "abc123def456",
    "span_id": "789ghi"
  }
}

Sinks (configurable):
  - Console (development)
  - File (with rotation: 100MB per file, 7 days retention)
  - Seq (structured log server)
  - Elasticsearch (ELK stack)
  - Loki (Grafana stack)
  - Splunk (enterprise)

Log Levels:
  Verbose  — internal framework details
  Debug    — plugin communication, content repo operations
  Information — step start/complete, pipeline lifecycle
  Warning  — back-pressure active, retry triggered, schema drift
  Error    — step failure, plugin crash, DLQ routing
  Fatal    — unrecoverable error, process shutdown
```

### 9.4 Health Check Endpoints

```
Health Check Endpoints (Kubernetes-ready)
─────────────────────────────────────────

GET /health/live
  → 200 OK if process is running
  → Used by Kubernetes livenessProbe
  → Response: { "status": "alive" }

GET /health/ready
  → 200 OK if ready to accept requests
  → Checks: PostgreSQL connection, Content Repository accessible
  → Used by Kubernetes readinessProbe
  → Response: {
      "status": "ready",
      "checks": {
        "postgresql": "ok",
        "content_repository": "ok",
        "worker_connection": "ok"
      }
    }

GET /health/startup
  → 200 OK when initial startup complete
  → Checks: migrations applied, plugins loaded, coordinator elected
  → Used by Kubernetes startupProbe
  → Response: {
      "status": "started",
      "startup_time_ms": 3200,
      "plugins_loaded": 12
    }

GET /health/detailed
  → Full system health report
  → Response: {
      "cluster": {
        "coordinator": "worker-01",
        "workers": 3,
        "healthy_workers": 3
      },
      "pipelines": {
        "active": 5,
        "paused": 1,
        "error": 0
      },
      "queues": {
        "total_depth": 234,
        "backpressure_active": 1
      },
      "content_repository": {
        "claims": 15234,
        "size_bytes": 8589934592,
        "disk_free_bytes": 107374182400
      },
      "dlq": {
        "total_entries": 23,
        "oldest_entry": "2026-03-14T10:00:00Z"
      }
    }
```

### 9.5 Bulletin Board / Notification Center

```
Bulletin Board (UI Component)
─────────────────────────────

Central notification hub in the Web UI, inspired by NiFi's bulletin board.

┌──────────────────────────────────────────────────────────────────┐
│  Notifications                                    [Mark All Read]│
│──────────────────────────────────────────────────────────────────│
│                                                                  │
│  🔴 14:32  Pipeline "Equipment Monitoring"                       │
│     DLQ: 5 new items in last hour (threshold: 3)                │
│     [View DLQ] [Acknowledge]                                     │
│                                                                  │
│  🟡 14:28  Pipeline "ERP Sync"                                   │
│     Schema drift detected: new field "discount_code" in output  │
│     Policy: PAUSE_ON_CHANGE — pipeline paused                    │
│     [Review Schema] [Approve] [Reject]                           │
│                                                                  │
│  🟡 14:15  Worker "worker-03"                                    │
│     High memory usage: 87% (threshold: 80%)                     │
│     [View Worker] [Acknowledge]                                  │
│                                                                  │
│  🟢 14:00  System                                                │
│     Daily DLQ summary: 3 entries resolved, 2 pending            │
│     [View Summary]                                               │
│                                                                  │
│  Filter: [All ▼] [Pipeline ▼] [Severity ▼]   [Auto-refresh ✓] │
└──────────────────────────────────────────────────────────────────┘

Bulletin Storage:
  Table: bulletins
  ├── id, severity, category, pipeline_id, worker_id
  ├── title, message, action_url
  ├── created_at, acknowledged_at, acknowledged_by
  └── expires_at (auto-dismiss after TTL)
```

### 9.6 Alerting Rules

```yaml
# Alerting configuration (per pipeline or global)
alerting:
  rules:
    - name: "High failure rate"
      condition: "rate(hermes_step_executions_total{status='FAILED'}[5m]) > 0.1"
      severity: critical
      channels: [pagerduty, slack]
      cooldown: 15m

    - name: "Queue buildup"
      condition: "hermes_pipeline_queue_depth > 5000"
      severity: warning
      channels: [slack]
      cooldown: 30m

    - name: "Worker down"
      condition: "hermes_active_workers < hermes_expected_workers"
      severity: critical
      channels: [pagerduty]
      cooldown: 5m

    - name: "Content repository disk usage"
      condition: "hermes_content_repository_bytes / node_filesystem_size_bytes > 0.85"
      severity: warning
      channels: [email]
      cooldown: 1h

  channels:
    slack:
      webhook_url: "${SLACK_WEBHOOK_URL}"
      channel: "#hermes-alerts"
    pagerduty:
      routing_key: "${PAGERDUTY_KEY}"
    email:
      smtp_host: "smtp.example.com"
      recipients: ["ops@example.com"]
```

### 9.7 Grafana Dashboard Templates

```
Pre-built Grafana Dashboards
─────────────────────────────

Dashboard 1: Cluster Overview
  - Active workers (gauge)
  - Total throughput (items/sec graph)
  - Pipeline health matrix (table: pipeline x status)
  - Content Repository usage (pie chart)
  - DLQ entry rate (graph)

Dashboard 2: Pipeline Detail
  - Per-step throughput (stacked bar)
  - Per-step latency (heatmap)
  - Queue depth over time (line graph)
  - Back-pressure events (annotations)
  - Error rate by step (line graph)
  - Schema drift events (annotations)

Dashboard 3: Worker Health
  - CPU/Memory/Disk per worker (multi-line)
  - Items processed per worker (bar)
  - Queue depth per worker (gauge)
  - Heartbeat latency (line)

Dashboard 4: Content Repository
  - Storage growth over time (area graph)
  - Read/write IOPS (line)
  - Claim count and dedup ratio (stat panels)
  - GC frequency and duration (bar)

Shipped as JSON files in:
  hermes/deployment/grafana/dashboards/
```

---

## 10. Retry & Resilience (P1)

### 10.1 Retry Policy

```
Retry Policy Configuration
──────────────────────────

Per-step or per-pipeline retry configuration:

retryPolicy:
  maxAttempts: 5                    # Maximum retry attempts
  initialInterval: 1s              # First retry delay
  backoffCoefficient: 2.0          # Exponential backoff multiplier
  maxInterval: 60s                 # Maximum delay between retries
  jitter: true                     # Add random jitter (0-25% of interval)
  retryableErrors:                 # Only retry these error classifications
    - TRANSIENT
    - UNKNOWN
  nonRetryableErrors:              # Never retry these
    - PERMANENT

Retry Schedule Example (maxAttempts=5, initial=1s, coefficient=2.0):
  Attempt 1: immediate
  Attempt 2: 1s  (+/- jitter)
  Attempt 3: 2s  (+/- jitter)
  Attempt 4: 4s  (+/- jitter)
  Attempt 5: 8s  (+/- jitter)
  → After attempt 5: route to DLQ

Implementation:
  Using Polly (.NET) or tenacity (Python):
  - Retry with exponential backoff
  - Configurable per step
  - Retry count tracked in step_execution.retry_attempt
  - Each retry logged in ExecutionEventLog
```

### 10.2 Circuit Breaker

```
Circuit Breaker Pattern (Per External Endpoint)
────────────────────────────────────────────────

States:
  CLOSED (normal operation)
    → Track failure rate over sliding window (default: 10 requests)
    → If failure_rate > threshold (default: 50%) → transition to OPEN

  OPEN (failing, reject all requests)
    → All requests immediately fail with CircuitOpenError
    → After break_duration (default: 30s) → transition to HALF_OPEN

  HALF_OPEN (testing recovery)
    → Allow 1 probe request through
    → If probe succeeds → transition to CLOSED
    → If probe fails → transition to OPEN (reset break timer)

Configuration:
  circuitBreaker:
    failureThreshold: 0.5          # 50% failure rate triggers open
    samplingWindow: 10             # requests in sliding window
    breakDuration: 30s             # time in OPEN state
    halfOpenMaxProbes: 3           # probes before full close

Per-Endpoint Circuit Breakers:
  - Each external URL/host gets its own circuit breaker
  - Pipeline step with S3 transfer → circuit breaker for S3 endpoint
  - Pipeline step with REST API → circuit breaker for API host
  - Circuit breaker state visible in UI (step node shows state)

Integration with Retry:
  retry attempts → circuit breaker → actual call
  If circuit is OPEN, retry doesn't even attempt the call
  (avoids wasting retry budget on known-down endpoints)
```

### 10.3 Bulkhead Pattern

```
Bulkhead Isolation
──────────────────

Purpose: Prevent one pipeline's failure from cascading to others.

Implementation:
  1. Thread/Task Pool Isolation:
     - Each pipeline gets its own task pool
     - maxConcurrency per pipeline (default: 10)
     - Pipeline A exhausting its pool doesn't starve Pipeline B

  2. Memory Isolation:
     - Per-pipeline memory budget
     - Back-pressure triggered independently per pipeline
     - OOM in pipeline A doesn't crash the worker process

  3. Connection Pool Isolation:
     - Each external endpoint gets its own connection pool
     - Pipeline A's slow database doesn't exhaust connections for Pipeline B

Configuration:
  bulkhead:
    maxConcurrency: 10              # max parallel items per pipeline
    maxQueueDepth: 100              # max queued items per pipeline
    timeout: 300s                   # max time per item execution
```

### 10.4 Timeout Policies

```
Timeout Configuration
─────────────────────

Per-Step Timeout:
  - Each step has a configurable timeout (default: 300s)
  - On timeout: step marked as FAILED with error_code = TIMEOUT
  - Timeout triggers retry (if retryable) or DLQ routing

Per-Pipeline Timeout:
  - Total execution time for all steps (default: 3600s)
  - On timeout: cancel remaining steps, mark as FAILED

Per-Plugin Timeout:
  - Plugin process/container timeout (default: 600s)
  - On timeout: kill plugin process, mark step as FAILED

Timeout Configuration:
  timeouts:
    step:
      default: 300s
      collect: 120s               # Collection steps should be fast
      algorithm: 600s             # Algorithm steps may be slow
      transfer: 180s              # Transfer should be fast
    pipeline: 3600s               # 1 hour total
    plugin: 600s                  # 10 minutes per plugin invocation
    healthCheck: 10s              # Health check timeout
```

### 10.5 Fallback Strategies

```
Fallback Strategy Configuration
───────────────────────────────

Per-Step Fallback:
  - Define what happens when a step fails after all retries

Fallback Options:
  NONE          — no fallback, route to DLQ (default)
  SKIP          — skip this step, pass previous output to next step
  DEFAULT_VALUE — use a configured default output
  ALTERNATIVE   — use an alternative plugin/endpoint
  CACHE         — use cached output from last successful execution

Configuration:
  steps:
    - stepOrder: 2
      stageType: ALGORITHM
      fallback:
        strategy: ALTERNATIVE
        alternativeRef: "simple-threshold-check"  # simpler algorithm
        config:
          threshold: 100
          mode: "basic"

    - stepOrder: 3
      stageType: TRANSFER
      fallback:
        strategy: ALTERNATIVE
        alternativeRef: "local-file-output"  # write to local disk if S3 fails
        config:
          path: "/var/hermes/fallback/{pipeline_id}/{job_id}.json"
```

---

## 11. Security (P2)

### 11.1 Authentication

```
Authentication: JWT/OIDC (Pluggable)
─────────────────────────────────────

Supported Providers:
  - Built-in (local users in PostgreSQL — development/small teams)
  - OIDC (Keycloak, Auth0, Azure AD, Okta)
  - LDAP/Active Directory
  - API Keys (for service-to-service)

JWT Flow:
  1. User authenticates via OIDC provider → receives JWT
  2. JWT included as Authorization: Bearer {token} on API requests
  3. Hermes validates JWT signature and claims
  4. User identity extracted: sub, email, roles, groups

Configuration:
  auth:
    enabled: true                    # false = open access (dev mode)
    provider: oidc                   # builtin | oidc | ldap | apikey
    oidc:
      issuer: https://auth.example.com
      clientId: hermes-app
      clientSecret: ${OIDC_CLIENT_SECRET}
      scopes: [openid, profile, email]
      audienceValidation: true
    session:
      tokenExpiry: 1h
      refreshTokenExpiry: 24h

API Key Authentication (for programmatic access):
  Table: api_keys
  ├── id, key_hash (bcrypt), name, description
  ├── scopes (JSONB), created_by, created_at
  ├── last_used_at, expires_at, is_active
  └── rate_limit_rpm (requests per minute)
```

### 11.2 RBAC

```
Role-Based Access Control
─────────────────────────

Built-in Roles:
  VIEWER
    - Read all pipelines, recipes, work items
    - View dashboards and metrics
    - View DLQ entries
    - Cannot modify anything

  OPERATOR
    - Everything VIEWER can do
    - Edit recipes (create new versions)
    - Activate/deactivate pipelines
    - Reprocess work items
    - Replay DLQ entries
    - Acknowledge bulletins

  ADMIN
    - Everything OPERATOR can do
    - Create/delete pipelines
    - Manage plugin definitions
    - Manage users and roles
    - View audit log
    - Configure alerting
    - Manage schema registry

  SUPERADMIN
    - Everything ADMIN can do
    - System configuration
    - Cluster management
    - Workspace management (multi-tenancy)
    - API key management

Resource-Level Permissions (optional):
  - Per-pipeline access control
  - Per-workspace isolation
  - Custom roles with fine-grained permissions

Table: user_roles
├── user_id, role, scope (GLOBAL | WORKSPACE:{id} | PIPELINE:{id})
├── granted_by, granted_at
└── expires_at (optional)
```

### 11.3 Audit Log

```
Audit Log
─────────

Every user action recorded for compliance:

Table: audit_log
├── id                  — PK
├── timestamp           — when
├── user_id             — who
├── user_email          — who (denormalized for search)
├── source_ip           — from where
├── action              — what (enum)
├── resource_type       — pipeline | recipe | job | user | system
├── resource_id         — which resource
├── detail              — JSONB: action-specific details
├── old_value           — JSONB: previous state (for modifications)
├── new_value           — JSONB: new state (for modifications)
└── session_id          — correlate actions in same session

Audited Actions:
  AUTH_LOGIN, AUTH_LOGOUT, AUTH_FAILED
  PIPELINE_CREATED, PIPELINE_MODIFIED, PIPELINE_DELETED
  PIPELINE_ACTIVATED, PIPELINE_DEACTIVATED
  RECIPE_CREATED, RECIPE_PUBLISHED, RECIPE_REVERTED
  WORKITEM_REPROCESSED, WORKITEM_BULK_REPROCESSED
  DLQ_REPLAYED, DLQ_DELETED, DLQ_BULK_REPLAYED
  SCHEMA_APPROVED, SCHEMA_REJECTED
  USER_CREATED, USER_ROLE_CHANGED, USER_DELETED
  APIKEY_CREATED, APIKEY_REVOKED
  SYSTEM_CONFIG_CHANGED

Retention:
  - Default: 2 years
  - Configurable per compliance requirement
  - Export to external SIEM (Splunk, ELK, etc.)
```

### 11.4 Secrets Management

```
Secrets Management
──────────────────

Secret Sources (pluggable):
  1. Environment Variables (default, simplest)
     SECRET_DB_PASSWORD=xxx → referenced as ${DB_PASSWORD}

  2. Azure Key Vault
     secrets:
       provider: azure-keyvault
       vaultUrl: https://myvault.vault.azure.net/

  3. AWS Secrets Manager
     secrets:
       provider: aws-secrets-manager
       region: us-east-1

  4. HashiCorp Vault
     secrets:
       provider: hashicorp-vault
       address: https://vault.example.com
       authMethod: kubernetes  # or token, approle

  5. Kubernetes Secrets
     secrets:
       provider: kubernetes
       namespace: hermes

Secret Reference in Recipes:
  config_json: {
    "url": "https://api.vendor.com",
    "auth_token": "${secret:vendor_api_token}"  ← resolved at runtime
  }

  secret_binding_json: {
    "vendor_api_token": {
      "source": "env",            # or "azure-keyvault", "aws-sm", etc.
      "key": "VENDOR_API_TOKEN"
    }
  }

Security:
  - Secrets never stored in PostgreSQL
  - Secrets never logged (masked in event logs)
  - Secrets never returned in API responses
  - Secret values resolved at execution time only
  - Secret rotation supported (re-resolve on next execution)
```

### 11.5 TLS & Encryption

```
TLS Configuration
─────────────────

All communications encrypted:
  - API server: HTTPS (TLS 1.2+)
  - gRPC (plugin protocol): TLS
  - PostgreSQL: SSL mode = require
  - Kafka: SASL_SSL
  - Inter-node (coordinator ↔ worker): mTLS

Configuration:
  tls:
    enabled: true
    certFile: /etc/hermes/tls/server.crt
    keyFile: /etc/hermes/tls/server.key
    caFile: /etc/hermes/tls/ca.crt
    minVersion: "1.2"
    mtls:
      enabled: true                # for inter-node communication
      clientCertFile: /etc/hermes/tls/client.crt
      clientKeyFile: /etc/hermes/tls/client.key

Data Encryption at Rest:
  - Content Repository: AES-256-GCM encryption (optional)
  - Encryption key managed via secrets management
  - Per-claim encryption (different key per pipeline, optional)
  - Key rotation support (re-encrypt on GC cycle)
```

### 11.6 Multi-Tenancy

```
Workspace Isolation
───────────────────

Workspace = isolated tenant environment within Hermes

Table: workspaces
├── id, name, slug (URL-safe)
├── owner_id, created_at
├── resource_quota (JSONB)
├── settings (JSONB)
└── is_active

Isolation:
  - Every resource (pipeline, recipe, work item) belongs to a workspace
  - Database: workspace_id column on all tables + row-level security
  - Content Repository: per-workspace directory prefix
  - API: workspace context in JWT claims or URL prefix (/api/v1/workspaces/{ws}/...)
  - UI: workspace switcher in top navigation

Resource Quotas:
  workspace_quota:
    max_pipelines: 50
    max_active_pipelines: 10
    max_jobs_per_day: 100000
    max_content_repository_bytes: 50GB
    max_workers: 5
    max_api_requests_per_minute: 1000

Cross-Workspace:
  - Pipeline templates can be shared across workspaces
  - Plugin definitions are global (available to all workspaces)
  - System admin can view all workspaces
```

---

## 12. Data Preview & Testing (P2)

### 12.1 Preview Endpoint

```
Pipeline Preview
────────────────

POST /api/v1/pipelines/{id}/preview
Body: {
  "sampleData": { ... },           // or
  "sampleFile": "base64:...",      // or
  "sampleSource": "last_job",// use last successful input

  "steps": [1, 2, 3],             // which steps to preview (default: all)
  "maxItems": 10,                  // limit output items
  "timeout": 30                    // preview timeout (seconds)
}

Response: {
  "steps": [
    {
      "stepOrder": 1,
      "stageType": "COLLECT",
      "duration_ms": 120,
      "output": {
        "records": [...first 10 records...],
        "totalRecords": 15000,
        "schema": { "type": "object", "properties": {...} }
      }
    },
    {
      "stepOrder": 2,
      "stageType": "ALGORITHM",
      "duration_ms": 2100,
      "output": {
        "anomalies": [...],
        "statistics": {...}
      }
    }
  ],
  "totalDuration_ms": 2520
}

Preview runs in isolated sandbox:
  - No side effects (transfers are dry-run)
  - No work items created
  - No event logs persisted
  - Content Repository: temp claims (auto-deleted)
  - Timeout enforced (default 30s)
```

### 12.2 Test Mode

```
Plugin Test Mode
────────────────

POST /api/v1/plugins/{id}/test
Body: {
  "config": { "threshold": 3.0, "method": "zscore" },
  "input": { "data": [...] },
  "timeout": 30
}

Response: {
  "success": true,
  "output": { ... },
  "logs": [ ... ],
  "duration_ms": 450,
  "resourceUsage": {
    "peakMemoryMB": 128,
    "cpuTimeMs": 380
  }
}

Enables:
  - Test new plugin with sample data before deploying
  - Validate recipe changes before publishing
  - Debug plugin issues with controlled input
```

### 12.3 Dry-Run Mode

```
Dry-Run Pipeline Execution
──────────────────────────

POST /api/v1/pipelines/{id}/activate
Body: { "dryRun": true }

Dry-run behavior:
  - Monitor detects events normally
  - Work items created with flag: dry_run = true
  - COLLECT steps execute normally (read data)
  - ALGORITHM steps execute normally (process data)
  - TRANSFER steps are SKIPPED (no side effects)
  - All results logged and visible in Job Explorer
  - UI badge: "DRY RUN" on pipeline and work items

Use cases:
  - Validate new pipeline before going live
  - Test recipe changes against real data
  - Verify monitoring configuration detects expected events
```

---

## 13. Content-Based Routing & Branching (P2)

### 13.1 DAG Pipeline Topology

```
V1: Linear Pipeline
  Step 1 → Step 2 → Step 3

V2: DAG Pipeline (Directed Acyclic Graph)
  Step 1 → Step 2 ─┬→ Step 3a → Step 5
                    └→ Step 3b → Step 4 → Step 5

Supported Topology Patterns:
  LINEAR:    A → B → C
  BRANCH:    A → B ─┬→ C
                     └→ D
  MERGE:     A ─┐
              B ─┤→ D
              C ─┘
  ROUTER:    A → ROUTER ─┬→ B (if condition X)
                          ├→ C (if condition Y)
                          └→ D (default)
  FANOUT:    A → FANOUT → [B₁, B₂, ..., Bₙ] → MERGE → C
```

### 13.2 Step Types

```
New Step Types for V2
─────────────────────

ROUTER:
  Evaluate conditions on work item, route to one branch.
  config:
    routes:
      - condition: "$.metadata.equipment_type == 'TYPE_A'"
        targetStep: 3a
      - condition: "$.data.anomalyCount > 10"
        targetStep: 3b
      - default: true
        targetStep: 3c

FANOUT:
  Split one work item into many (e.g., one file → many records).
  config:
    splitPath: "$.data.records"     # JSONPath to array
    maxParallel: 10                 # max concurrent sub-items

MERGE:
  Combine multiple work items into one (e.g., aggregate results).
  config:
    strategy: WAIT_ALL | WAIT_ANY | TIMEOUT
    timeout: 300s
    mergeFunction: "concatenate"    # or "aggregate", "custom"

CONDITIONAL:
  Execute step only if condition is met.
  config:
    condition: "$.metadata.recordCount > 100"
    onFalse: SKIP | FAIL | DEFAULT_VALUE
```

### 13.3 React Flow Integration

```
Pipeline Designer (React Flow) — DAG Support
─────────────────────────────────────────────

React Flow (@xyflow/react) already supports:
  - Arbitrary node connections (not just linear)
  - Multiple output handles per node
  - Visual connection validation
  - Drag-and-drop node addition
  - Zoom, pan, minimap

V2 additions to Pipeline Designer:
  - ROUTER node type with condition editor
  - FANOUT node type with split configuration
  - MERGE node type with aggregation settings
  - Color-coded connections (by route/condition)
  - Connection labels (condition summary)
  - Validation: no cycles, all paths lead to terminal step
  - Live preview: highlight active path during execution

Node palette:
  ┌──────────────────────────────────────┐
  │  Node Types                          │
  │  ┌──────┐ ┌──────┐ ┌──────┐        │
  │  │COLLCT│ │ALGTHM│ │TRNSF │        │
  │  └──────┘ └──────┘ └──────┘        │
  │  ┌──────┐ ┌──────┐ ┌──────┐        │
  │  │ROUTER│ │FANOUT│ │MERGE │        │
  │  └──────┘ └──────┘ └──────┘        │
  │  ┌──────┐                            │
  │  │COND  │                            │
  │  └──────┘                            │
  └──────────────────────────────────────┘
```

---

## 14. Batching & Windowing (P3)

### 14.1 Batch Processing Mode

```
Batch Processing
────────────────

Collect N items before processing as a group.

Configuration:
  batch:
    enabled: true
    policies:
      maxCount: 100               # Process when 100 items collected
      maxBytes: 10MB              # Or when total size reaches 10MB
      maxWait: 60s                # Or when 60 seconds elapsed (whichever first)
    ordering: FIFO                # FIFO | LIFO | PRIORITY

Batch Flow:
  1. Monitor detects events → individual work items created
  2. Work items accumulate in batch buffer
  3. When batch policy triggers:
     a. Create BatchJob containing references to individual items
     b. Execute pipeline steps with batch as input
     c. Results mapped back to individual work items
  4. Each individual item tracked independently in Job Explorer

Use Cases:
  - Database inserts: batch 100 rows per INSERT for efficiency
  - API calls: batch requests to reduce HTTP overhead
  - File processing: process all files in a directory as one batch
```

### 14.2 Window-Based Processing

```
Window Processing
─────────────────

Tumbling Window:
  Fixed-size, non-overlapping time windows.
  window:
    type: tumbling
    duration: 5m                  # 5-minute windows
  Items collected in [00:00-05:00] processed together,
  then [05:00-10:00], etc.

Sliding Window:
  Fixed-size, overlapping windows.
  window:
    type: sliding
    duration: 5m                  # Window size
    slide: 1m                     # Slide interval
  Items in [00:00-05:00], [01:00-06:00], [02:00-07:00], etc.

Session Window:
  Dynamic windows based on activity gap.
  window:
    type: session
    gap: 30s                      # New window after 30s inactivity
  Window closes when no new items arrive for 30 seconds.

Configuration:
  windows:
    type: tumbling | sliding | session
    duration: 5m
    slide: 1m                     # only for sliding
    gap: 30s                      # only for session
    allowedLateness: 10s          # accept late-arriving items
    watermark: event_time         # event_time | processing_time
```

---

## 15. Enterprise Features (Exit-Strategy Features)

### 15.1 Multi-Tenancy

See Section 11.6 for workspace isolation details.

Additional enterprise multi-tenancy features:

```
Enterprise Multi-Tenancy
────────────────────────

1. Resource Isolation:
   - Per-workspace CPU/memory limits (cgroups on workers)
   - Per-workspace Content Repository quotas
   - Per-workspace API rate limits
   - Network isolation (optional, via network policies)

2. Billing & Metering:
   - Track resource usage per workspace:
     - Compute time (step execution seconds)
     - Storage (Content Repository bytes)
     - Network (data transferred bytes)
     - API calls (request count)
   - Usage exported as metrics for billing systems

3. Self-Service Onboarding:
   - Workspace creation wizard
   - Default quota templates (free, starter, enterprise)
   - Automatic plugin catalog provisioning
   - Sample pipeline templates
```

### 15.2 Pipeline Versioning & Git Integration

```
Git-Based Pipeline Versioning
─────────────────────────────

1. Pipeline-as-Code:
   - Every pipeline exportable as YAML/JSON file
   - Pipeline definitions stored in git repository
   - Changes tracked via commits

   hermes-pipelines/
   ├── equipment-monitoring/
   │   ├── pipeline.yaml          # pipeline definition
   │   ├── recipes/
   │   │   ├── collector-v3.yaml  # recipe versions
   │   │   └── algorithm-v5.yaml
   │   └── tests/
   │       ├── sample-input.json
   │       └── expected-output.json
   └── erp-sync/
       ├── pipeline.yaml
       └── recipes/
           └── ...

2. PR-Based Pipeline Changes:
   - Developer creates branch, modifies pipeline YAML
   - PR created → CI runs pipeline validation + preview
   - Code review → merge to main
   - CD syncs main branch to Hermes → pipeline updated

3. Environment Promotion:
   Branches map to environments:
     develop → dev Hermes instance
     staging → staging Hermes instance
     main    → production Hermes instance

   Promotion flow:
     develop → PR → staging → PR → main → auto-deploy

4. Rollback:
   - Revert git commit → previous pipeline version deployed
   - Hermes tracks which git commit each pipeline version came from
   - One-click rollback in UI (creates revert commit)

5. API:
   POST /api/v1/pipelines/import     # import from YAML
   GET  /api/v1/pipelines/{id}/export  # export to YAML
   POST /api/v1/pipelines/sync-git   # sync from git repo
```

### 15.3 Compliance & Audit

```
Compliance Features
───────────────────

1. Complete Audit Trail:
   - See Section 11.3 for audit log details
   - Every user action logged with who/what/when/where
   - Tamper-evident: audit log entries are hash-chained
   - Export to SIEM systems for centralized compliance

2. Data Lineage Graph:
   - End-to-end data journey visualization
   - From source (file/API/DB) through all processing steps to destination
   - Cross-pipeline lineage (when output of one feeds another)
   - Queryable: "Show me all data that touched pipeline X"
   - Visual graph in UI (built on React Flow)

   API:
   GET /api/v1/lineage/job/{id}     # lineage for one item
   GET /api/v1/lineage/pipeline/{id}      # lineage for pipeline
   GET /api/v1/lineage/data/{source_key}  # lineage by source

3. Retention Policies:
   retention:
     jobs:
       completed: 90d            # keep completed items for 90 days
       failed: 180d              # keep failed items longer
     executionLogs: 365d          # keep logs for 1 year
     auditLogs: 730d              # keep audit for 2 years
     contentClaims: 30d           # keep content for 30 days after last ref
     dlqEntries: 90d              # keep DLQ entries for 90 days

   Auto-purge job runs daily, respects retention policies.

4. GDPR Support:
   - Data Subject Access Request (DSAR):
     POST /api/v1/compliance/dsar
     Body: { "subjectId": "user@example.com", "requestType": "access" }
     → Returns all data associated with subject across all pipelines

   - Right to Erasure:
     POST /api/v1/compliance/erasure
     Body: { "subjectId": "user@example.com" }
     → Deletes all content claims containing subject's data
     → Anonymizes work item metadata
     → Logs erasure in audit trail

   - Data Processing Agreement tracking:
     Table: data_processing_agreements
     ├── pipeline_id, data_category, legal_basis
     ├── retention_period, processor_name
     └── approved_by, approved_at

5. SOC2 / ISO27001 Readiness:
   - Access control: RBAC with least-privilege (Section 11.2)
   - Encryption: TLS in transit, AES-256 at rest (Section 11.5)
   - Monitoring: comprehensive logging and alerting (Section 9)
   - Incident response: DLQ + bulletin board for operational issues
   - Change management: git-based versioning with approval flow
   - Business continuity: HA coordinator, worker failover, WAL recovery
```

### 15.4 API Gateway & Marketplace

```
Plugin Marketplace
──────────────────

1. Internal Marketplace:
   - Organization-private plugin registry
   - Plugin versioning with semantic versioning
   - Dependency management
   - Usage statistics per plugin

2. Public Marketplace (future):
   - Community-contributed plugins
   - Verified publisher program
   - Security scanning before listing
   - Revenue sharing for paid plugins

3. Plugin Registry API:
   GET    /api/v1/marketplace/plugins           # browse
   GET    /api/v1/marketplace/plugins/{id}      # detail
   POST   /api/v1/marketplace/plugins           # publish
   POST   /api/v1/marketplace/plugins/{id}/install  # install to workspace
   DELETE /api/v1/marketplace/plugins/{id}      # unpublish

4. Plugin Packaging:
   hermes-plugin.tar.gz
   ├── hermes-plugin.json          # manifest
   ├── README.md                   # documentation
   ├── CHANGELOG.md                # version history
   ├── src/                        # source code
   ├── Dockerfile                  # for container execution
   └── tests/                      # plugin tests

Webhook Management:
  - Register webhooks for pipeline events
  - Webhook retry with exponential backoff
  - Webhook signature verification (HMAC-SHA256)
  - Webhook delivery log

SSO Integration:
  - SAML 2.0 support (enterprise IdPs)
  - OIDC (see Section 11.1)
  - SCIM for user provisioning
  - Just-in-time user creation
```

### 15.5 Analytics & Reporting

```
Analytics & Reporting
─────────────────────

1. Pipeline Performance Analytics:
   - Processing time trends (per step, per pipeline)
   - Throughput analysis (items/hour, items/day)
   - Error rate analysis (by type, by step, by time)
   - Capacity planning projections

2. Cost Tracking:
   - Compute cost: step execution time * worker cost/hour
   - Storage cost: Content Repository size * storage cost/GB
   - Network cost: data transferred * network cost/GB
   - Per-pipeline cost breakdown
   - Cost anomaly detection

3. SLA Monitoring:
   sla:
     - name: "Equipment data processed within 5 minutes"
       pipeline: "equipment-monitoring"
       metric: end_to_end_latency
       threshold: 300s
       target: 99.9%             # 99.9% of items within 5 minutes
       window: 30d               # measured over 30-day rolling window
       alertOnBreach: true

   Dashboard:
     - SLA compliance percentage (current period)
     - SLA trend over time
     - Breach count and details
     - Time to resolution for breaches

4. Custom Dashboards:
   - User-created dashboards with drag-and-drop widgets
   - Widget types: chart, table, gauge, map, text
   - Dashboard sharing and embedding
   - Scheduled report delivery (email/Slack)

5. Executive Reports:
   - Weekly/monthly summary reports
   - Data volume processed
   - System availability
   - SLA compliance
   - Cost summary
   - Trend analysis
```

---

## 16. Roadmap (Phased Delivery)

### Phase 1: MVP (3 months)

```
Deliverables:
  ✓ Core pipeline CRUD + Recipe management
  ✓ Plugin system (YAML manifest + stdin/stdout protocol)
  ✓ File/API/Kafka collectors (built-in)
  ✓ Job tracking + basic reprocessing
  ✓ Web UI:
    - Pipeline Designer (React Flow, linear topology)
    - Recipe Editor (react-jsonschema-form)
    - Monitor Dashboard (real-time via WebSocket)
    - Job Explorer (search, filter, detail view)
  ✓ PostgreSQL + SQLAlchemy/EF Core
  ✓ Docker Compose deployment
  ✓ REST API (OpenAPI 3.0 documented)
  ✓ Basic test suite (pytest/xUnit, >60% coverage)
  ✓ CLAUDE.md + ARCHITECTURE.md documentation

Milestone: Demo-ready product for early adopters.
Target: "I can show this to a potential customer."
```

### Phase 2: Production-Ready (+2 months)

```
Deliverables:
  ○ Back-pressure management (Section 4)
  ○ Dead Letter Queue (Section 5)
  ○ Schema registry + drift detection (Section 6)
  ○ Content Repository — disk-based storage (Section 3.1)
  ○ Write-Ahead Log for crash recovery (Section 3.2)
  ○ Retry/Circuit Breaker via Polly/tenacity (Section 10)
  ○ Prometheus metrics endpoint (Section 9.1)
  ○ Structured logging (Section 9.3)
  ○ Health check endpoints (Section 9.4)
  ○ Authentication — JWT (Section 11.1)
  ○ NiFi integration bridge (NIFI_INTEGRATION.md)
  ○ 80%+ test coverage
  ○ Performance benchmarks: 10K items/hour sustained

Milestone: Production deployment at design partner.
Target: "A real company is running this in production."
```

### Phase 3: Enterprise (+3 months)

```
Deliverables:
  ○ Distributed cluster — coordinator + workers (Section 2)
  ○ Leader election + coordinator failover (Section 2.2)
  ○ Work distribution + rebalancing (Section 2.3)
  ○ Node failure handling + poison pill detection (Section 2.4)
  ○ Swap files for queue overflow (Section 3.3)
  ○ Persistent state store (Section 3.4)
  ○ RBAC + audit log (Sections 11.2, 11.3)
  ○ gRPC plugin protocol (Section 7.2)
  ○ Streaming + chunked transfer for large data (Section 7.3)
  ○ Exactly-once processing + checkpointing (Section 8)
  ○ Data preview + dry-run mode (Section 12)
  ○ Content-based routing + DAG topology (Section 13)
  ○ OpenTelemetry tracing (Section 9.2)
  ○ Grafana dashboard templates (Section 9.7)
  ○ Helm chart + Kubernetes manifests
  ○ Kubernetes operator (basic)

Milestone: Enterprise pilot deployment.
Target: "An enterprise is evaluating this for purchase."
```

### Phase 4: Exit-Ready (+3 months)

```
Deliverables:
  ○ Multi-tenancy + workspace isolation (Section 11.6)
  ○ Plugin marketplace (Section 15.4)
  ○ Git integration + pipeline-as-code (Section 15.2)
  ○ Compliance features — GDPR, audit, data lineage (Section 15.3)
  ○ SLA monitoring + analytics (Section 15.5)
  ○ Batching + windowing (Section 14)
  ○ Secrets management — Vault/KV/SM integration (Section 11.4)
  ○ SSO — SAML 2.0 + SCIM (Section 15.4)
  ○ Kubernetes operator (advanced — auto-scaling, upgrades)
  ○ Edge nodes for remote sites (Section 2.1)
  ○ Commercial documentation site
  ○ Enterprise support tooling (support ticket integration)
  ○ Security audit + penetration test
  ○ SOC2 Type II certification readiness

Milestone: Acquisition-ready product.
Target: "A strategic buyer sees this as worth acquiring."
```

---

## 17. Competitive Comparison (Updated for V2)

| Feature | **Hermes V2** | **Apache NiFi** | **Airbyte** | **Benthos** | **n8n** | **Airflow** |
|---|---|---|---|---|---|---|
| **Core Focus** | Data processing + tracking | Data routing + provenance | EL (Extract-Load) | Stream processing | Workflow automation | DAG orchestration |
| **Per-Item Tracking** | First-class Job Explorer | Provenance (developer UI) | Partial (sync logs) | No | No | No |
| **Visual Pipeline Designer** | React Flow (modern) | Java Swing canvas | Config UI only | No (YAML only) | Node editor | No (Python code) |
| **Recipe/Config Management** | Versioned, form-based, diffable | Parameter Contexts | Connection config | YAML files | Node params | Variables |
| **Reprocessing** | First-class, any step, with snapshot | Manual provenance replay | Full re-sync only | No | Manual re-execute | DAG re-run |
| **Plugin System** | Any language (gRPC + stdin/stdout) | Java only | Docker per connector | Go only | JS only | Python only |
| **Back-Pressure** | Per-step, configurable thresholds | Built-in (connection-based) | No | Built-in | No | No (not streaming) |
| **Dead Letter Queue** | Built-in, UI explorer, replay | No (manual handling) | No | Built-in (basic) | No | No |
| **Schema Registry** | Built-in, drift detection, evolution | No | Schema inference | No | No | No |
| **Content Repository** | Disk-based, content-addressed | Built-in (Java NIO) | No (memory/Docker) | No (memory) | No | No (XCom, limited) |
| **Exactly-Once** | Checkpointing + idempotency keys | Built-in (FlowFile repo) | At-least-once | At-least-once | At-most-once | At-least-once |
| **Distributed** | Coordinator + Workers + Edge | Clustered (ZooKeeper) | Docker-based scaling | No (single process) | Queue mode (Redis) | Celery workers |
| **Failure Handling** | Retry + circuit breaker + DLQ + poison pill | Penalize + route | Retry only | Retry only | Retry only | Retry only |
| **Observability** | Prometheus + OTel + Grafana | JMX + NiFi API | Prometheus (basic) | Prometheus (basic) | No | Prometheus + StatsD |
| **Security** | JWT/OIDC + RBAC + audit + secrets | LDAP/Kerberos + policies | Basic auth | No | Basic auth | RBAC + LDAP |
| **Multi-Tenancy** | Workspace isolation + quotas | No (single tenant) | Multi-workspace | No | No | No |
| **Git Integration** | Pipeline-as-code, PR workflow | NiFi Registry | Octavia CLI | YAML in git | No | Native (DAGs in git) |
| **Compliance** | Audit log + data lineage + GDPR | Provenance (raw) | No | No | No | Audit log |
| **Memory Footprint** | ~256MB base | ~2GB+ (JVM) | ~1GB+ (Docker) | ~50MB | ~256MB | ~512MB+ |
| **Deployment** | Docker/K8s/binary | JVM + ZooKeeper | Docker Compose/K8s | Binary | Docker/K8s | Docker/K8s |
| **License** | Apache 2.0 | Apache 2.0 | ELv2 (source-avail) | MIT | Sustainable Use | Apache 2.0 |
| **Target User** | Operators + developers | Developers + data engineers | Data engineers | Developers | Citizen developers | Data engineers |
| **Maturity** | Early (building) | Mature (10+ years) | Growing (3+ years) | Stable (5+ years) | Growing (5+ years) | Mature (8+ years) |

### Hermes V2 Unique Advantages

1. **Per-Item Tracking + Reprocessing**: No other tool offers NiFi-grade provenance with one-click reprocessing in a lightweight package.

2. **Operator-First UI**: n8n-grade simplicity with NiFi-grade power. Non-developers can configure complex pipelines.

3. **Polyglot Plugin System**: gRPC + stdin/stdout protocol means plugins in any language. No vendor lock-in to Java/Python/Go.

4. **Content Repository + Lightweight Footprint**: Disk-based NiFi-style content storage at 1/8th the memory footprint.

5. **Schema Registry Built-In**: No separate Confluent Schema Registry deployment. Schema management integrated into pipeline lifecycle.

6. **Exit-Ready Architecture**: Multi-tenancy, compliance, marketplace — features that make the product acquisition-worthy from day one of design.

---

## 18. Deployment Architecture

### 18.1 Docker Compose (Development / Small Production)

```yaml
# docker-compose.yml (simplified)
services:
  coordinator:
    image: hermes/coordinator:2.0
    ports:
      - "8000:8000"    # API
      - "3000:3000"    # Web UI
    environment:
      - VESSEL_ROLE=coordinator
      - DATABASE_URL=postgresql://hermes:pass@postgres:5432/hermes
    volumes:
      - content-repo:/var/hermes/content
    depends_on:
      - postgres

  worker:
    image: hermes/worker:2.0
    environment:
      - VESSEL_ROLE=worker
      - VESSEL_COORDINATOR_URL=http://coordinator:8000
      - DATABASE_URL=postgresql://hermes:pass@postgres:5432/hermes
    volumes:
      - content-repo:/var/hermes/content
    deploy:
      replicas: 2

  postgres:
    image: postgres:16
    volumes:
      - pgdata:/var/lib/postgresql/data

  prometheus:
    image: prom/prometheus:latest
    volumes:
      - ./deployment/prometheus.yml:/etc/prometheus/prometheus.yml

  grafana:
    image: grafana/grafana:latest
    volumes:
      - ./deployment/grafana/dashboards:/var/lib/grafana/dashboards

volumes:
  content-repo:
  pgdata:
```

### 18.2 Kubernetes (Production)

```yaml
# Helm chart values (simplified)
hermes:
  coordinator:
    replicas: 2                    # HA pair
    resources:
      requests: { cpu: 500m, memory: 512Mi }
      limits: { cpu: 2000m, memory: 2Gi }
    persistence:
      contentRepository:
        size: 100Gi
        storageClass: fast-ssd

  worker:
    replicas: 5
    autoscaling:
      enabled: true
      minReplicas: 2
      maxReplicas: 20
      targetCPUUtilization: 70
    resources:
      requests: { cpu: 1000m, memory: 1Gi }
      limits: { cpu: 4000m, memory: 4Gi }
    persistence:
      contentRepository:
        size: 50Gi
      swap:
        size: 20Gi

  postgresql:
    enabled: true                  # or use external
    replicas: 3                    # HA cluster
    persistence:
      size: 50Gi

  monitoring:
    prometheus:
      enabled: true
      serviceMonitor: true
    grafana:
      enabled: true
      dashboards: true

  ingress:
    enabled: true
    className: nginx
    tls: true
    hosts:
      - hermes.example.com
```

### 18.3 Kubernetes Operator (Phase 3-4)

```
Hermes Kubernetes Operator
──────────────────────────

Custom Resources:
  HermesCluster    — defines a Hermes cluster (coordinator + workers)
  HermesPipeline   — pipeline definition (synced from CR to Hermes API)
  HermesPlugin     — plugin deployment (manages plugin containers)

Operator Responsibilities:
  - Auto-scaling workers based on queue depth
  - Rolling upgrades with zero downtime
  - Automatic failover on node failure
  - Content Repository storage management
  - Certificate rotation for mTLS
  - Backup/restore coordination

Example:
  apiVersion: hermes.io/v1alpha1
  kind: HermesCluster
  metadata:
    name: production
  spec:
    coordinator:
      replicas: 2
    workers:
      minReplicas: 3
      maxReplicas: 15
      scaleMetric: queue_depth
      scaleThreshold: 1000
    storage:
      contentRepository:
        class: fast-ssd
        size: 500Gi
      wal:
        class: fast-ssd
        size: 50Gi
```

---

## 19. Migration Guide (V1 → V2)

```
V1 to V2 Migration Path
────────────────────────

Phase 1: Non-Breaking Upgrades
  - V2 is backward compatible with V1 API
  - Existing pipelines continue working
  - New features are opt-in

Phase 2: Enable V2 Features
  1. Content Repository:
     - Set VESSEL_CONTENT_REPO_PATH=/var/hermes/content
     - Existing in-memory data flow continues to work
     - New pipelines can opt-in to content repo

  2. Back-Pressure:
     - Enabled by default with conservative thresholds
     - Existing pipelines get default back-pressure config
     - Tune per-pipeline as needed

  3. DLQ:
     - Auto-created for each pipeline
     - Failed items that would have been lost now go to DLQ
     - No configuration needed for basic DLQ

Phase 3: Distributed Deployment
  - Deploy coordinator + workers
  - Existing single-node continues to work
  - Scale by adding workers
  - No pipeline reconfiguration needed

Database Migration:
  - Alembic/EF Core migrations handle schema changes
  - New tables added (step_checkpoints, content_refs, etc.)
  - Existing tables gain new columns with defaults
  - Zero-downtime migration supported
```

---

## 20. Success Metrics

```
Success Metrics for V2
──────────────────────

Technical:
  - Throughput: 100K items/hour sustained (single worker)
  - Latency: <100ms p99 for API responses
  - Availability: 99.9% uptime with HA coordinator
  - Recovery: <30s coordinator failover
  - Memory: <256MB base footprint per worker
  - Storage: Content Repository handles 1TB+ per node

Adoption:
  - GitHub stars: 1,000+ within 6 months of launch
  - Contributors: 20+ within 12 months
  - Production deployments: 10+ within 12 months
  - Plugin ecosystem: 50+ community plugins within 18 months

Commercial:
  - Design partner: 1 paying customer within 6 months
  - Revenue: $100K ARR within 18 months
  - Enterprise pilot: 3 enterprise evaluations within 12 months
  - Acquisition interest: Inbound inquiry from strategic buyer within 24 months
```
