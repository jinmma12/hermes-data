# Hermes Cluster Design

> **Hermes** (formerly Hermes): Enterprise-grade, lightweight data processing platform
> with distributed execution, disk-based storage, and production-hardened reliability.
>
> This document specifies the cluster architecture across all deployment modes,
> from single-node development to large-scale enterprise production.

---

## Table of Contents

1. [Cluster Modes](#1-cluster-modes)
2. [Node Election and Coordination](#2-node-election-and-coordination)
3. [Work Distribution](#3-work-distribution)
4. [Failure Handling](#4-failure-handling)
5. [Cluster Communication](#5-cluster-communication)
6. [Log Viewer (Web UI)](#6-log-viewer-web-ui)
7. [Cluster Configuration](#7-cluster-configuration)
8. [Deployment Topologies](#8-deployment-topologies)
9. [Security Considerations](#9-security-considerations)
10. [Migration Path](#10-migration-path)

---

## 1. Cluster Modes

Hermes supports three deployment modes, each building on the previous one.
The mode is selected via the `Hermes.Cluster.Mode` configuration key and
determines which subsystems are activated at startup.

### Mode 1: Standalone (Phase 1)

```
┌─────────────────────────────────────────────┐
│              Hermes (single process)        │
│                                             │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ API      │  │ Worker   │  │ Monitor  │  │
│  │ Server   │  │ Engine   │  │ Service  │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │              │              │        │
│       └──────────────┼──────────────┘        │
│                      │                       │
│              ┌───────┴───────┐               │
│              │  PostgreSQL   │               │
│              │  (state)      │               │
│              └───────────────┘               │
└─────────────────────────────────────────────┘
```

**Characteristics:**

- Single node, single OS process
- API server, worker engine, and monitoring all co-located
- PostgreSQL for persistent state (pipelines, work items, provenance)
- Content Repository on local disk
- No coordination protocol required
- No heartbeat, no election, no inter-node communication

**Suitable for:**

- Local development and testing
- Small deployments (fewer than 50 pipelines, under 1000 work items/hour)
- Demo and evaluation environments
- CI/CD pipeline testing

**Limitations:**

- Single point of failure (no HA)
- Vertical scaling only (bound by single-machine resources)
- No work distribution across machines

**Startup behavior:**

1. Process starts with `Mode=Standalone`
2. Initializes local Content Repository
3. Starts API server on configured port (default 8000)
4. Starts worker engine (inline, no gRPC)
5. Starts monitoring service (inline)
6. Ready to accept pipelines and process work items

---

### Mode 2: Minimal Cluster (Phase 3)

```
┌──────────────────┐  ┌──────────────────┐  ┌──────────────────┐
│   Node 1         │  │   Node 2         │  │   Node 3         │
│   (Coordinator)  │  │   (Worker)       │  │   (Worker)       │
│                  │  │                  │  │                  │
│  ┌────────────┐  │  │  ┌────────────┐  │  │  ┌────────────┐  │
│  │ API Server │  │  │  │ Worker     │  │  │  │ Worker     │  │
│  │ Scheduler  │  │  │  │ Engine     │  │  │  │ Engine     │  │
│  │ Health Mon │  │  │  │ Plugin RT  │  │  │  │ Plugin RT  │  │
│  │ Embedded   │  │  │  │ Content    │  │  │  │ Content    │  │
│  │ ZooKeeper  │  │  │  │ Repo       │  │  │  │ Repo       │  │
│  └─────┬──────┘  │  │  └─────┬──────┘  │  │  └─────┬──────┘  │
│        │         │  │        │         │  │        │         │
└────────┼─────────┘  └────────┼─────────┘  └────────┼─────────┘
         │                     │                     │
    ┌────┴─────────────────────┴─────────────────────┴────┐
    │                    PostgreSQL                        │
    │              (shared metadata store)                 │
    └─────────────────────────────────────────────────────┘
```

**Characteristics:**

- Minimum 3 nodes for quorum-safe operation
- Deployment options:
  - **Dedicated roles**: 1 Coordinator + 2 Workers (recommended)
  - **Peer election**: 3 identical nodes, one elected as coordinator
- Embedded ZooKeeper on the coordinator node for coordination
- Shared PostgreSQL for persistent state
- Each worker has its own local Content Repository partition
- gRPC for inter-node communication

**Suitable for:**

- Production deployments with HA requirements
- Moderate throughput (up to 10,000 work items/hour)
- Teams that want fault tolerance without infrastructure complexity

**Peer election mode:**

In this variant all three nodes start identically. On boot each node
attempts to acquire the coordinator lease. The winner becomes the
coordinator; the other two become workers. If the coordinator goes
down, the remaining two nodes hold a new election.

**Minimum node count rationale:**

- 1 node = standalone (no fault tolerance)
- 2 nodes = no quorum possible on split (unsafe)
- 3 nodes = tolerates 1 node failure with quorum

---

### Mode 3: Large Cluster (Phase 4)

```
┌──────────┐ ┌──────────┐ ┌──────────┐
│ Coord 1  │ │ Coord 2  │ │ Coord 3  │     Coordinator Pool
│ (Leader) │ │(Standby) │ │(Standby) │     (HA, active/standby)
└────┬─────┘ └────┬─────┘ └────┬─────┘
     │             │             │
     └─────────────┼─────────────┘
                   │
    ┌──────────────┼──────────────────────────┐
    │              │                          │
┌───┴──────┐ ┌────┴─────┐ ┌──────────┐ ┌────┴─────┐
│ Worker 1 │ │ Worker 2 │ │ Worker 3 │ │ Worker N │
│          │ │          │ │          │ │          │
│ Content  │ │ Content  │ │ Content  │ │ Content  │
│ Repo     │ │ Repo     │ │ Repo     │ │ Repo     │
└──────────┘ └──────────┘ └──────────┘ └──────────┘
                   │
    ┌──────────────┼──────────────┐
    │              │              │
┌───┴──────┐ ┌────┴─────┐ ┌─────┴────┐
│ ZK / etcd│ │ ZK / etcd│ │ ZK / etcd│   External coordination
│ Node 1   │ │ Node 2   │ │ Node 3   │   cluster
└──────────┘ └──────────┘ └──────────┘
                   │
          ┌────────┴────────┐
          │   PostgreSQL    │
          │   (HA cluster)  │
          └─────────────────┘
```

**Characteristics:**

- 3 or more coordinator nodes (active/standby with leader election)
- N worker nodes (horizontal scale-out)
- External ZooKeeper or etcd cluster for coordination
- PostgreSQL HA cluster (e.g., Patroni, Citus, or cloud-managed)
- Load balancer in front of coordinator API endpoints
- Per-worker Content Repository with optional shared storage (NFS, S3)

**Suitable for:**

- Enterprise deployments processing millions of work items per day
- Multi-team, multi-tenant environments
- Deployments requiring zero-downtime upgrades
- Kubernetes-native operation via Hermes Operator

**Scaling dimensions:**

| Dimension | How to Scale |
|---|---|
| Throughput | Add worker nodes |
| Storage | Expand Content Repository partitions, add S3 tier |
| API capacity | Add coordinator standbys behind load balancer |
| Coordination | Scale ZooKeeper/etcd ensemble (3 → 5 → 7 nodes) |
| Database | PostgreSQL read replicas, connection pooling (PgBouncer) |

---

## 2. Node Election and Coordination

### Coordination Technology Options

Hermes supports three coordination backends, each suited to a different
deployment scale. The choice is made via `Hermes.Cluster.Coordination.Type`.

#### Option A: PostgreSQL Advisory Locks

**How it works:**

```
Coordinator Election via PostgreSQL Advisory Locks
──────────────────────────────────────────────────

1. Each coordinator candidate attempts:
   SELECT pg_try_advisory_lock(hashtext('hermes-coordinator-leader'))

2. Winner holds the lock for its PostgreSQL session lifetime.
   The lock is automatically released if:
   - The process exits (gracefully or crashes)
   - The PostgreSQL connection drops
   - The session is terminated

3. Other candidates poll every 5 seconds:
   SELECT pg_try_advisory_lock(hashtext('hermes-coordinator-leader'))

4. If the active coordinator crashes, PostgreSQL releases the lock
   within the connection timeout (~5-10 seconds).
   The next polling candidate acquires it.

5. To prevent stale leaders, the winner also writes a row to
   the coordinator_lease table with a TTL:

   INSERT INTO coordinator_lease (node_id, fencing_token, acquired_at, expires_at)
   VALUES ($1, nextval('fencing_token_seq'), now(), now() + interval '30 seconds')
   ON CONFLICT (lock_name) DO UPDATE SET ...

   The leader must renew this lease every 10 seconds.
```

**Advantages:**

- No additional infrastructure (uses existing PostgreSQL)
- Well-understood semantics, battle-tested in PostgreSQL
- Automatic cleanup on process crash
- Simple to implement and debug

**Disadvantages:**

- Tied to PostgreSQL availability (PostgreSQL down = no elections)
- Polling-based, not event-driven (slightly higher failover time: 5-15s)
- Not suitable for clusters larger than ~10 nodes

**Recommended for:** Standalone to Minimal Cluster transition (Phase 2)

---

#### Option B: Embedded ZooKeeper

**How it works:**

```
Coordinator Election via Embedded ZooKeeper
────────────────────────────────────────────

1. The coordinator node runs an embedded ZooKeeper instance.
   (NiFi 1.x uses this exact pattern — proven in production.)

2. All nodes connect to the embedded ZooKeeper as clients.

3. Leader election uses the ZooKeeper recipe:
   a. Each candidate creates an ephemeral sequential znode:
      /hermes/election/candidate-000000001
      /hermes/election/candidate-000000002
   b. Node with the lowest sequence number is the leader.
   c. Each non-leader watches the znode immediately before it.
   d. If the watched znode is deleted (node died), check if
      this node is now the lowest → become leader.

4. Cluster membership tracked via ephemeral znodes:
   /hermes/nodes/{node-id}  (ephemeral, data = NodeInfo JSON)

5. Configuration changes distributed via ZooKeeper watches:
   /hermes/config/{key}  → all nodes notified on change

6. Embedded ZooKeeper data stored locally:
   ./data/zookeeper/  (configurable via Coordination.ZooKeeper.DataDir)
```

**.NET integration:**

- Client library: [ZooKeeperNetEx](https://github.com/shayhatsor/zookeeper) (Apache 2.0)
- Embedded server: JVM-based ZooKeeper launched as a managed subprocess
- Alternative: Use [dotnet-zookeeper](https://github.com/ewoutkramer/dotnet-zookeeper)

**Advantages:**

- No external dependency for small clusters (embedded mode)
- Event-driven (watches), sub-second failover detection
- Proven pattern (Apache NiFi 1.x uses this exact approach)
- Rich coordination primitives (locks, barriers, queues)

**Disadvantages:**

- Embedded ZooKeeper requires JVM on the coordinator node
- Additional operational complexity vs. PostgreSQL advisory locks
- ZooKeeper data must be backed up separately

**Recommended for:** Minimal Cluster (Phase 3)

---

#### Option C: etcd

**How it works:**

```
Coordinator Election via etcd Lease
────────────────────────────────────

1. Each candidate creates an etcd lease with TTL=15s.

2. Candidates race to create key "/hermes/leader" with their
   lease attached (using an etcd transaction with compare-and-swap):

   txn.If(
     Key("/hermes/leader").CreateRevision == 0  // key doesn't exist
   ).Then(
     Put("/hermes/leader", nodeId, WithLease(leaseId))
   )

3. Winner refreshes the lease via KeepAlive stream every 5s.

4. If the leader crashes:
   - KeepAlive stream breaks
   - Lease expires after TTL (15s)
   - Key "/hermes/leader" is deleted
   - Other candidates detect deletion via Watch and race again

5. Cluster membership:
   /hermes/nodes/{node-id}  (with lease, auto-cleaned on crash)

6. Configuration distribution:
   /hermes/config/{key}  (watched by all nodes)
```

**.NET integration:**

- Client library: [dotnet-etcd](https://github.com/shaman-apprentice/dotnet-etcd) (MIT)
- Native gRPC protocol (no JVM dependency)

**Advantages:**

- Lighter than ZooKeeper (single static binary, no JVM)
- Native gRPC protocol (aligns with Hermes inter-node communication)
- First-class Kubernetes integration (etcd is Kubernetes' own store)
- Simpler operational model than ZooKeeper

**Disadvantages:**

- Requires an external etcd cluster (no embedded mode)
- Smaller ecosystem of coordination recipes compared to ZooKeeper
- Less battle-tested for this specific use case compared to ZooKeeper + NiFi

**Recommended for:** Large Cluster (Phase 4), especially Kubernetes deployments

---

### Phased Recommendation

```
Phase 1 (Standalone)      → No coordination needed.
                             Single process; all components in-proc.

Phase 2 (HA Standalone)   → PostgreSQL Advisory Locks.
                             Simplest path to active/standby coordinator.
                             No new infrastructure. 5-15s failover.

Phase 3 (Minimal Cluster) → Embedded ZooKeeper.
                             Sub-second failover. Event-driven coordination.
                             Proven NiFi pattern. 3-node minimum.

Phase 4 (Large Cluster)   → External ZooKeeper or etcd.
                             ZooKeeper for existing JVM shops.
                             etcd for Kubernetes-native deployments.
                             Independent scaling of coordination layer.
```

---

### Leader Election Protocol

Regardless of the coordination backend, the leader election follows the
same logical protocol:

```
Leader Election State Machine
─────────────────────────────

States:
  CANDIDATE  → Attempting to acquire leadership
  LEADER     → Holds the leader lease, serving as coordinator
  FOLLOWER   → Lost election, watching for leader failure
  DEMOTED    → Was leader, lost lease (network partition, overload)

Transitions:
  CANDIDATE → LEADER    : Acquired leader lease
  CANDIDATE → FOLLOWER  : Another node acquired lease first
  LEADER    → DEMOTED   : Failed to renew lease within TTL
  LEADER    → DEMOTED   : Lost quorum (< 50% of known workers reachable)
  FOLLOWER  → CANDIDATE : Leader lease expired / leader znode deleted
  DEMOTED   → CANDIDATE : After cool-down period (10s)

On becoming LEADER:
  1. Increment fencing token (monotonic counter persisted in PostgreSQL)
  2. Write leader announcement to coordination store
  3. Load cluster state from PostgreSQL
  4. Begin accepting worker registrations
  5. Start work assignment loop
  6. Start health monitoring loop

On becoming FOLLOWER:
  1. Stop accepting new work assignments (if was leader)
  2. Watch leader znode / lease for changes
  3. Optionally serve read-only API requests (if configured)

On becoming DEMOTED:
  1. Immediately stop all coordinator functions
  2. Reject any in-flight assignment requests
  3. Log demotion event with reason
  4. Wait cool-down period before re-entering CANDIDATE
```

#### Fencing Tokens

Fencing tokens prevent stale leaders from corrupting state after a
network partition heals. Every write the coordinator makes to
PostgreSQL carries its fencing token.

```
Fencing Token Protocol
──────────────────────

1. On election, new leader:
   UPDATE cluster_state SET fencing_token = fencing_token + 1
   RETURNING fencing_token
   → Stores this as current_fencing_token

2. All coordinator writes include the token:
   UPDATE jobs SET status = 'ASSIGNED', fencing_token = $token
   WHERE id = $id AND fencing_token < $token

3. PostgreSQL trigger enforces monotonicity:
   CREATE OR REPLACE FUNCTION enforce_fencing_token()
   RETURNS trigger AS $$
   BEGIN
     IF NEW.fencing_token < OLD.fencing_token THEN
       RAISE EXCEPTION 'Stale fencing token: % < %',
         NEW.fencing_token, OLD.fencing_token;
     END IF;
     RETURN NEW;
   END;
   $$ LANGUAGE plpgsql;

4. If a stale leader (old fencing token) tries to write:
   → Write rejected by trigger
   → Stale leader detects rejection → self-demotes
```

#### Leader Lease Duration and Renewal

| Parameter | Default | Description |
|---|---|---|
| `lease_ttl` | 30s | Time before an unrenewed lease expires |
| `renewal_interval` | 10s | How often the leader renews its lease |
| `election_timeout` | 15s | Max time to wait for election result |
| `cool_down` | 10s | Delay before a demoted leader re-candidates |
| `quorum_check_interval` | 15s | How often the leader verifies worker quorum |

The lease TTL should be at least 3x the renewal interval to tolerate
transient network issues without triggering unnecessary failovers.

---

## 3. Work Distribution

### Job Assignment Model

Hermes uses a **pull-based** job assignment model. Workers pull jobs
from the coordinator rather than having jobs pushed to them. This
naturally provides back-pressure: overloaded workers simply stop pulling.

```
Job Assignment Flow
───────────────────

  Worker                     Coordinator                  PostgreSQL
    │                            │                            │
    │── RequestWork(capacity) ──→│                            │
    │                            │── SELECT next_queued ─────→│
    │                            │←─ job_row ─────────────────│
    │                            │                            │
    │                            │── Apply affinity rules     │
    │                            │── Apply load balancing     │
    │                            │── Score candidate workers  │
    │                            │                            │
    │                            │── UPDATE SET assigned ────→│
    │                            │   WHERE fencing_token OK   │
    │                            │←─ confirmed ───────────────│
    │                            │                            │
    │←─ JobAssignment ───────────│                            │
    │                            │                            │
    │   (process job locally)    │                            │
    │                            │                            │
    │── CompleteJob(result) ────→│                            │
    │                            │── UPDATE SET completed ───→│
    │                            │←─ confirmed ───────────────│
    │←─ Ack ─────────────────────│                            │
    │                            │                            │
    │── RequestWork(capacity) ──→│  (cycle repeats)           │
```

### Job Queue in PostgreSQL

```sql
CREATE TABLE job_queue (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_id     UUID NOT NULL REFERENCES pipelines(id),
    target_id       VARCHAR(200),
    priority        INTEGER NOT NULL DEFAULT 0,
    status          VARCHAR(20) NOT NULL DEFAULT 'QUEUED',
        -- QUEUED, ASSIGNED, PROCESSING, COMPLETED, FAILED, POISON, CANCELLED
    assigned_worker VARCHAR(100),
    assigned_at     TIMESTAMPTZ,
    lease_expires   TIMESTAMPTZ,
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    retry_count     INTEGER NOT NULL DEFAULT 0,
    max_retries     INTEGER NOT NULL DEFAULT 3,
    fencing_token   BIGINT NOT NULL DEFAULT 0,
    payload_json    JSONB,
    result_json     JSONB,
    error_message   TEXT,
    affinity_key    VARCHAR(200),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_job_queue_status ON job_queue(status, priority DESC, created_at);
CREATE INDEX idx_job_queue_worker ON job_queue(assigned_worker) WHERE status = 'ASSIGNED';
CREATE INDEX idx_job_queue_lease ON job_queue(lease_expires) WHERE status = 'ASSIGNED';
CREATE INDEX idx_job_queue_affinity ON job_queue(affinity_key) WHERE affinity_key IS NOT NULL;
```

### Worker Heartbeat

Workers send heartbeats to the coordinator at a fixed interval.
The heartbeat includes resource utilization so the coordinator can
make informed assignment decisions.

```
Heartbeat Contents
──────────────────

HeartbeatRequest {
  node_id:          "worker-1"
  timestamp:        2026-03-15T10:15:03.421Z
  status:           ACTIVE          // ACTIVE, DRAINING, STOPPING
  active_jobs:      4
  queued_jobs:      12
  max_concurrent:   10
  cpu_percent:      45.2
  memory_used_mb:   890
  memory_total_mb:  4096
  disk_used_gb:     23.4
  disk_total_gb:    100.0
  uptime_seconds:   280800
  plugins_loaded:   ["ftp-collector", "z-score-algorithm", "db-transfer"]
}

HeartbeatResponse {
  ack:              true
  fencing_token:    42            // current leader's token
  config_version:   7             // latest config version
  actions:          []            // optional: DRAIN, SHUTDOWN, RELOAD_CONFIG
}
```

**Heartbeat parameters:**

| Parameter | Default | Description |
|---|---|---|
| `heartbeat_interval` | 5s | Time between heartbeats |
| `heartbeat_timeout` | 15s | Time before a worker is marked SUSPECT |
| `grace_period` | 30s | Time before a SUSPECT worker is marked DEAD |

### Job Leasing

Every job assignment carries a lease. If the worker does not complete
(or renew) the job within the lease period, the coordinator reclaims it.

```
Job Lease Lifecycle
───────────────────

1. Coordinator assigns job to worker:
   lease_expires = now() + lease_duration
   (default lease_duration = 2x expected job duration, minimum 5 minutes)

2. Worker processes job:
   - For long-running jobs, worker sends periodic heartbeats
   - Each heartbeat implicitly renews the lease:
     lease_expires = now() + lease_duration

3. Job completes normally:
   - Worker sends CompleteJob
   - Lease cleared

4. Worker dies mid-job:
   - No heartbeat → lease expires
   - Coordinator's lease reaper (runs every 30s) finds expired leases:
     UPDATE job_queue
     SET status = 'QUEUED', assigned_worker = NULL, retry_count = retry_count + 1
     WHERE status = 'ASSIGNED' AND lease_expires < now()
   - Job reassigned to another worker
```

### Affinity Rules

Affinity rules influence (but do not strictly enforce) which worker
receives a particular job. They are advisory: if the preferred worker
is unavailable, any eligible worker can take the job.

```
Affinity Rule Types
───────────────────

1. PIPELINE_AFFINITY
   - Specified in pipeline metadata: "affinity_group": "data-center-east"
   - Workers tagged with matching group get a scoring bonus
   - Use case: co-locate processing with data source

2. DATA_LOCALITY
   - Jobs prefer workers where source data is locally accessible
   - Automatic: coordinator checks worker capabilities and mount points
   - Use case: avoid network transfer for large files

3. PLUGIN_AFFINITY
   - Jobs prefer workers where the required plugin is already loaded
   - Avoids cold-start overhead of loading plugins
   - Use case: heavy plugins (ML models, JDBC drivers)

4. STICKY_SESSION
   - Jobs with the same affinity_key route to the same worker
   - Enables stateful processing (e.g., session windows, caches)
   - Implemented via consistent hashing on affinity_key
   - Falls back to any worker if preferred worker is unavailable

Configuration example:
  {
    "pipeline_id": "temperature-collection",
    "affinity": {
      "type": "STICKY_SESSION",
      "key": "{{target.equipment_id}}",
      "fallback": "ANY"        // ANY | QUEUE_UNTIL_AVAILABLE
    }
  }
```

### Load Balancing

The coordinator scores eligible workers and assigns the job to the
highest-scoring worker.

```
Worker Scoring Algorithm
────────────────────────

score(worker, job) =
    w1 * cpu_headroom(worker)          // 0.0-1.0, weight: 0.20
  + w2 * memory_headroom(worker)       // 0.0-1.0, weight: 0.20
  + w3 * queue_headroom(worker)        // 0.0-1.0, weight: 0.30
  + w4 * affinity_bonus(worker, job)   // 0.0-1.0, weight: 0.20
  + w5 * locality_bonus(worker, job)   // 0.0-1.0, weight: 0.10

Where:
  cpu_headroom     = 1.0 - (cpu_percent / 100.0)
  memory_headroom  = 1.0 - (memory_used / memory_total)
  queue_headroom   = 1.0 - (active_jobs / max_concurrent)
  affinity_bonus   = 1.0 if affinity matches, 0.0 otherwise
  locality_bonus   = 1.0 if data is local, 0.0 otherwise

Weights are configurable via Hermes.Cluster.WorkDistribution.Weights.

Tie-breaking: lowest active job count wins. If still tied, lowest
node_id (lexicographic) wins for determinism.
```

### Work Stealing

When a worker's local queue is empty and other workers are overloaded,
idle workers can steal queued (not in-progress) jobs.

```
Work Stealing Protocol
──────────────────────

1. Worker completes all active jobs and has nothing queued.

2. Worker sends RequestWork to coordinator with steal_hint=true.

3. Coordinator checks other workers' queues:
   - Find the most-loaded worker (highest queue_depth)
   - If most_loaded.queue_depth > steal_threshold (default: 3):
     a. Select QUEUED jobs from the overloaded worker's queue
     b. Reassign to the idle worker
     c. Notify overloaded worker of reassignment

4. Stolen jobs are always QUEUED, never PROCESSING.
   In-progress jobs are never interrupted.

5. Steal threshold is configurable:
   - Hermes.Cluster.WorkDistribution.StealThreshold = 3
   - Set to 0 to disable work stealing entirely

Benefits:
  - Natural convergence to balanced load
  - No preemptive migration (avoids unnecessary overhead)
  - Workers self-regulate throughput
```

---

## 4. Failure Handling

### Worker Failure

```
Worker Failure Detection and Recovery
─────────────────────────────────────

Timeline:
  T+0s    Worker's last successful heartbeat
  T+5s    First missed heartbeat (expected at T+5s)
  T+10s   Second missed heartbeat
  T+15s   Third missed heartbeat → Coordinator marks worker as SUSPECT
  T+15s   Coordinator logs: "Worker worker-3 missed 3 heartbeats, status=SUSPECT"
  T+15s   Coordinator sends probe (gRPC health check) to worker
  T+45s   Grace period expires (30s since SUSPECT)
           If still no heartbeat and probe failed:
           → Coordinator marks worker as DEAD

Recovery:
  1. Coordinator queries all jobs assigned to the dead worker:
     SELECT * FROM job_queue
     WHERE assigned_worker = 'worker-3'
       AND status IN ('ASSIGNED', 'PROCESSING')

  2. For each orphaned job:
     a. If status = 'ASSIGNED' (not yet started):
        - Clear assigned_worker, set status = 'QUEUED'
        - Job re-enters the assignment queue immediately

     b. If status = 'PROCESSING':
        - Check Content Repository for checkpoint:
          * Checkpoint exists → mark job as QUEUED with checkpoint reference
            (new worker will resume from checkpoint via ExecuteRequest.state_json)
          * No checkpoint → set status = 'QUEUED', increment retry_count
        - If retry_count >= max_retries → route to DLQ

  3. Emit WORKER_FAILED event:
     {
       "event": "WORKER_FAILED",
       "worker_id": "worker-3",
       "orphaned_jobs": 6,
       "reassigned": 5,
       "sent_to_dlq": 1,
       "detected_at": "2026-03-15T10:15:45Z"
     }

  4. Update cluster health metrics
  5. If dead worker reconnects later → treated as a new registration
```

### Coordinator Failure

```
Coordinator Failure Detection and Recovery
──────────────────────────────────────────

Detection:
  - Workers detect coordinator absence when heartbeat responses stop
  - Workers retry coordinator connection with exponential backoff:
    1s → 2s → 4s → 8s → 15s (capped)
  - ZooKeeper/etcd detects leader ephemeral node deletion

Worker Behavior During Coordinator Outage:
  1. Workers continue processing all in-flight jobs (no interruption)
  2. Workers use cached pipeline configurations (immutable snapshots)
  3. Workers write completed results to:
     - Local Content Repository (data)
     - PostgreSQL directly if reachable (status updates)
     - Local WAL if PostgreSQL unreachable
  4. Workers stop accepting NEW work assignments
     (no coordinator to assign, so queue drains naturally)
  5. Workers continue monitoring heartbeats to detect coordinator return

New Coordinator Election:
  1. Coordination backend detects leader loss:
     - PostgreSQL: advisory lock released, next candidate acquires within 5-15s
     - ZooKeeper: ephemeral znode deleted, watcher fires within 1-2s
     - etcd: lease expires within TTL (15s)

  2. New coordinator startup sequence:
     a. Acquire leader lease
     b. Read fencing_token from PostgreSQL, increment it
     c. Load all pipeline definitions from PostgreSQL
     d. Load all active/queued jobs from PostgreSQL
     e. Broadcast COORDINATOR_ELECTED via coordination store

  3. Workers discover new coordinator:
     - ZooKeeper/etcd: watch on /hermes/leader fires
     - PostgreSQL: workers poll coordinator_lease table
     - Workers re-register with new coordinator
     - Workers report:
       * Jobs completed during outage
       * Jobs still in progress
       * Current resource utilization

  4. New coordinator reconciles:
     - Matches worker reports against PostgreSQL state
     - Identifies orphaned jobs (assigned to dead coordinator)
     - Resumes normal work assignment

Key invariant:
  All coordinator state is in PostgreSQL (the coordinator is stateless).
  No data is lost on coordinator failover.
  In-memory caches are rebuilt from the database on startup.
```

### Network Partition

```
Network Partition Handling
──────────────────────────

Hermes follows an AP-leaning strategy (Availability + Partition tolerance)
with eventual consistency on partition heal.

Scenario 1: Workers can reach DB but not coordinator
────────────────────────────────────────────────────
  - Workers continue processing current in-flight jobs
  - Workers write job status updates directly to PostgreSQL
  - No new jobs are assigned (coordinator unavailable)
  - Queued jobs wait until coordinator returns
  - When partition heals:
    → Workers re-register with coordinator
    → Coordinator reads current state from PostgreSQL
    → Normal operation resumes

Scenario 2: Workers can reach coordinator but not DB
────────────────────────────────────────────────────
  - Coordinator assigns jobs from in-memory queue
  - Workers process jobs, buffer results locally (WAL)
  - No new work items are persisted
  - When partition heals:
    → WAL entries replayed to PostgreSQL
    → Duplicate detection via idempotency keys
    → No data loss

Scenario 3: Workers isolated (no coordinator, no DB)
────────────────────────────────────────────────────
  - Workers complete in-flight jobs
  - Results written to local Content Repository + local WAL
  - Monitoring continues if autonomous_monitoring=true
  - New work items queued locally with provisional IDs
  - When partition heals:
    → Full reconciliation protocol (see below)

Reconciliation Protocol (on partition heal):
  1. Worker reconnects to coordinator
  2. Worker uploads local WAL entries
  3. Coordinator replays entries:
     a. Duplicate work items → merge by dedup_key
     b. Provisional IDs → replaced with canonical IDs
     c. Status conflicts → higher-progress state wins
        (COMPLETED > FAILED > PROCESSING > QUEUED > DETECTED)
  4. Worker receives canonical state
  5. Worker purges local provisional data
  6. Normal operation resumes

Split-Brain Prevention:
  - Coordinator self-demotes if it cannot reach >50% of known workers
  - Workers reject commands from coordinators with stale fencing tokens
  - All state mutations in PostgreSQL carry fencing tokens
  - PostgreSQL trigger rejects writes with stale tokens (see Section 2)
```

### Poison Pill Detection

```
Poison Pill Detection and Quarantine
─────────────────────────────────────

A "poison pill" is a job that consistently causes failures regardless
of which worker attempts it. Without detection, a poison pill can
consume all retry capacity and starve healthy jobs.

Detection Criteria:
  - Job has failed >= N times (default: 3)
  - Failures have occurred on >= M different workers (default: 2)
  - Failures occurred within a time window (default: 1 hour)
  - All three conditions must be met

Detection Query:
  SELECT job_id, COUNT(DISTINCT worker_id), COUNT(*) as failure_count
  FROM job_failures
  WHERE failed_at > now() - interval '1 hour'
  GROUP BY job_id
  HAVING COUNT(*) >= 3 AND COUNT(DISTINCT worker_id) >= 2

Response:
  1. Mark job status = 'POISON' in job_queue
  2. Route job to Dead Letter Queue (DLQ):
     INSERT INTO dead_letter_queue (
       job_id, pipeline_id, reason, failure_history_json,
       input_snapshot, created_at
     )
  3. Emit POISON_PILL_DETECTED alert:
     {
       "event": "POISON_PILL_DETECTED",
       "job_id": "abc-123",
       "pipeline_id": "temperature-collection",
       "failure_count": 3,
       "workers_tried": ["worker-1", "worker-2", "worker-3"],
       "errors": ["timeout", "OOM", "timeout"],
       "failed_step": "ALGORITHM"
     }
  4. Never assign this job to any more workers
  5. If poison_rate > 10% of recent jobs in a pipeline:
     → Auto-pause the pipeline
     → Emit PIPELINE_AUTO_PAUSED alert

Recovery:
  - Operator investigates via DLQ Explorer in the web UI
  - Root cause identified (bad data, plugin bug, resource issue)
  - Fix applied (recipe change, plugin update, data correction)
  - Operator replays job from DLQ with corrected configuration
  - If replay succeeds → job exits DLQ
  - If replay fails → remains in DLQ for further investigation
```

---

## 5. Cluster Communication

### Communication Matrix

| From | To | Protocol | Purpose |
|---|---|---|---|
| Coordinator | Worker | gRPC | Job assignment, config updates, shutdown signals |
| Worker | Coordinator | gRPC | Heartbeat, job completion/failure, metrics |
| Worker | Worker | (none) | No direct communication in normal operation |
| Worker | Worker | gRPC | Work stealing (direct, coordinator-mediated) |
| All nodes | PostgreSQL | TCP/SQL | Persistent state, job queue, audit trail |
| All nodes | ZooKeeper/etcd | TCP | Leader election, cluster membership, config distribution |

### Coordinator to Worker Communication

```
Coordinator → Worker (gRPC, push)
─────────────────────────────────

Messages:
  - AssignJob:        New job assignment with payload and lease
  - CancelJob:        Cancel an in-progress job (pipeline deactivated, etc.)
  - UpdateConfig:     Pipeline configuration changed, reload
  - DrainAndStop:     Graceful shutdown: finish current jobs, accept no new ones
  - ShutdownNow:      Immediate shutdown (emergency)

The coordinator maintains a persistent gRPC channel to each registered worker.
If the channel breaks, the coordinator marks the worker as SUSPECT and
begins the failure detection protocol.
```

### Worker to Coordinator Communication

```
Worker → Coordinator (gRPC, periodic + event-driven)
────────────────────────────────────────────────────

Periodic:
  - Heartbeat:        Every 5s, includes resource metrics

Event-driven:
  - Register:         On startup, worker introduces itself
  - RequestWork:      Worker has capacity, requests job assignment
  - CompleteJob:      Job finished successfully, includes result summary
  - FailJob:          Job failed, includes error detail and retry recommendation
  - ReportMetrics:    Aggregated plugin metrics (records/sec, error rates)

Fallback (PostgreSQL):
  If gRPC channel to coordinator is broken, workers write job status
  updates directly to PostgreSQL. The coordinator picks these up on
  its next state-load cycle.
```

### Worker to Worker Communication

```
Worker ↔ Worker (gRPC, exceptional cases only)
──────────────────────────────────────────────

In normal operation, workers never communicate directly.
The coordinator mediates all work distribution.

Exception: Work Stealing
  When the coordinator authorizes a work steal:
  1. Coordinator tells idle worker: "steal from worker-2"
  2. Idle worker opens gRPC channel to worker-2
  3. Idle worker calls StealJobs(count=N)
  4. Worker-2 returns N QUEUED jobs (never PROCESSING)
  5. Idle worker begins processing stolen jobs
  6. Both workers report status to coordinator

This direct channel avoids coordinator becoming a bottleneck
for large-scale rebalancing operations.
```

### gRPC Service Definitions

The cluster communication protocol is defined in
`/protos/hermes_cluster.proto`. See below for the full definition.

```protobuf
// Key services:

service HermesClusterService {
  rpc Register(RegisterRequest) returns (RegisterResponse);
  rpc Heartbeat(HeartbeatRequest) returns (HeartbeatResponse);
  rpc RequestWork(WorkRequest) returns (WorkResponse);
  rpc AssignJob(JobAssignment) returns (AssignmentAck);
  rpc CompleteJob(JobCompletion) returns (CompletionAck);
  rpc FailJob(JobFailure) returns (FailureAck);
  rpc CancelJob(JobCancellation) returns (CancellationAck);
  rpc StealJobs(StealRequest) returns (StealResponse);
  rpc DrainAndStop(DrainRequest) returns (DrainResponse);
  rpc ReportMetrics(NodeMetrics) returns (MetricsAck);
}
```

Full proto file: [`/protos/hermes_cluster.proto`](../protos/hermes_cluster.proto)

---

## 6. Log Viewer (Web UI)

### Design Goals

The Log Viewer provides a unified view of logs across all cluster nodes,
inspired by Apache NiFi's log tab but with modern filtering, search, and
streaming capabilities. It is a core feature of the Hermes web UI, not a
separate Grafana/Kibana deployment.

### Log Viewer Mockup

```
┌──────────────────────────────────────────────────────────────┐
│  Cluster Logs                                    [Live ●]    │
│──────────────────────────────────────────────────────────────│
│                                                               │
│  Filters:                                                     │
│    Node:     [All Nodes      v]  [coordinator-1] [worker-1]  │
│    Level:    [*ALL *ERROR *WARN *INFO  DEBUG  TRACE]         │
│    Pipeline: [All Pipelines  v]                              │
│    Job:      [               ]  (search by job ID)           │
│    Time:     [Last 1 hour    v]                              │
│    Keyword:  [                              ] [Search]       │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │ 10:15:03.421  worker-1   INFO   pipeline/temperature   │  │
│  │   Job #3421 started: Target=Equip-A, 3 files matched   │  │
│  │                                                         │  │
│  │ 10:15:03.523  worker-1   INFO   stage/COLLECT           │  │
│  │   Downloading temp_001.csv (1.2MB) from /data/equip_a/  │  │
│  │                                                         │  │
│  │ 10:15:04.812  worker-2   WARN   pipeline/pressure       │  │
│  │   FTP connection timeout to 192.168.1.100:21            │  │
│  │   Retry 1/3 in 2s (exponential backoff)                 │  │
│  │                                                         │  │
│  │ 10:15:05.100  worker-1   INFO   stage/ALGORITHM         │  │
│  │   Z-Score analysis: 7 anomalies detected                │  │
│  │   Recipe: threshold=3.5, method=modified                │  │
│  │                                                         │  │
│  │ 10:15:06.812  worker-2   ERROR  pipeline/pressure       │  │
│  │   FTP connection failed after 3 retries                 │  │
│  │   Job #2891 -> FAILED -> routed to DLQ                  │  │
│  │   [View Job Detail] [View DLQ Entry]                    │  │
│  │                                                         │  │
│  │ 10:15:07.000  coord-1    INFO   cluster/health          │  │
│  │   Cluster: 3 nodes healthy, 12 jobs active              │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  [Download Logs]  [Export to CSV]            Page 1 of 42    │
└──────────────────────────────────────────────────────────────┘
```

**Features:**

- **Live streaming**: WebSocket connection pushes new log entries in real time.
  Toggle between live mode (auto-scroll) and paused (manual browse).
- **Multi-node aggregation**: Logs from all cluster nodes merged into a single
  time-ordered stream. Each entry labeled with its source node.
- **Filterable**: Node, log level, pipeline, job ID, time range, keyword search.
  Filters apply to both historical and live logs.
- **Clickable context**: Job IDs and pipeline names are links to their detail
  pages. Error entries include links to the DLQ entry if applicable.
- **Export**: Download filtered logs as CSV or plain text. Useful for sharing
  with plugin developers or attaching to incident reports.
- **Syntax highlighting**: Error stack traces rendered with syntax highlighting.
  JSON payloads in detail_json are collapsible and pretty-printed.

### Cluster Dashboard Mockup

```
┌──────────────────────────────────────────────────────────────┐
│  Cluster Overview                                 [Refresh]  │
│──────────────────────────────────────────────────────────────│
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Nodes                                                  │  │
│  │                                                         │  │
│  │  * coordinator-1  LEADER   CPU: 12%  MEM: 340MB         │  │
│  │    Jobs assigned: 0  Uptime: 3d 4h                      │  │
│  │                                                         │  │
│  │  * worker-1       ACTIVE   CPU: 45%  MEM: 890MB         │  │
│  │    Jobs active: 4  Queue: 12  Uptime: 3d 4h             │  │
│  │                                                         │  │
│  │  * worker-2       ACTIVE   CPU: 23%  MEM: 560MB         │  │
│  │    Jobs active: 2  Queue: 8   Uptime: 2d 1h             │  │
│  │                                                         │  │
│  │  o worker-3       DEAD     Last seen: 15min ago         │  │
│  │    [Investigate] [Remove from cluster]                   │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐    │
│  │ Active   │  │ Queued   │  │ Failed   │  │ DLQ      │    │
│  │ Jobs     │  │ Jobs     │  │ (1h)     │  │ Items    │    │
│  │   6      │  │   20     │  │   3      │  │   1      │    │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘    │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  Throughput (last 24h)                                  │  │
│  │                                                         │  │
│  │  Jobs/min  ___                                          │  │
│  │  60 |     /   \        ___                              │  │
│  │  40 |    /     \      /   \    ___                      │  │
│  │  20 |___/       \____/     \__/   \___                  │  │
│  │   0 |_____|_____|_____|_____|_____|____                 │  │
│  │     00:00 04:00 08:00 12:00 16:00 20:00                │  │
│  └────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────┘
```

**Dashboard features:**

- **Node health overview**: Status, role, resource utilization, uptime for each node.
  Color-coded: green (active), yellow (suspect), red (dead).
- **Job summary cards**: Active, queued, failed (rolling 1h window), and DLQ count.
  Each card is clickable to drill into the job list.
- **Throughput chart**: Jobs processed per minute over the last 24 hours.
  Helps identify processing patterns and capacity issues.
- **Actions**: Investigate dead nodes, remove from cluster, drain workers,
  trigger manual rebalance.

### Log Architecture

Each node emits structured logs using Serilog (.NET) with JSON formatting.
The log pipeline evolves across phases:

```
Phase 1: Local Files Only
─────────────────────────
  - Each node writes structured JSON logs to local files
  - Serilog with RollingFile sink
  - No centralized viewing (use SSH + jq for troubleshooting)
  - Log rotation: 100MB per file, 7 days retention

Phase 2: PostgreSQL + Log Viewer UI
────────────────────────────────────
  - All nodes write logs to PostgreSQL cluster_logs table
  - Hermes API queries this table for the Log Viewer UI
  - WebSocket for live streaming (new entries pushed to UI)
  - Simple, no external dependencies
  - Scales to ~10M log entries (use partitioning + retention)

Phase 3: Loki/Elasticsearch + Grafana Integration
──────────────────────────────────────────────────
  - Nodes ship logs to Loki or Elasticsearch via sidecar/agent
  - Hermes UI queries Loki/ES API for the Log Viewer
  - Scales to billions of log entries
  - Optional: Grafana dashboards alongside Hermes-native UI
  - Prometheus metrics for log-based alerting
```

### cluster_logs Table (Phase 2)

```sql
CREATE TABLE cluster_logs (
    id              BIGSERIAL PRIMARY KEY,
    node_id         VARCHAR(100) NOT NULL,
    node_role       VARCHAR(50) NOT NULL,   -- coordinator, worker, edge
    timestamp       TIMESTAMPTZ NOT NULL,
    level           VARCHAR(10) NOT NULL,   -- TRACE, DEBUG, INFO, WARN, ERROR, FATAL
    category        VARCHAR(200),           -- e.g., "pipeline/temperature", "cluster/health"
    pipeline_id     UUID,
    job_id          UUID,
    target_id       VARCHAR(200),
    message         TEXT NOT NULL,
    detail_json     JSONB,                  -- structured context, stack traces, etc.
    trace_id        VARCHAR(64),            -- OpenTelemetry trace ID
    span_id         VARCHAR(32)             -- OpenTelemetry span ID
);

-- Query performance indexes
CREATE INDEX idx_cluster_logs_timestamp ON cluster_logs (timestamp DESC);
CREATE INDEX idx_cluster_logs_level     ON cluster_logs (level) WHERE level IN ('ERROR', 'WARN', 'FATAL');
CREATE INDEX idx_cluster_logs_node      ON cluster_logs (node_id, timestamp DESC);
CREATE INDEX idx_cluster_logs_pipeline  ON cluster_logs (pipeline_id, timestamp DESC) WHERE pipeline_id IS NOT NULL;
CREATE INDEX idx_cluster_logs_job       ON cluster_logs (job_id, timestamp DESC) WHERE job_id IS NOT NULL;
CREATE INDEX idx_cluster_logs_trace     ON cluster_logs (trace_id) WHERE trace_id IS NOT NULL;

-- Full-text search on message content
CREATE INDEX idx_cluster_logs_message_fts ON cluster_logs USING gin(to_tsvector('english', message));

-- Partition by month for performance and easy retention management
CREATE TABLE cluster_logs_y2026m03 PARTITION OF cluster_logs
    FOR VALUES FROM ('2026-03-01') TO ('2026-04-01');
CREATE TABLE cluster_logs_y2026m04 PARTITION OF cluster_logs
    FOR VALUES FROM ('2026-04-01') TO ('2026-05-01');
-- ... partitions created automatically by a scheduled job

-- Retention: drop partitions older than configurable period (default 30 days)
-- Cron job: DROP TABLE IF EXISTS cluster_logs_y2025m12;
```

**Write optimization:**

To avoid overwhelming PostgreSQL with high-volume log writes, nodes batch
log entries and flush periodically:

- Buffer size: 100 entries (configurable)
- Flush interval: 2 seconds (configurable)
- Flush on buffer full OR interval elapsed, whichever comes first
- Use `COPY` for bulk inserts (10x faster than individual INSERTs)
- On PostgreSQL unreachable: fall back to local file, replay on reconnect

---

## 7. Cluster Configuration

### Full Configuration Schema

```jsonc
{
  "Hermes": {
    "Cluster": {
      // Cluster deployment mode.
      // "Standalone": single process, no coordination (Phase 1)
      // "MinimalCluster": 3+ nodes with embedded coordination (Phase 3)
      // "LargeCluster": N nodes with external coordination (Phase 4)
      "Mode": "Standalone",

      // Unique identifier for this node.
      // "auto": generated from hostname + random suffix (e.g., "worker-abc12")
      // Any string: used as-is (must be unique within the cluster)
      "NodeId": "auto",

      // Role assignment for this node.
      // "auto": determined by election (peer mode) or configuration
      // "coordinator": this node runs as coordinator (does not process jobs)
      // "worker": this node processes jobs (does not coordinate)
      // "hybrid": this node does both (Standalone mode only)
      "NodeRole": "auto",

      // Coordination backend configuration.
      "Coordination": {
        // Backend type:
        // "PostgreSQL": advisory locks (Phase 2, simplest)
        // "ZooKeeper": embedded or external (Phase 3-4)
        // "etcd": external only (Phase 4, Kubernetes-friendly)
        "Type": "PostgreSQL",

        "PostgreSQL": {
          // Lock name used for advisory lock (hashed internally)
          "LockName": "hermes-coordinator-leader",
          // Polling interval for candidates checking if leader lock is free
          "PollIntervalSeconds": 5
        },

        "ZooKeeper": {
          // true: Hermes manages a ZooKeeper process on the coordinator node
          // false: connect to an existing external ZooKeeper ensemble
          "Embedded": true,
          // Directory for embedded ZooKeeper data (only if Embedded=true)
          "DataDir": "./data/zookeeper",
          // Client port for ZooKeeper connections
          "ClientPort": 2181,
          // ZooKeeper ensemble servers (only if Embedded=false)
          // Format: ["host1:2181", "host2:2181", "host3:2181"]
          "Servers": [],
          // ZooKeeper session timeout
          "SessionTimeoutMs": 10000,
          // ZooKeeper connection timeout
          "ConnectionTimeoutMs": 5000,
          // Root znode for all Hermes data (namespace isolation)
          "RootPath": "/hermes"
        },

        "etcd": {
          // etcd cluster endpoints
          // Format: ["http://etcd1:2379", "http://etcd2:2379", "http://etcd3:2379"]
          "Endpoints": [],
          // Username for etcd authentication (optional)
          "Username": "",
          // Password (use secret reference: "${secret:etcd-password}")
          "Password": "",
          // TLS certificate paths (optional)
          "CertFile": "",
          "KeyFile": "",
          "CaFile": "",
          // Key prefix for namespace isolation
          "KeyPrefix": "/hermes/"
        }
      },

      // Heartbeat configuration.
      "Heartbeat": {
        // How often workers send heartbeats to the coordinator
        "IntervalSeconds": 5,
        // How many seconds of missed heartbeats before SUSPECT status
        // (should be >= 3 * IntervalSeconds)
        "TimeoutSeconds": 15,
        // How many seconds to wait in SUSPECT before marking DEAD
        "GracePeriodSeconds": 30
      },

      // Work distribution configuration.
      "WorkDistribution": {
        // Maximum concurrent jobs per worker
        "MaxConcurrentJobs": 10,
        // Default job lease duration (seconds).
        // Set to 2x expected maximum job duration.
        "JobLeaseSeconds": 300,
        // Enable idle workers to steal from overloaded workers
        "WorkStealingEnabled": true,
        // Minimum queue depth on a worker before it becomes a steal candidate
        "StealThreshold": 3,
        // Scoring weights for worker selection (must sum to 1.0)
        "Weights": {
          "CpuHeadroom": 0.20,
          "MemoryHeadroom": 0.20,
          "QueueHeadroom": 0.30,
          "AffinityBonus": 0.20,
          "LocalityBonus": 0.10
        }
      },

      // Leader election configuration.
      "Election": {
        // Leader lease TTL (seconds). Must be >= 3 * RenewalIntervalSeconds.
        "LeaseTtlSeconds": 30,
        // How often the leader renews its lease
        "RenewalIntervalSeconds": 10,
        // Maximum time to wait for an election result
        "ElectionTimeoutSeconds": 15,
        // Delay before a demoted leader re-enters candidacy
        "CoolDownSeconds": 10,
        // How often the leader checks it can reach >50% of workers
        "QuorumCheckIntervalSeconds": 15
      },

      // Inter-node gRPC configuration.
      "Grpc": {
        // Port for gRPC server on each node
        "Port": 9090,
        // Enable TLS for inter-node communication
        "TlsEnabled": false,
        "CertFile": "",
        "KeyFile": "",
        "CaFile": "",
        // Maximum message size (bytes). Default 16MB.
        "MaxMessageSize": 16777216,
        // Keep-alive ping interval (seconds)
        "KeepAliveSeconds": 30
      },

      // Poison pill detection configuration.
      "PoisonPill": {
        // Number of failures before a job is considered poison
        "FailureThreshold": 3,
        // Minimum distinct workers that must have failed the job
        "MinDistinctWorkers": 2,
        // Time window for counting failures
        "WindowMinutes": 60,
        // If poison rate exceeds this percentage, auto-pause the pipeline
        "AutoPauseThresholdPercent": 10
      },

      // Logging configuration.
      "Logging": {
        // Where to ship cluster logs:
        // "File": local files only
        // "PostgreSQL": centralized DB table
        // "Loki": ship to Grafana Loki
        // "Elasticsearch": ship to ES
        "Sink": "File",
        // Buffer size before flushing to sink
        "BufferSize": 100,
        // Flush interval (seconds)
        "FlushIntervalSeconds": 2,
        // Retention period (days). Logs older than this are purged.
        "RetentionDays": 30,
        // Maximum log file size before rotation (MB)
        "MaxFileSizeMb": 100,
        // Local file path for log files
        "LogDirectory": "./logs"
      }
    }
  }
}
```

### Environment Variable Overrides

All configuration keys can be overridden via environment variables using
double-underscore notation:

```bash
# Override cluster mode
HERMES__CLUSTER__MODE=MinimalCluster

# Override heartbeat interval
HERMES__CLUSTER__HEARTBEAT__INTERVALSECONDS=10

# Override coordination type
HERMES__CLUSTER__COORDINATION__TYPE=etcd

# Override gRPC port
HERMES__CLUSTER__GRPC__PORT=9091
```

### Configuration Precedence

1. Environment variables (highest priority)
2. `appsettings.{Environment}.json` (environment-specific)
3. `appsettings.json` (base configuration)
4. Code defaults (lowest priority)

---

## 8. Deployment Topologies

### Docker Compose (Development / Small Production)

```yaml
# docker-compose.cluster.yml
version: "3.8"

services:
  coordinator:
    image: hermes:latest
    environment:
      HERMES__CLUSTER__MODE: MinimalCluster
      HERMES__CLUSTER__NODEROLE: coordinator
      HERMES__CLUSTER__NODEID: coordinator-1
      HERMES__CLUSTER__COORDINATION__TYPE: PostgreSQL
    ports:
      - "8000:8000"   # API
      - "9090:9090"   # gRPC
    depends_on:
      - postgres

  worker-1:
    image: hermes:latest
    environment:
      HERMES__CLUSTER__MODE: MinimalCluster
      HERMES__CLUSTER__NODEROLE: worker
      HERMES__CLUSTER__NODEID: worker-1
    ports:
      - "9091:9090"   # gRPC
    depends_on:
      - coordinator
      - postgres

  worker-2:
    image: hermes:latest
    environment:
      HERMES__CLUSTER__MODE: MinimalCluster
      HERMES__CLUSTER__NODEROLE: worker
      HERMES__CLUSTER__NODEID: worker-2
    ports:
      - "9092:9090"   # gRPC
    depends_on:
      - coordinator
      - postgres

  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: hermes
      POSTGRES_USER: hermes
      POSTGRES_PASSWORD: "${POSTGRES_PASSWORD}"
    volumes:
      - pgdata:/var/lib/postgresql/data
    ports:
      - "5432:5432"

volumes:
  pgdata:
```

### Kubernetes (Production)

```yaml
# Helm values.yaml (summary)
hermes:
  cluster:
    mode: LargeCluster
    coordination:
      type: etcd
      etcd:
        endpoints:
          - "http://etcd-0.etcd:2379"
          - "http://etcd-1.etcd:2379"
          - "http://etcd-2.etcd:2379"

  coordinator:
    replicas: 3
    resources:
      requests: { cpu: "500m", memory: "512Mi" }
      limits:   { cpu: "2",    memory: "2Gi"   }

  worker:
    replicas: 5
    autoscaling:
      enabled: true
      minReplicas: 3
      maxReplicas: 20
      targetCPU: 70
    resources:
      requests: { cpu: "1",   memory: "1Gi" }
      limits:   { cpu: "4",   memory: "4Gi" }
    contentRepository:
      storageClass: "gp3"
      size: "100Gi"
```

---

## 9. Security Considerations

### Inter-Node Communication

- **TLS required in production**: All gRPC channels between nodes must use
  mutual TLS (mTLS) in MinimalCluster and LargeCluster modes.
- **Certificate rotation**: Certificates stored in Kubernetes secrets or
  HashiCorp Vault, rotated via operator or sidecar.
- **Node authentication**: Each node presents a client certificate. The
  coordinator validates the certificate against a trusted CA.

### Fencing Token Storage

- Fencing tokens stored in PostgreSQL with `SERIALIZABLE` isolation for
  the increment operation.
- Tokens are 64-bit integers. At one election per second, overflow occurs
  after 292 billion years.

### Secrets in Configuration

- Passwords and tokens in configuration use secret references:
  `"${secret:etcd-password}"` resolved at startup from the Hermes vault.
- Raw secrets never appear in configuration files, logs, or API responses.
- Node heartbeat payloads contain only resource metrics, never business data.

### Network Segmentation

- Coordinator API port (8000) exposed to users (behind load balancer)
- gRPC port (9090) internal only (cluster network, not user-facing)
- PostgreSQL port (5432) internal only
- ZooKeeper/etcd ports (2181/2379) internal only

---

## 10. Migration Path

### Standalone to Minimal Cluster

```
Migration: Standalone → Minimal Cluster
────────────────────────────────────────

Prerequisites:
  - PostgreSQL accessible from all nodes (not localhost)
  - Network connectivity between all nodes on gRPC port
  - Content Repository accessible or migrated to shared storage

Steps:
  1. Stop the standalone Hermes process.
  2. Update configuration:
     Mode: Standalone → MinimalCluster
     Coordination.Type: PostgreSQL (or ZooKeeper)
  3. Deploy coordinator node with updated config.
  4. Deploy 2 worker nodes pointing to same PostgreSQL.
  5. Start coordinator. It acquires the leader lease.
  6. Start workers. They register with the coordinator.
  7. Existing pipelines and jobs are loaded from PostgreSQL.
  8. Workers begin pulling jobs. Cluster is operational.

Rollback:
  - Stop all nodes.
  - Revert configuration to Mode: Standalone.
  - Start single node. All state intact in PostgreSQL.
```

### Minimal Cluster to Large Cluster

```
Migration: Minimal Cluster → Large Cluster
───────────────────────────────────────────

Steps:
  1. Deploy external ZooKeeper/etcd cluster (3 nodes).
  2. Update configuration:
     Mode: MinimalCluster → LargeCluster
     Coordination.Type: ZooKeeper (Embedded: false) or etcd
     Add ZooKeeper/etcd server addresses
  3. Rolling restart: coordinator first, then workers one at a time.
  4. Add coordinator standbys (deploy 2 additional coordinator nodes).
  5. Add workers as needed (horizontal scale-out).
  6. Place load balancer in front of coordinator API endpoints.

No downtime required if performed as a rolling upgrade.
```

---

## Appendix A: Database Schema Summary

Tables introduced by the cluster subsystem:

| Table | Purpose | Phase |
|---|---|---|
| `coordinator_lease` | Leader election lease tracking | Phase 2 |
| `cluster_nodes` | Registered node inventory and status | Phase 3 |
| `job_queue` | Distributed job queue with leasing | Phase 3 |
| `job_failures` | Failure history for poison pill detection | Phase 3 |
| `dead_letter_queue` | Quarantined poison pill jobs | Phase 3 |
| `cluster_logs` | Centralized log aggregation | Phase 2 |
| `cluster_state` | Fencing tokens and cluster metadata | Phase 2 |

## Appendix B: Glossary

| Term | Definition |
|---|---|
| **Coordinator** | Node responsible for work assignment, health monitoring, and API serving |
| **Worker** | Node responsible for executing pipeline jobs |
| **Fencing token** | Monotonically increasing counter that prevents stale leaders from writing |
| **Leader lease** | Time-limited claim on the coordinator role |
| **Poison pill** | A job that consistently fails across multiple workers |
| **DLQ** | Dead Letter Queue: quarantine for poison pill jobs |
| **Work stealing** | Mechanism for idle workers to claim jobs from overloaded workers |
| **Affinity** | Preference for routing certain jobs to certain workers |
| **Content Repository** | Disk-based storage for work item data (see V2_ARCHITECTURE.md Section 3) |
| **WAL** | Write-Ahead Log: local buffer for state changes during partition |
| **Quorum** | Majority (>50%) of known nodes required for safe operation |

---

*This document is part of the Hermes architecture specification. For the
complete system architecture, see [V2_ARCHITECTURE.md](./V2_ARCHITECTURE.md).
For plugin protocol details, see [/protos/hermes_plugin.proto](../protos/hermes_plugin.proto)
and [/protos/hermes_cluster.proto](../protos/hermes_cluster.proto).*
