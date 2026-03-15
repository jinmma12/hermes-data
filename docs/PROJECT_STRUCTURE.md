# Hermes - Project Structure (Transitioning Architecture)

> Current state: Python (reference API) + .NET (target API/Engine) + React (Frontend)
>
> V2 direction: ASP.NET Core becomes the public API, .NET remains the engine,
> and Python shifts toward reference logic, plugin support, and migration parity.

---

## 1. Polyglot Architecture

```
Current:
React (Frontend) <--> Python FastAPI (reference API) <--> .NET Core Engine

Target:
React (Frontend) <--> ASP.NET Core API <--> .NET Workers / Engine
                                            | gRPC
                                      Algorithm Containers
```

### Python Reference Layer (`backend/`)

The Python layer currently contains the richest reference implementation and test corpus.
It should be treated as a migration source and compatibility reference:

- existing REST API endpoints and schemas
- existing WebSocket/event forwarding logic
- existing domain behavior and pytest scenarios
- current PostgreSQL async data access
- Tests: pytest (API tests, schema validation, auth tests)

This layer should shrink over time as route parity moves into ASP.NET Core.

### .NET API Layer (`engine/src/Hermes.Api/`)

The ASP.NET Core layer is the target public API surface for V2:

- REST endpoints for the React frontend
- health and contract-tested API surfaces
- OpenAPI/Swagger and realtime endpoints
- provider-aware data access for PostgreSQL and SQL Server
- API contract tests via `WebApplicationFactory`

### .NET Core Engine (`engine/`)

The .NET layer is the **processing powerhouse**. It owns all stateful,
long-running, and performance-critical logic:

- Monitoring Engine (File/FTP/API/DB/Kafka watchers)
- Processing Orchestrator (stage execution, CQRS)
- Execution Dispatcher (gRPC to algorithm containers)
- Content Repository (disk-based storage with claim management)
- Back-throughput and flow control
- Dead Letter Queue (DLQ) with retry policies
- Circuit Breaker for external dependencies
- Schema Registry (version tracking, compatibility checks)
- Cluster coordination (ZooKeeper-based leader election)
- Prometheus metrics endpoint
- Tests: xUnit (collection scenarios, failure handling, resilience)

### React Frontend (`webapp/`)

- Pipeline Designer (React Flow / @xyflow/react)
- Recipe Editor (react-jsonschema-form / @rjsf)
- Job creation wizard
- Monitor Dashboard (real-time pipeline status)
- Job Explorer with TraceEvent timeline
- Cluster log viewer (multi-node)

### Algorithm Containers (Docker)

- Connected via gRPC (`hermes_plugin.proto` / `vessel_plugin.proto`)
- Any language (Python, R, C++, Java, etc.)
- Isolated execution with resource limits
- SDK available as NuGet package (`Hermes.Plugins.Sdk`)

---

## 2. Directory Structure

