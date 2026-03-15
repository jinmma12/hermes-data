# Hermes Stream Roadmap

> Last updated: 2026-03-15
> Status: Phase 0 (Design) → Phase 1 (MVP) 진입 준비

---

## Vision

**"The .NET NiFi"** — Enterprise-grade, lightweight data processing platform.

NiFi의 강점(per-item tracking, provenance)을 가져가되,
.NET 기반으로 가볍고, non-developer가 Web UI에서 운영 가능한 플랫폼.

---

## Hermes의 핵심 강점 (Differentiators)

### 1. Job-Level Tracking
> 모든 데이터 아이템의 수집→분석→전송 전 과정을 개별 추적.
> NiFi 외에는 아무도 하지 않는 기능.

### 2. Recipe Management for Non-Developers
> SW 개발자가 아닌 운영자가 Web UI에서 수집 설정, 알고리즘 파라미터를 변경.
> JSON Schema → 자동 폼 생성. 버전 관리 + diff/compare.

### 3. First-Class Reprocessing
> 실패 건 단건/일괄 재처리. 특정 Step부터 재시작. 최신 Recipe 적용 선택.
> 경쟁 제품 중 이걸 제대로 하는 곳이 없음.

### 4. NiFi-Friendly, Not NiFi-Dependent
> 기존 NiFi 레거시를 그대로 활용하면서 Hermes의 UI/추적/재처리 레이어를 씌울 수 있음.
> NiFi 없이도 독립 실행 가능.

### 5. Plugin Protocol (gRPC, Language-Agnostic)
> 알고리즘은 Docker container로 격리. gRPC/Kafka로 통신.
> Python, R, C++, Java 등 어떤 언어로든 플러그인 작성 가능.

### 6. Disk-Based Content Repository
> NiFi처럼 대용량 데이터를 디스크 기반으로 처리.
> 메모리 부족 없이 GB 단위 데이터 파이프라인 운영.

---

## Phase 0: Design (Current) ✅

| Item | Status | 산출물 |
|---|---|---|
| 전체 아키텍처 설계 | ✅ Done | `docs/ARCHITECTURE.md` |
| 데이터 수집 설계 | ✅ Done | `docs/DATA_COLLECTION_DESIGN.md` |
| NiFi 연동 설계 | ✅ Done | `docs/NIFI_INTEGRATION.md` |
| 테스트 전략 | ✅ Done | `docs/TEST_STRATEGY.md` |
| DB 스키마 | ✅ Done | `backend/database/schema.sql` |
| Python 프로토타입 | ✅ Done | `backend/`, `webapp/`, `plugins/` |
| 벤치마크 Gap 분석 | ✅ Done | 17개 Gap 식별 (P0~P3) |
| .NET Solution 설계 | ✅ Done | `docs/DOTNET_SOLUTION_DESIGN.md` |
| gRPC Protocol 설계 | ✅ Done | `protos/hermes_plugin.proto`, `hermes_bridge.proto`, `hermes_cluster.proto` |
| Domain Interface 설계 | ✅ Done | `docs/DOMAIN_INTERFACES.md` |
| V2 아키텍처 (분산/디스크) | 🔄 In Progress | `docs/V2_ARCHITECTURE.md` |

---

## Phase 1: MVP (3 months)

> 목표: 단일 노드에서 동작하는 핵심 기능. 사내 PoC 가능 수준.

### Core Pipeline
- [x] ASP.NET Core 8 Web API 프로젝트 셋업
- [x] EF Core + PostgreSQL (Code First Migrations)
- [x] Definition CRUD (Collector, Algorithm, Transfer + Versions)
- [x] Instance CRUD + Recipe 버전 관리
- [x] Pipeline CRUD + Step 순서 관리
- [x] Pipeline Activation/Deactivation

### Monitoring Engine
- [x] File Watcher (FileSystemWatcher + polling fallback)
- [x] API Poller (HttpClient + Polly)
- [ ] Kafka Consumer (Confluent.Kafka)
- [x] Condition Evaluator + dedup

### Processing Engine
- [x] Job 생성 + 상태 관리
- [x] Processing Orchestrator (순차 Step 실행)
- [x] Execution Snapshot 캡처
- [x] Event Log 기록
- [x] Reprocess (단건 + 일괄 + 특정 Step부터)

