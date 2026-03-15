# Hermes Development Workflow

> 이 문서는 Hermes의 개발 프로세스와 품질 관리 기준을 정의한다.
> 모든 기능 추가, 버그 수정 시 이 프로세스를 따른다.

---

## 1. Test-Driven Development (TDD)

### 원칙
```
"테스트 없는 기능은 기능이 아니다."
"기존 테스트가 깨지면 새 기능은 머지할 수 없다."
```

### 개발 사이클

```
┌────────────────────────────────────────────────────────┐
│  Step 1: 기존 테스트 확인                               │
│  $ dotnet test                                         │
│  → 전부 통과해야 새 작업 시작                           │
│                                                        │
│  Step 2: 새 기능 테스트 작성 (RED)                      │
│  → 실패하는 테스트부터 작성                             │
│  → 테스트가 "이 기능이 뭘 해야 하는지" 정의             │
│                                                        │
│  Step 3: 최소 구현 (GREEN)                              │
│  → 테스트 통과하는 최소한의 코드                        │
│                                                        │
│  Step 4: 리팩토링 (REFACTOR)                            │
│  → 중복 제거, 네이밍, 구조 개선                         │
│  → 테스트 여전히 통과 확인                              │
│                                                        │
│  Step 5: 전체 테스트 실행                               │
│  $ dotnet test --collect:"XPlat Code Coverage"         │
│  → 기존 테스트 + 새 테스트 전부 통과                    │
│  → 커버리지 하락 없음                                   │
│                                                        │
│  Step 6: 커밋 + PR                                     │
│  → ROADMAP.md 업데이트 (체크박스 체크)                  │
│  → CHANGELOG.md 업데이트                                │
└────────────────────────────────────────────────────────┘
```

### 테스트 레벨

```
Level 1: Unit Tests (가장 많이)
─────────────────────────────
  - Domain 로직 (Recipe 버전 관리, Job 상태 전이, dedup)
  - Application 서비스 (Orchestrator, Dispatcher)
  - 외부 의존성 Mock (DB, Kafka, gRPC)
  - 실행 시간: < 10초

Level 2: Service Tests (핵심 시나리오)
─────────────────────────────────────
  - 서비스 간 통합 (Orchestrator → Dispatcher → Plugin)
  - In-memory DB 사용
  - 실행 시간: < 30초

Level 3: Integration Tests (실제 인프라)
───────────────────────────────────────
  - TestContainers (PostgreSQL, Kafka)
  - 실제 DB + 실제 gRPC 호출
  - E2E 시나리오
  - 실행 시간: < 2분

Level 4: Acceptance Tests (기능 검증)
────────────────────────────────────
  - 차별화 기능별 시나리오
  - Job lifecycle, Reprocessing, Recipe versioning
  - API 엔드포인트 통합 테스트
  - 실행 시간: < 5분
```

### 커버리지 기준

| Phase | 전체 커버리지 | Domain | Application | Infrastructure |
|---|---|---|---|---|
| Phase 1 (MVP) | 80%+ | 90%+ | 85%+ | 70%+ |
| Phase 2 (Prod) | 90%+ | 95%+ | 90%+ | 80%+ |
| Phase 3+ | 90%+ | 95%+ | 90%+ | 85%+ |

---

## 2. 차별화 기능 테스트 시나리오

### Feature 1: Job Tracking (핵심 차별화)
```
test_workitem_full_lifecycle_happy_path
test_workitem_step_failure_records_details
test_workitem_dedup_prevents_duplicate
test_workitem_concurrent_processing
test_workitem_status_transitions_valid_only
test_workitem_event_log_complete_trace
```

### Feature 2: Recipe Management (non-developer 핵심)
```
test_recipe_create_first_version
test_recipe_auto_increment_version
test_recipe_diff_shows_changes
test_recipe_validate_against_schema
test_recipe_reject_invalid_config
test_recipe_rollback_to_previous
test_recipe_snapshot_preserved_at_execution
test_recipe_change_does_not_affect_past_runs
```

