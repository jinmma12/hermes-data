# Hermes — Message & Trace Design

> Hermes(선박)이 운반하는 Message(화물)와 그 항해 기록 Trace(= Provenance).
> NiFi FlowFile + Provenance의 Hermes 버전.

---

## 1. 왜 Message가 필요한가

### 현재 문제

```
Job = 추적 단위 (OK)
하지만 Step 사이를 "데이터"가 어떻게 이동하는지 정의가 없음

Step A output → ??? → Step B input
  - 메모리? 파일? Kafka? gRPC?
  - 대용량이면?
  - 실패하면 원본 데이터는?
  - 재처리 시 원본 데이터 어디서?
```

### Message가 해결하는 것

```
Message = 데이터 이동의 표준 단위

Step A → [Message] → Step B → [Message'] → Step C

- Message는 데이터를 직접 들고 다니지 않음 (참조만)
- 실제 데이터는 ContentRepository(디스크)에 저장
- 각 Step에서의 변환은 새 Message 생성 (불변)
- 모든 이동/변환이 Trace Event로 기록
```

---

## 2. Core Concepts

```
┌─────────────────────────────────────────────────────────────┐
│                                                              │
│  Message   = Payload(참조) + Manifest(메타데이터)              │
│  Trace  = Message의 전체 이동/변환 기록 (Provenance)          │
│  Content = 실제 데이터 (디스크, 불변, SHA-256 해시)          │
│                                                              │
│  관계:                                                       │
│  Job 1 ──── 1..N Message (Step마다 새 Message 생성 가능)    │
│  Message 1 ──── 1 ContentClaim (데이터 참조)                   │
│  Message 1 ──── 1..N TraceEvent (이동 기록)                   │
│                                                              │
│  ContentClaim N ←── 1 Physical File (같은 파일 중복 참조)    │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

### 2.1 Message

```csharp
public record Message
{
    public Guid Id { get; init; }
    public Guid JobId { get; init; }
    public Guid? ParentMessageId { get; init; }  // CLONE/SPLIT 시 원본

    // Payload — 실제 데이터 참조 (데이터 자체가 아님!)
    public string PayloadRef { get; init; }      // "content://sha256:aabb1122"
    public string ContentType { get; init; }     // "text/csv"
    public long ContentSize { get; init; }       // bytes
    public string? ContentEncoding { get; init; } // "utf-8", "gzip"

    // Manifest — 메타데이터 (Step을 거치며 진화)
    public Dictionary<string, object> Manifest { get; init; }

    // State
    public MessageStatus Status { get; init; }     // ACTIVE, COMPLETED, DROPPED
    public DateTimeOffset CreatedAt { get; init; }
}
```

### 2.2 ContentClaim

```csharp
public record ContentClaim
{
    public Guid Id { get; init; }
    public string ContentHash { get; init; }     // SHA-256
    public long ContentSize { get; init; }
    public string ContentType { get; init; }
    public string StoragePath { get; init; }     // 디스크 경로
    public int RefCount { get; init; }           // 참조 카운트
    public DateTimeOffset CreatedAt { get; init; }
    public DateTimeOffset? LastAccessed { get; init; }
}
```

### 2.3 TraceEvent (Provenance)

```csharp
public record TraceEvent
{
    public Guid Id { get; init; }
    public Guid MessageId { get; init; }
    public Guid JobId { get; init; }
    public Guid? ExecutionId { get; init; }

    // Event
    public TraceEventType EventType { get; init; }
    public Guid? StepId { get; init; }
    public string? StageType { get; init; }
    public string? PluginRef { get; init; }
    public string? WorkerNode { get; init; }

    // Payload 변화
    public string? PreviousPayloadRef { get; init; }
    public string CurrentPayloadRef { get; init; }
    public long PayloadSizeBytes { get; init; }

    // Manifest 변화
    public Dictionary<string, object>? ManifestBefore { get; init; }
    public Dictionary<string, object>? ManifestAfter { get; init; }
    public Dictionary<string, object>? ManifestChanges { get; init; }

    // Recipe (실행 당시 설정)
    public Dictionary<string, object>? RecipeSnapshot { get; init; }