### Plugin System
- [x] gRPC Plugin Protocol v2 (hermes_plugin.proto)
- [ ] Hermes.Plugins.Sdk NuGet 패키지
- [x] Plugin 프로세스 관리 (spawn, health, kill)
- [ ] 빌트인 플러그인: REST API Collector, File Watcher, Passthrough, File Output

### Web UI
- [x] React + TypeScript + Vite 셋업
- [x] Pipeline Designer (React Flow)
- [x] Recipe Editor (react-jsonschema-form)
- [x] Monitor Dashboard
- [x] Job Explorer + Detail
- [x] Definition Manager

### Infrastructure
- [x] Docker Compose (API + Worker + PostgreSQL)
- [x] Health Check endpoints
- [x] Structured logging (Serilog)
- [x] appsettings.json 구조

### Testing
- [x] xUnit 프로젝트 셋업
- [x] Domain 단위 테스트 (Recipe, Job lifecycle)
- [ ] Application 서비스 테스트
- [ ] API 통합 테스트 (WebApplicationFactory)
- [ ] TestContainers (PostgreSQL)
- [ ] CI: GitHub Actions (build + test on PR)

### Milestone Criteria
```
✅ docker compose up → API + Worker + UI 동작
✅ Web UI에서 Pipeline 생성 → 수집 설정 → 활성화
✅ 파일 생성 시 Job 자동 생성 + 처리
✅ 실패 건 Web UI에서 재처리
✅ Recipe 변경 → 새 버전 생성 → diff 확인
✅ 전체 테스트 통과 (80%+ 커버리지)
```

---

## Phase 2: Production-Ready (+2 months)

> 목표: 실제 운영 환경 투입 가능. P0/P1 Gap 전부 해결.

### P0 Gaps
- [ ] Back-pressure (큐 깊이 제한 + 모니터링 일시정지)
- [ ] Dead Letter Queue (실패 데이터 격리 + DLQ Explorer UI)
- [ ] Schema Discovery & Evolution (drift 감지 + 알림)

### P1 Gaps
- [ ] Content Repository (디스크 기반 대용량 처리)
- [ ] Exactly-Once (Step별 checkpoint + 크래시 복구)
- [ ] Graceful Shutdown (drain mode + orphan 복구)
- [ ] Observability (Prometheus metrics + Grafana 대시보드)
- [ ] Retry 정교화 (exponential backoff + jitter + Polly)

### NiFi Integration
- [ ] NiFi REST API Client
- [ ] NiFi-Hermes Bridge (Process Group ↔ Pipeline 동기화)
- [ ] NiFi Provenance → Job 추적
- [ ] Recipe → NiFi Parameter Context 푸시

### Testing
- [ ] E2E 시나리오 테스트 (파일 수집 → 분석 → 전송 전체 흐름)
- [ ] Back-pressure 부하 테스트
- [ ] DLQ 시나리오 테스트
- [ ] NiFi 연동 테스트 (Mock NiFi)
- [ ] 90%+ 커버리지

### Milestone Criteria
```
✅ 1만 건/시간 처리 안정적 동작
✅ 대용량 파일 (100MB+) 처리 가능
✅ 외부 API 장애 시 Circuit Breaker 작동
✅ 크래시 후 재시작 → 데이터 유실 없음
✅ Grafana 대시보드에서 전체 상태 모니터링
✅ NiFi 기존 Flow를 Hermes에서 관리 가능
```

---

## Phase 3: Enterprise (+3 months)

> 목표: 다중 노드 운영 + 기업 기능. 상용화 기반.

### Distributed Processing
- [ ] Worker 노드 수평 확장
- [ ] Coordinator-Worker 아키텍처
- [ ] 작업 분배 + 리밸런싱
- [ ] Worker 장애 → 자동 재할당
- [ ] Split-brain 방지

### P2 Gaps
- [ ] Authentication (JWT/OIDC)
- [ ] RBAC (Viewer/Operator/Admin)
- [ ] Audit Log (사용자 행동 추적)
- [ ] Data Preview (파이프라인 실행 전 미리보기)
- [ ] Content-Based Routing (조건부 분기)
- [ ] Rate Limiting
- [ ] Circuit Breaker