```
hermes-data/
├── backend/                        <- Python FastAPI (Web API)
│   ├── vessel/                     <- Python package
│   │   ├── api/                    <- REST endpoints (routes, schemas)
│   │   │   └── schemas/            <- Pydantic DTOs
│   │   ├── domain/models/          <- SQLAlchemy models (DB read/write)
│   │   ├── core/                   <- Engine client, runtime, plugin loader
│   │   └── main.py                 <- FastAPI app entrypoint
│   ├── tests/                      <- pytest
│   │   ├── test_*.py               <- API tests, schema validation
│   │   └── collection/             <- Collection scenario tests (Python mocks)
│   ├── pyproject.toml
│   └── Dockerfile
│
├── engine/                         <- .NET Core Engine (NEW)
│   ├── src/
│   │   ├── Hermes.Domain/          <- Entities, Value Objects, Interfaces
│   │   │                              Zero external dependencies
│   │   ├── Hermes.Application/     <- Services, CQRS handlers, DTOs
│   │   │                              Orchestrator, Dispatcher logic
│   │   ├── Hermes.Infrastructure/  <- EF Core, Kafka, gRPC clients,
│   │   │                              NiFi bridge, Content Repository
│   │   ├── Hermes.Engine/          <- Worker host (monitoring loop,
│   │   │                              processing pipeline, DI root)
│   │   └── Hermes.Plugins.Sdk/     <- NuGet SDK for plugin authors
│   ├── tests/
│   │   ├── Hermes.Domain.Tests/        <- Entity logic, state transitions
│   │   ├── Hermes.Engine.Tests/        <- Collection, failure, resilience (xUnit)
│   │   └── Hermes.IntegrationTests/    <- Full pipeline with TestContainers
│   ├── Hermes.sln
│   └── Dockerfile
│
├── webapp/                         <- React Frontend
│   ├── src/
│   │   ├── pages/                  <- Route pages (Pipeline, Job, Monitor)
│   │   ├── components/             <- Reusable UI components
│   │   ├── hooks/                  <- Custom React hooks
│   │   └── api/                    <- API client (fetch wrappers)
│   ├── package.json
│   └── Dockerfile
│
├── plugins/                        <- Built-in algorithm plugins
│   ├── collectors/                 <- REST API, File Watcher, DB Query, Kafka
│   ├── algorithms/                 <- JSON Transform, Passthrough, etc.
│   └── transfers/                  <- File Transfer, REST API Transfer, etc.
│
├── protos/                         <- gRPC definitions (shared)
│   ├── vessel_plugin.proto         <- Plugin protocol (container <-> engine)
│   ├── hermes_cluster.proto        <- Cluster comms (coordinator <-> worker)
│   └── hermes_bridge.proto         <- Python <-> .NET bridge (NEW)
│
├── docs/                           <- All design documents
│   ├── ARCHITECTURE.md             <- Core design spec
│   ├── DOTNET_SOLUTION_DESIGN.md   <- .NET Clean Architecture blueprint
│   ├── CLUSTER_DESIGN.md           <- Distributed cluster design
│   ├── DATA_COLLECTION_DESIGN.md   <- Collection patterns
│   ├── DOMAIN_INTERFACES.md        <- Domain model interfaces
│   ├── MESSAGE_AND_TRACE.md        <- Message format and tracing
│   ├── NIFI_INTEGRATION.md         <- Optional NiFi backend
│   ├── TEST_STRATEGY.md            <- Testing approach
│   ├── DEVELOPMENT_WORKFLOW.md     <- TDD workflow and quality gates
│   ├── V2_ARCHITECTURE.md          <- V2 evolution plan
│   └── PROJECT_STRUCTURE.md        <- This file
│
├── docker/
│   └── docker-compose.yml          <- Full stack (Python + .NET + React + PG + Kafka)
│
├── CLAUDE.md                       <- Project conventions for AI assistants
├── README.md
├── ROADMAP.md
└── LICENSE
```

---

## 3. Communication Between Layers

### Python <-> .NET Bridge (gRPC)

The bridge protocol (`hermes_bridge.proto`) defines how the Python Web API
delegates engine operations to the .NET Core Engine:

```
Python FastAPI                          .NET Engine
--------------                          ----------

POST /api/v1/pipelines/{id}/activate
  -> calls gRPC: EngineService.ActivatePipeline(id)
      -> .NET starts MonitoringEngine for that pipeline

GET /api/v1/jobs
  -> reads PostgreSQL directly (fast reads, no gRPC hop)

GET /api/v1/jobs/{id}
  -> reads PostgreSQL directly

POST /api/v1/jobs/{id}/reprocess
  -> calls gRPC: EngineService.ReprocessJob(id, recipe)
      -> .NET orchestrates reprocessing through stages

POST /api/v1/pipelines/{id}/deactivate
  -> calls gRPC: EngineService.DeactivatePipeline(id)
      -> .NET gracefully stops monitoring and drains jobs

POST /api/v1/pipelines/{id}/test-connection
  -> calls gRPC: EngineService.TestConnection(config)
      -> .NET validates source connectivity

WebSocket /api/v1/ws/pipeline/{id}/events
  -> .NET pushes events via gRPC stream (StreamEvents)
  -> Python forwards to WebSocket clients in real-time
```

### Design Decisions

| Decision | Rationale |
|---|---|
| Python reads DB directly for GET queries | Avoids gRPC round-trip for simple reads; keeps UI snappy |
| .NET owns all writes during processing | Single writer prevents race conditions on job state |
| Python forwards create/update to .NET for engine entities | Ensures .NET domain validation runs |
| Events flow .NET -> Python -> WebSocket | .NET is the source of truth for processing events |

### `hermes_bridge.proto`

Defined in `/protos/hermes_bridge.proto`. Key services:

```protobuf
service HermesEngineService {
  // Pipeline lifecycle
  rpc ActivatePipeline(ActivateRequest) returns (ActivateResponse);
  rpc DeactivatePipeline(DeactivateRequest) returns (DeactivateResponse);
  rpc GetPipelineStatus(StatusRequest) returns (PipelineStatusResponse);

  // Job management
  rpc ReprocessJob(ReprocessRequest) returns (ReprocessResponse);
  rpc BulkReprocessJobs(BulkReprocessRequest) returns (BulkReprocessResponse);
  rpc CancelJob(CancelRequest) returns (CancelResponse);

  // Monitoring
  rpc StreamEvents(EventStreamRequest) returns (stream EngineEvent);
  rpc GetEngineHealth(HealthRequest) returns (EngineHealthResponse);
  rpc GetMetrics(MetricsRequest) returns (MetricsResponse);

  // Testing
  rpc TestConnection(TestConnectionRequest) returns (TestConnectionResponse);
  rpc PreviewData(PreviewRequest) returns (PreviewResponse);
}
```