    // Metrics
    public int? DurationMs { get; init; }
    public int? RecordsProcessed { get; init; }
    public int? RecordsOutput { get; init; }

    // Error
    public string? ErrorCode { get; init; }
    public string? ErrorMessage { get; init; }
    public bool? IsRetryable { get; init; }

    // Time
    public DateTimeOffset Timestamp { get; init; }
}

public enum TraceEventType
{
    CREATED,     // Message 최초 생성 (모니터링에서 감지)
    RECEIVED,    // Step이 Message를 수신
    MODIFIED,    // Step이 Message 데이터를 변환 (새 Payload 생성)
    ROUTED,      // 조건부 분기로 라우팅됨
    SENT,        // 외부 시스템으로 전송됨
    CLONED,      // Message 복제 (FANOUT)
    MERGED,      // 여러 Message 합침
    DROPPED,     // 폐기됨 (필터링)
    FAILED,      // 처리 실패
    REPLAYED     // 재처리됨
}
```

---

## 3. Content Repository

NiFi의 Content Repository를 차용하되, .NET에 맞게 설계.

```
ContentRepository/
  ├── claims/                    ← 불변 데이터 블롭
  │   ├── aa/                    ← 해시 첫 2자리로 디렉토리 분산
  │   │   └── bb/
  │   │       └── aabb1122...    ← SHA-256 해시명 파일
  │   └── cc/
  │       └── dd/
  │           └── ccdd3344...
  ├── staging/                   ← 쓰기 중인 임시 파일
  ├── journal/                   ← WAL (Write-Ahead Log)
  │   └── 2026-03-15_001.wal
  └── metadata.db                ← SQLite (빠른 로컬 인덱스)
```

### 3.1 IContentRepository Interface

```csharp
public interface IContentRepository
{
    /// <summary>
    /// 데이터를 저장하고 ContentClaim 반환.
    /// 같은 데이터(해시 동일)면 기존 claim 재사용.
    /// </summary>
    Task<ContentClaim> StoreAsync(
        Stream data,
        string contentType,
        CancellationToken ct);

    /// <summary>
    /// ContentClaim으로 데이터 스트림 열기.
    /// 메모리에 로드하지 않고 스트리밍.
    /// </summary>
    Task<Stream> ReadAsync(
        string contentHash,
        CancellationToken ct);

    /// <summary>
    /// 참조 카운트 증가 (Message가 이 content를 참조)
    /// </summary>
    Task IncrementRefCountAsync(string contentHash, CancellationToken ct);

    /// <summary>
    /// 참조 카운트 감소. 0이 되면 GC 대상.
    /// </summary>
    Task DecrementRefCountAsync(string contentHash, CancellationToken ct);

    /// <summary>
    /// ref_count = 0인 content 정리 (가비지 컬렉션)
    /// </summary>
    Task<long> CollectGarbageAsync(CancellationToken ct);

    /// <summary>
    /// 저장소 통계
    /// </summary>
    Task<ContentRepositoryStats> GetStatsAsync(CancellationToken ct);
}

public record ContentRepositoryStats
{
    public long TotalClaims { get; init; }
    public long TotalSizeBytes { get; init; }
    public long OrphanedClaims { get; init; }  // ref_count = 0
    public long OrphanedSizeBytes { get; init; }
}
```

### 3.2 데이터 흐름 — Content Repository 사용

```
Step A (Collector) 실행:
  1. 외부에서 데이터 가져옴 (파일, API, Kafka...)
  2. ContentRepository.StoreAsync(data) → ContentClaim { hash: "aabb..." }
  3. Message 생성 { payloadRef: "content://sha256:aabb...", manifest: {...} }
  4. TraceEvent { type: CREATED, currentPayloadRef: "content://sha256:aabb..." }

Step B (Algorithm) 실행:
  1. 이전 Message에서 payloadRef 확인
  2. ContentRepository.ReadAsync("aabb...") → Stream (메모리 아닌 스트리밍)
  3. gRPC로 Algorithm Container에 스트리밍 전달
  4. 결과 수신 → ContentRepository.StoreAsync(result) → "ccdd..."
  5. 새 Message 생성 { payloadRef: "content://sha256:ccdd...", manifest: {...} }
  6. TraceEvent { type: MODIFIED, prev: "aabb", current: "ccdd" }