### Feature 3: Reprocessing (킬러 피처)
```
test_reprocess_with_same_recipe
test_reprocess_with_updated_recipe
test_reprocess_from_specific_step
test_reprocess_bulk_multiple_items
test_reprocess_audit_trail
test_reprocess_already_completed_item
```

### Feature 4: Back-Pressure (P0)
```
test_backpressure_pauses_monitoring_at_threshold
test_backpressure_resumes_when_queue_drains
test_backpressure_hard_limit_stops_ingestion
test_backpressure_metrics_exposed
```

### Feature 5: Dead Letter Queue (P0)
```
test_dlq_routes_permanent_errors
test_dlq_preserves_error_context
test_dlq_replay_to_pipeline
test_dlq_discard_removes_permanently
```

### Feature 6: Schema Evolution (P0)
```
test_schema_discovery_from_plugin
test_schema_drift_detection
test_schema_change_alerts_operator
test_schema_validation_between_steps
```

---

## 3. PR Checklist

모든 Pull Request는 아래 체크리스트를 포함해야 한다:

```markdown
## PR Checklist

### 필수
- [ ] 기존 테스트 전부 통과 (`dotnet test`)
- [ ] 새 기능에 대한 테스트 코드 포함
- [ ] 커버리지 하락 없음
- [ ] 보안 검사: 하드코딩된 비밀 없음
- [ ] `dotnet format` 통과

### 해당 시
- [ ] ROADMAP.md 체크박스 업데이트
- [ ] CHANGELOG.md 업데이트
- [ ] API 변경 시 Swagger/OpenAPI 문서 확인
- [ ] DB 스키마 변경 시 Migration 포함
- [ ] Proto 변경 시 generated code 업데이트
- [ ] 새 NuGet 패키지 추가 시 라이선스 확인
```

---

## 4. CI/CD Pipeline

```
┌─────────────────────────────────────────────────┐
│  On PR:                                          │
│                                                  │
│  ┌──────────┐  ┌──────────┐  ┌───────────────┐ │
│  │ Build    │→ │ Unit     │→ │ Integration   │ │
│  │ (dotnet  │  │ Tests    │  │ Tests         │ │
│  │  build)  │  │          │  │ (TestContainers│ │
│  └──────────┘  └──────────┘  └───────────────┘ │
│                                      │          │
│                        ┌─────────────┼────────┐ │
│                        │             │        │ │
│                        ▼             ▼        │ │
│                   ┌──────────┐ ┌──────────┐   │ │
│                   │ Coverage │ │ Security │   │ │
│                   │ Check    │ │ Scan     │   │ │
│                   │ (≥80%)   │ │          │   │ │
│                   └──────────┘ └──────────┘   │ │
│                                               │ │
│  All pass → ✅ Merge allowed                  │ │
└───────────────────────────────────────────────┘ │
                                                  │
┌─────────────────────────────────────────────────┐
│  On Merge to main:                               │
│                                                  │
│  Build → Test → Docker Build → Push to Registry  │
│                                    │             │
│                                    ▼             │
│                              GitHub Release      │
│                              + NuGet Publish     │
│                              (Hermes.Plugins.Sdk)│
└──────────────────────────────────────────────────┘
```

---

## 5. 릴리스 관리

### Semantic Versioning
```
v{major}.{minor}.{patch}

major: 호환성 깨지는 변경 (API 변경, proto 변경)
minor: 새 기능 추가 (하위 호환)
patch: 버그 수정
```

### 릴리스 체크리스트
```
1. develop → release/x.y.z 브랜치 생성
2. 전체 테스트 통과 확인
3. CHANGELOG.md 최종 업데이트
4. ROADMAP.md Phase 항목 체크
5. 버전 번호 업데이트 (*.csproj)
6. Docker 이미지 빌드 + 태깅
7. GitHub Release 생성 (release notes)
8. NuGet 패키지 발행 (Hermes.Plugins.Sdk)
9. release → main 머지
10. main → develop 역머지
```