---

## 4. Which Tests Go Where

| Test Category | Language | Location | Why |
|---|---|---|---|
| API endpoint tests | .NET | `engine/tests/Hermes.Api.Tests/` | Target API contract for the React frontend |
| FastAPI parity/reference tests | Python | `backend/tests/` | Existing behavior reference during migration |
| Recipe CRUD tests | Python | `backend/tests/` | DB operations via SQLAlchemy (Python owns the read path) |
| Schema validation | Python | `backend/tests/` | Pydantic DTO validation |
| Auth / CORS tests | Python | `backend/tests/` | Middleware lives in Python layer |
| Collection scenarios | C# / xUnit | `engine/tests/` | MonitoringEngine logic lives in .NET |
| Failure handling | C# / xUnit | `engine/tests/` | Retry, circuit breaker, DLQ in .NET |
| Back-throughput | C# / xUnit | `engine/tests/` | Flow control is an engine concern |
| Dead Letter Queue | C# / xUnit | `engine/tests/` | DLQ management in .NET |
| Orchestration | C# / xUnit | `engine/tests/` | Stage execution, state transitions |
| Plugin protocol | Both | both | gRPC contract tests (proto compatibility) |
| E2E scenarios | Both | both | Transition period until FastAPI is retired |

### Test Naming Conventions

- **Python**: `test_<feature>.py` with pytest, e.g. `test_pipeline_crud.py`
- **.NET**: `<Feature>Tests.cs` with xUnit, e.g. `CollectionScenarioTests.cs`

---

## 5. Development Workflow

### Prerequisites

- Python 3.12+
- .NET 8 SDK
- Node.js 20+ (for webapp)
- Docker & Docker Compose
- PostgreSQL 15 (or use Docker)

### Running Each Component Locally

#### 1. Python Web API (`backend/`)

```bash
cd backend
cp .env.example .env          # Configure DB, gRPC endpoint
pip install -e ".[dev]"
uvicorn vessel.main:app --reload --port 8000
```

#### 2. .NET Core Engine (`engine/`)

```bash
cd engine
dotnet restore
dotnet run --project src/Hermes.Engine
# Engine starts gRPC server on port 5100 (default)
```

#### 3. React Frontend (`webapp/`)

```bash
cd webapp
npm install
npm run dev
# Dev server on port 3000, proxies API to localhost:8000
```

#### 4. Full Stack (Docker Compose)

```bash
docker compose up -d
# Python API:    http://localhost:8000
# API docs:      http://localhost:8000/docs
# Web UI:        http://localhost:3000
# .NET Engine:   grpc://localhost:5100
# PostgreSQL:    localhost:5432
# Kafka:         localhost:9092
# Prometheus:    http://localhost:9090
```

### Environment Variables

| Variable | Component | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | Python | `postgresql+asyncpg://...` | Python reference PostgreSQL connection string |
| `HERMES_ENGINE_GRPC_URL` | Python | `localhost:5100` | .NET Engine gRPC endpoint |
| `Database__Provider` | .NET | `postgres` | `postgres` or `sqlserver` |
| `Database__Schema` | .NET | `hermes` | Dedicated Hermes schema/namespace |
| `Database__ConnectionStrings__Postgres` | .NET | `Host=localhost;...` | PostgreSQL connection |
| `Database__ConnectionStrings__SqlServer` | .NET | `Server=localhost;...` | SQL Server connection |
| `GrpcServer__Port` | .NET | `5100` | gRPC listen port |
| `Kafka__BootstrapServers` | .NET | `localhost:9092` | Kafka broker address |
| `ContentRepository__BasePath` | .NET | `./content-repo` | Disk storage for content claims |
| `VITE_API_URL` | React | `http://localhost:8000` | Backend API base URL |

## 6. Database Support

Hermes V2 should support both PostgreSQL and SQL Server.

- default schema: `hermes`
- Docker DB is optional
- users with existing DB infrastructure should be able to connect directly
- provider-specific bootstrap scripts must be kept in sync with application models
- the `.NET` prototype exposes `/api/v1/system/database` and `/api/v1/system/database/bootstrap-script` for install-time configuration and schema bootstrap retrieval

Bootstrap assets:

- `database/postgresql/init_query.sql`
- `database/sqlserver/init_query.sql`

### Running Tests

```bash
# Python tests
cd backend && pytest -v

# .NET tests
cd engine && dotnet test

# Frontend tests
cd webapp && npm test

# Full test suite (CI)
docker compose -f docker-compose.test.yml up --abort-on-container-exit
```

### Code Quality

```bash
# Python
cd backend && ruff check . && mypy vessel/

# .NET
cd engine && dotnet format --verify-no-changes

# Frontend
cd webapp && npm run lint && npm run typecheck
```