Step C (Transfer) 실행:
  1. 이전 Message에서 payloadRef 확인
  2. ContentRepository.ReadAsync("ccdd...") → Stream
  3. 외부 시스템에 전송
  4. TraceEvent { type: SENT, destination: "postgresql://..." }
```

---

## 4. Step 간 Message 전달 — Transport 추상화

```csharp
/// <summary>
/// Step 간 데이터 전달 방식 추상화.
/// gRPC든 Kafka든 Shared Volume이든 동일한 인터페이스.
/// </summary>
public interface IMessageTransport
{
    /// <summary>
    /// Message를 다음 Step에 전달
    /// </summary>
    Task SendAsync(Message cargo, StepExecutionContext context, CancellationToken ct);

    /// <summary>
    /// Message 수신 (Step이 자기에게 온 데이터를 받음)
    /// </summary>
    Task<Message> ReceiveAsync(StepExecutionContext context, CancellationToken ct);

    /// <summary>
    /// 대용량 데이터 스트리밍 전달
    /// </summary>
    IAsyncEnumerable<DataChunk> StreamPayloadAsync(
        string payloadRef, CancellationToken ct);
}

// 구현체들:
// - InProcessTransport    (같은 프로세스 내, 기본)
// - GrpcTransport         (gRPC, Docker container 연결)
// - KafkaTransport        (Kafka, 비동기 대용량)
// - SharedVolumeTransport (파일시스템 공유, 단순)
// - NiFiTransport         (NiFi Input/Output Port)
```

### Transport 선택 로직

```csharp
public class TransportSelector
{
    public IMessageTransport Select(StepConfig step, Message cargo)
    {
        // 1. Step의 executionType에 따라
        if (step.ExecutionType == ExecutionType.GRPC)
            return _grpcTransport;
        if (step.ExecutionType == ExecutionType.NIFI_FLOW)
            return _nifiTransport;

        // 2. 데이터 크기에 따라 자동 선택
        if (cargo.ContentSize > _config.KafkaThresholdBytes)
            return _kafkaTransport;  // 대용량 → Kafka

        // 3. 기본값
        return _inProcessTransport;
    }
}
```

---

## 5. Reprocessing에서의 Message

재처리 시 Message/Content Repository의 강점:

```
원본 데이터가 ContentRepository에 남아있으므로:

Reprocess 요청:
  1. 원본 Job의 첫 번째 Message 찾기
  2. payloadRef → ContentRepository에서 원본 데이터 확인
  3. 원본 데이터 그대로 재사용 (복사 불필요!)
  4. 새 Recipe로 Algorithm Step만 재실행
  5. 새 결과 → 새 ContentClaim → 새 Message
  6. TraceEvent { type: REPLAYED, ... }

→ 원본 데이터를 다시 수집할 필요 없음
→ ContentClaim의 ref_count만 증가
→ 디스크 공간 추가 사용 없음 (같은 데이터)
```

---

## 6. 메타포 정리

```
Hermes  = 선박 (플랫폼 전체)
Pipeline = 항로 (데이터가 지나는 경로)
Step     = 항구 (데이터가 처리되는 지점)
Message   = 화물 (데이터 이동 단위)
Manifest = 화물 목록 (메타데이터)
Payload  = 실제 화물 내용물 (데이터 바이트)
Trace   = 항해 기록 (Provenance, 추적 이력)
Recipe   = 화물 처리 지침서 (파라미터 설정)
Job = 운송장 (전체 운송 건 추적)

ContentRepository = 창고 (데이터 보관)
ContentClaim      = 창고 보관증 (데이터 참조)

DeadLetterQueue   = 미배달 화물 보관소
BackPressure      = 항구 정체 (처리 못 따라갈 때)
CircuitBreaker    = 항로 폐쇄 (목적지 장애)
```

모든 용어가 "선박/항해" 메타포로 일관됨 →
브랜딩, 문서, UI에서 통일된 세계관 제공.