### Deployment
- [ ] Kubernetes Helm Chart
- [ ] K8s Operator (CRD for Pipeline)
- [ ] Grafana Dashboard 템플릿 제공
- [ ] 운영 가이드 문서

### Testing
- [ ] 분산 환경 테스트 (multi-node)
- [ ] 장애 주입 테스트 (Chaos Engineering)
- [ ] 성능 벤치마크 (NiFi/Airbyte 대비)
- [ ] 95%+ 커버리지

### Milestone Criteria
```
✅ 3+ Worker 노드 클러스터 안정 운영
✅ Worker 1대 kill → 자동 복구 (데이터 유실 없음)
✅ RBAC: Operator는 Recipe만, Admin은 Pipeline도 관리
✅ Helm chart로 K8s 배포 5분 내 완료
```

---

## Phase 4: Exit-Ready (+3 months)

> 목표: 인수/투자 유치 가능한 상용 제품 수준.

### Enterprise Features
- [ ] Multi-tenancy (Workspace 격리)
- [ ] Plugin Marketplace (내부/외부)
- [ ] Pipeline Git Integration (version control)
- [ ] Environment Promotion (dev → staging → prod)
- [ ] SLA Monitoring + Alerting
- [ ] Cost Tracking (compute, storage)
- [ ] Custom Dashboard Builder

### Compliance
- [ ] SOC2 readiness
- [ ] GDPR 지원 (데이터 삭제 요청)
- [ ] Data Retention Policy
- [ ] Encryption at Rest

### Ecosystem
- [ ] Plugin SDK 문서 사이트
- [ ] Hermes Hub (플러그인 공유)
- [ ] Terraform Provider
- [ ] CLI 도구

### Community
- [ ] Documentation site (Docusaurus)
- [ ] Getting Started 튜토리얼
- [ ] Video demos
- [ ] Discord/Slack community

### Milestone Criteria
```
✅ 10+ 기업에서 프로덕션 사용
✅ 50+ 커뮤니티 플러그인
✅ 엔터프라이즈 고객 3+ (유료 지원)
✅ 기술 블로그 / 컨퍼런스 발표
```

---

## Development Workflow

### Branch Strategy
```
main          ← 안정 릴리스
├── develop   ← 개발 통합
│   ├── feature/xxx  ← 기능 개발
│   ├── fix/xxx      ← 버그 수정
│   └── test/xxx     ← 테스트 추가
└── release/x.y.z    ← 릴리스 준비
```

### PR Checklist (모든 PR 필수)
```
□ 기존 테스트 전부 통과 (dotnet test)
□ 새 기능에 대한 테스트 코드 포함
□ 커버리지 하락 없음
□ lint 통과 (dotnet format)
□ 보안 검사 통과 (no hardcoded secrets)
□ ROADMAP.md 업데이트 (해당 시)
□ CHANGELOG.md 업데이트
```

### Test-Driven Development
```
1. 새 기능 시작 전:
   → 기존 테스트 전부 통과 확인 (dotnet test)

2. 새 기능 개발:
   → 테스트 먼저 작성 (Red)
   → 구현 (Green)
   → 리팩토링 (Refactor)

3. PR 전:
   → 전체 테스트 통과
   → 커버리지 리포트 확인
   → 통합 테스트 통과 (TestContainers)
```

### CI/CD Pipeline
```
PR → Build → Unit Tests → Integration Tests → Coverage Check → Security Scan
                                                                      │
                                                                      ▼
                                                              Merge to develop
                                                                      │
                                                                      ▼
                                                         Release → Docker Build
                                                                      │
                                                                      ▼
                                                              Push to Registry
```

---

## Changelog

### v0.1.0 (2026-03-15) — Phase 0
- Initial project setup
- Python prototype (FastAPI + React)
- Architecture design documents
- DB schema (19 tables)
- Plugin system (6 built-in plugins)
- 90 test scenarios
- NiFi integration design
- Benchmark gap analysis (17 gaps identified)
- .NET solution design (in progress)
