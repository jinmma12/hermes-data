# Hermes - Data Collection & Algorithm Execution Design

> 이 문서는 Hermes의 실제 운영 시나리오를 다룬다.
> "데이터가 어떤 형태인지 모르는 상태에서, 어떻게 수집하고, 어떤 알고리즘에 어떤 파라미터로 분석할지"를
> 설정 가능하게 만드는 구조.

---

## 1. 문제 정의

### 실제 현장에서 일어나는 일

```
1. Kafka 메시지가 온다 (또는 NiFi가 감지한다)
   → "새 데이터가 생겼다" 신호

2. 그런데 데이터가 어디에, 어떤 형태로 있는지는 케이스마다 다르다
   → /data/equip_a/2026-03-15/run_001.csv
   → /logs/system_b/*.json (여러 파일)
   → DB 테이블의 특정 row
   → REST API 응답

3. 파일이 하나일 수도, 여러 개일 수도 있다
   → single file: 하나 찾으면 끝
   → multi file: 패턴에 맞는 것 전부

4. 수집한 데이터를 분석 엔진에 보낸다
   → 어떤 알고리즘을 쓸지?
   → 그 알고리즘의 파라미터는?
   → 결과와 로그는 어디에?

5. 이 모든 설정을 개발자가 아닌 운영자가 Web UI에서 한다
```

---

## 2. DataDescriptor — 데이터 형태 기술

데이터가 어떤 형태인지 모르므로, **DataDescriptor**로 데이터의 위치와 구조를 기술한다.

### 2.1 DataDescriptor Schema

```yaml
# DataDescriptor: "이 데이터는 어디에, 어떤 형태로 있는가"
dataDescriptor:
  # 데이터 위치
  source:
    type: FILE | API | DB | KAFKA | NIFI | CUSTOM

    # FILE인 경우
    file:
      basePath: "/data/equip_a/{date}"      # 변수 사용 가능
      pattern: "*.csv"                       # glob 패턴
      encoding: "utf-8"

    # API인 경우
    api:
      url: "https://vendor.com/api/data"
      method: GET
      headers: { "Authorization": "Bearer {token}" }

    # DB인 경우
    db:
      connectionRef: "erp_db"               # 미리 등록된 connection
      query: "SELECT * FROM orders WHERE created_at > {last_poll}"

    # KAFKA인 경우
    kafka:
      brokers: ["kafka:9092"]
      topic: "equipment.events"
      groupId: "hermes-collector"

  # 데이터 포맷
  format:
    type: CSV | JSON | JSONL | XML | YAML | PARQUET | BINARY | AUTO
    csv:
      delimiter: ","
      header: true
      quoteChar: '"'
    json:
      rootPath: "$.data.records"             # JMESPath/JSONPath
      encoding: "utf-8"
    binary:
      mimeType: "application/octet-stream"

  # 데이터 구조 (선택적 — 검증용)
  schema:
    type: object
    properties:
      timestamp: { type: string, format: date-time }
      value: { type: number }
      status: { type: string, enum: [OK, WARN, ERROR] }
```

### 2.2 Web UI에서의 DataDescriptor 설정

```
┌──────────────────────────────────────────────────────────────┐
│  Data Source Configuration                                    │
│──────────────────────────────────────────────────────────────│
│                                                               │
│  소스 타입:  ● FILE  ○ API  ○ DB  ○ KAFKA  ○ NiFi           │
│                                                               │
│  ── File Settings ──────────────────────────────────────────  │
│                                                               │
│  Base Path:  [ /data/equip_a/{date}          ]               │
│              ℹ️ {date}, {time} 등 변수 사용 가능              │
│                                                               │
│  File Pattern: [ *.csv                       ]               │
│                                                               │
│  Encoding:   [UTF-8           ▼]                             │
│                                                               │
│  ── Format ─────────────────────────────────────────────────  │
│                                                               │
│  데이터 형식:  ● CSV  ○ JSON  ○ YAML  ○ XML  ○ Auto-detect  │
│                                                               │
│  구분자:     [ ,  ]      헤더 포함: [✓]                      │
│                                                               │
│  ── Preview ────────────────────────────────────────────────  │
│                                                               │
│  [Test Connection]  [Preview Data]                            │
│                                                               │
│  ┌─────────────────────────────────────────────────────────┐ │
│  │  timestamp          │ value  │ status │                  │ │
│  │  2026-03-15 10:00  │  23.5  │ OK     │                  │ │
│  │  2026-03-15 10:01  │  24.1  │ OK     │                  │ │
│  │  2026-03-15 10:02  │  99.8  │ ERROR  │  ← 이상치        │ │
│  └─────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────┘
```

---

## 3. CollectionStrategy — 수집 전략

데이터를 "어떻게" 가져올지 전략을 정의한다.

### 3.1 CollectionStrategy Schema

```yaml
collectionStrategy:
  # 트리거: 언제 수집을 시작하는가
  trigger:
    type: SIGNAL | POLL | SCHEDULE | MANUAL

    # SIGNAL: 외부 신호 (Kafka msg, webhook, NiFi notify)
    signal:
      source: KAFKA | WEBHOOK | NIFI
      kafka:
        topic: "equipment.events"
        filter: "$.event_type == 'DATA_READY'"

    # POLL: 주기적 확인
    poll:
      interval: "5m"

    # SCHEDULE: cron 스케줄
    schedule:
      cron: "0 */1 * * *"    # 매시간

  # 파일 수집 모드
  fileCollection:
    mode: SINGLE | MULTI | LATEST | ALL_NEW

    # SINGLE: 조건에 맞는 파일 하나만 찾으면 종료
    # MULTI:  패턴에 맞는 모든 파일 수집
    # LATEST: 가장 최신 파일 하나만
    # ALL_NEW: 마지막 수집 이후 새로 생긴 파일 전부

    ordering: NEWEST_FIRST | OLDEST_FIRST | NAME_ASC | NAME_DESC

    # 필터
    filter:
      minSize: 1024                  # 최소 파일 크기 (bytes)
      maxAge: "24h"                  # 최대 파일 나이
      excludePattern: "*.tmp"        # 제외 패턴

    # 완료 판단
    completionCheck:
      type: NONE | MARKER_FILE | SIZE_STABLE | TIMEOUT
      # MARKER_FILE: .done 파일이 있으면 완료
      markerFile: ".done"
      # SIZE_STABLE: 파일 크기가 N초간 변하지 않으면 완료
      stableSeconds: 5

  # 수집 후 원본 처리
  postCollection:
    action: KEEP | MOVE | DELETE | RENAME
    moveTo: "/data/archive/{date}/"
    renameSuffix: ".processed"
```

### 3.2 Web UI — Collection Strategy

```
┌──────────────────────────────────────────────────────────────┐
│  Collection Strategy                                          │
│──────────────────────────────────────────────────────────────│
│                                                               │
│  ── Trigger ────────────────────────────────────────────────  │
│                                                               │
│  시작 조건:  ○ Signal (Kafka/Webhook)                        │
│             ● Poll (주기적 확인)                              │
│             ○ Schedule (cron)                                 │
│             ○ Manual (수동)                                   │
│                                                               │
│  확인 주기: [ 5m          ]                                  │
│                                                               │
│  ── File Mode ──────────────────────────────────────────────  │
│                                                               │
│  수집 모드:                                                   │
│    ○ Single   — 하나 찾으면 종료                              │
│    ○ Latest   — 가장 최신 파일만                              │
│    ● All New  — 마지막 수집 이후 새 파일 전부                  │
│    ○ Multi    — 패턴 매칭 전부                                │
│                                                               │
│  정렬:       [최신순 (Newest First) ▼]                        │
│                                                               │
│  ── Filters ────────────────────────────────────────────────  │
│                                                               │
│  최소 파일 크기: [ 1 KB      ]                               │
│  최대 파일 나이: [ 24h       ]                               │
│  제외 패턴:     [ *.tmp      ]                               │
│                                                               │
│  ── Completion Check ───────────────────────────────────────  │
│                                                               │
│  완료 판단:  ○ None (바로 수집)                               │
│             ● Marker File (.done 파일 확인)                   │
│             ○ Size Stable (크기 변화 없으면)                   │
│                                                               │
│  Marker 파일명: [ .done      ]                               │
│                                                               │
│  ── After Collection ───────────────────────────────────────  │
│                                                               │
│  수집 후 원본:  ○ 유지  ● 이동  ○ 삭제  ○ 이름 변경         │
│  이동 경로:    [ /data/archive/{date}/  ]                    │
└──────────────────────────────────────────────────────────────┘
```

---

## 4. AlgorithmRecipe — 분석 알고리즘 + 파라미터

### 4.1 AlgorithmDefinition의 실제 예시

```yaml
# 알고리즘 정의 (개발자가 등록)
algorithmDefinition:
  code: "anomaly-detection-zscore"
  name: "Z-Score 이상치 탐지"
  category: "anomaly-detection"

  # 이 알고리즘이 받는 파라미터 — JSON Schema
  inputSchema:
    type: object
    properties:
      # 분석 대상 컬럼
      targetColumn:
        type: string
        title: "분석 대상 컬럼"
        description: "이상치를 탐지할 데이터 컬럼명"

      # 알고리즘 파라미터
      threshold:
        type: number
        title: "Z-Score 임계값"
        description: "이 값을 초과하면 이상치로 판정"
        minimum: 0.5
        maximum: 10.0
        default: 3.0

      windowSize:
        type: integer
        title: "분석 윈도우 크기"
        description: "이동 평균 계산에 사용할 데이터 포인트 수"
        minimum: 10
        maximum: 10000
        default: 100

      method:
        type: string
        title: "Z-Score 방식"
        enum: ["standard", "modified", "iqr"]
        default: "standard"

      sensitivity:
        type: string
        title: "민감도"
        enum: ["low", "medium", "high"]
        default: "medium"

      outputMode:
        type: string
        title: "결과 출력 모드"
        enum: ["anomalies_only", "all_with_score", "summary"]
        default: "anomalies_only"

      # 선택적 전처리
      preprocessing:
        type: object
        title: "전처리 설정"
        properties:
          removeNulls:
            type: boolean
            default: true
          trimOutliers:
            type: boolean
            default: false
          normalization:
            type: string
            enum: ["none", "min-max", "standard"]
            default: "none"

    required: ["targetColumn"]

  # UI 힌트 — Web UI 렌더링 방식
  uiSchema:
    targetColumn:
      ui:widget: "text"
      ui:placeholder: "예: temperature, pressure, voltage"
    threshold:
      ui:widget: "range"
      ui:options:
        step: 0.1
      ui:help: "값이 클수록 느슨한 탐지 (3.0 = 99.7% 신뢰구간)"
    windowSize:
      ui:widget: "updown"
    method:
      ui:widget: "radio"
    sensitivity:
      ui:widget: "radio"
    outputMode:
      ui:widget: "select"
    preprocessing:
      ui:collapsible: true
      ui:collapsed: true
      ui:title: "고급: 전처리 설정"

  # 출력 스키마 — 알고리즘 결과 형태
  outputSchema:
    type: object
    properties:
      anomalyCount:
        type: integer
      anomalies:
        type: array
        items:
          type: object
          properties:
            index: { type: integer }
            value: { type: number }
            zScore: { type: number }
            severity: { type: string }
      statistics:
        type: object
        properties:
          mean: { type: number }
          stdDev: { type: number }
          totalProcessed: { type: integer }

  # 실행 방식
  executionType: PLUGIN
  executionRef: "algorithms/anomaly-zscore"
```

### 4.2 AlgorithmRecipe (운영자가 Web UI에서 설정하는 값)

```yaml
# Recipe v1: 초기 설정
algorithmRecipe:
  version: 1
  createdBy: "operator:kim"
  changeNote: "초기 설정 — 표준 z-score, 임계값 3.0"
  config:
    targetColumn: "temperature"
    threshold: 3.0
    windowSize: 100
    method: "standard"
    sensitivity: "medium"
    outputMode: "anomalies_only"
    preprocessing:
      removeNulls: true

---
# Recipe v2: 운영자가 임계값 조정
algorithmRecipe:
  version: 2
  createdBy: "operator:kim"
  changeNote: "오탐 많아서 임계값 상향 3.0 → 4.0, IQR 방식으로 변경"
  config:
    targetColumn: "temperature"
    threshold: 4.0              # ← 변경됨
    windowSize: 100
    method: "iqr"               # ← 변경됨
    sensitivity: "low"          # ← 변경됨
    outputMode: "anomalies_only"
    preprocessing:
      removeNulls: true

---
# Recipe v3: 다른 컬럼도 분석
algorithmRecipe:
  version: 3
  createdBy: "operator:park"
  changeNote: "압력 데이터도 분석 추가, modified z-score 적용"
  config:
    targetColumn: "pressure"     # ← 분석 대상 변경
    threshold: 3.5
    windowSize: 200             # ← 윈도우 확대
    method: "modified"          # ← modified z-score
    sensitivity: "high"
    outputMode: "all_with_score" # ← 전체 데이터에 점수 부여
    preprocessing:
      removeNulls: true
      trimOutliers: true        # ← 전처리 추가
      normalization: "min-max"   # ← 정규화 추가
```

### 4.3 Web UI — Algorithm Recipe Editor

```
┌──────────────────────────────────────────────────────────────┐
│  Algorithm Recipe: Z-Score 이상치 탐지          v2 → v3 ▼   │
│──────────────────────────────────────────────────────────────│
│                                                               │
│  분석 대상 컬럼                                               │
│  [ pressure                          ]                       │
│  예: temperature, pressure, voltage                          │
│                                                               │
│  Z-Score 임계값                                               │
│  [==========●══════════════════] 3.5                         │
│  ℹ️ 값이 클수록 느슨한 탐지 (3.0 = 99.7% 신뢰구간)          │
│                                                               │
│  분석 윈도우 크기                                             │
│  [ 200 ▲▼ ]                                                 │
│                                                               │
│  Z-Score 방식                                                 │
│  ○ Standard    ● Modified    ○ IQR                           │
│                                                               │
│  민감도                                                       │
│  ○ Low    ○ Medium    ● High                                 │
│                                                               │
│  결과 출력 모드                                               │
│  [ All with Score        ▼]                                  │
│                                                               │
│  ▸ 고급: 전처리 설정  ─────────────────────────────────────  │
│  │  Null 제거:    [✓]                                        │
│  │  극단값 제거:   [✓]                                        │
│  │  정규화:       [Min-Max       ▼]                          │
│  └──────────────────────────────────────────────────────────  │
│                                                               │
│  변경 사유: [ 압력 데이터 분석 추가, modified z-score 적용 ]  │
│                                                               │
│  ┌────────────────────────────────────────────────────────┐  │
│  │  v2 → v3 변경사항:                                     │  │
│  │   targetColumn: "temperature" → "pressure"             │  │
│  │   threshold: 4.0 → 3.5                                │  │
│  │   windowSize: 100 → 200                               │  │
│  │   method: "iqr" → "modified"                          │  │
│  │   + preprocessing.trimOutliers: true                   │  │
│  │   + preprocessing.normalization: "min-max"             │  │
│  └────────────────────────────────────────────────────────┘  │
│                                                               │
│                          [Cancel]  [Save as v3]              │
└──────────────────────────────────────────────────────────────┘
```

---

## 5. End-to-End Flow: Kafka Signal → Collect → Algorithm → Result

### 5.1 전체 흐름

```
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 1: TRIGGER (신호 수신)                                    │
│                                                                   │
│  Kafka Topic: "equipment.events"                                  │
│    ↓                                                              │
│  Message: {                                                       │
│    "event": "DATA_READY",                                        │
│    "equipment": "EQUIP_A",                                       │
│    "dataPath": "/data/equip_a/2026-03-15/",                     │
│    "runId": "run_001",                                           │
│    "timestamp": "2026-03-15T10:15:00Z"                          │
│  }                                                                │
│    ↓                                                              │
│  Hermes MonitoringEngine (Kafka consumer)                        │
│    ↓                                                              │
│  ConditionEvaluator: event.event == "DATA_READY" ✓               │
│    ↓                                                              │
│  Job 생성: source_key = "EQUIP_A/run_001"                   │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 2: COLLECT (데이터 수집)                                  │
│                                                                   │
│  DataDescriptor:                                                  │
│    source.type: FILE                                              │
│    source.file.basePath: "/data/equip_a/{date}"                  │
│    source.file.pattern: "run_{runId}_*.csv"                      │
│    format.type: CSV (delimiter=",", header=true)                  │
│                                                                   │
│  CollectionStrategy:                                              │
│    fileCollection.mode: MULTI (패턴 매칭 전부)                    │
│    ordering: NAME_ASC                                             │
│    completionCheck: MARKER_FILE (.done)                           │
│    postCollection: MOVE → /data/archive/                         │
│                                                                   │
│  수집 결과:                                                       │
│    ├── run_001_sensor_temp.csv  (1.2MB, 15000 rows)              │
│    ├── run_001_sensor_press.csv (0.8MB, 15000 rows)              │
│    └── run_001_meta.json       (2KB)                             │
│                                                                   │
│  Collector Output:                                                │
│    {                                                              │
│      "files": [...],                                             │
│      "totalRecords": 30002,                                      │
│      "totalSize": "2.0MB"                                        │
│    }                                                              │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 3: ALGORITHM (분석)                                       │
│                                                                   │
│  Algorithm: Z-Score 이상치 탐지                                   │
│  Recipe v3:                                                       │
│    targetColumn: "pressure"                                       │
│    threshold: 3.5                                                 │
│    method: "modified"                                             │
│    windowSize: 200                                                │
│    sensitivity: "high"                                            │
│    outputMode: "all_with_score"                                   │
│                                                                   │
│  실행:                                                            │
│    1. CSV 로드 (pandas/polars)                                    │
│    2. pressure 컬럼 추출                                          │
│    3. Modified Z-Score 계산 (MAD 기반)                           │
│    4. |z-score| > 3.5 인 데이터 포인트 마킹                      │
│    5. 결과 생성                                                   │
│                                                                   │
│  Algorithm Output:                                                │
│    {                                                              │
│      "anomalyCount": 7,                                          │
│      "anomalies": [                                              │
│        { "index": 3421, "value": 152.3, "zScore": 4.2,         │
│          "severity": "HIGH" },                                   │
│        ...                                                       │
│      ],                                                          │
│      "statistics": {                                             │
│        "mean": 101.2, "stdDev": 12.3,                           │
│        "totalProcessed": 15000                                   │
│      }                                                           │
│    }                                                              │
│                                                                   │
│  Logs (→ ExecutionEventLog):                                     │
│    10:15:01 ALG_START   "Modified Z-Score, threshold=3.5"        │
│    10:15:01 ALG_LOAD    "Loaded 15000 pressure readings"         │
│    10:15:02 ALG_PROCESS "Window size 200, computing..."          │
│    10:15:03 ALG_RESULT  "7 anomalies detected (0.047%)"         │
│    10:15:03 ALG_DONE    "Completed in 2.1s"                     │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  PHASE 4: TRANSFER (결과 전달)                                   │
│                                                                   │
│  Transfer: DB Insert + Alert                                      │
│  Recipe:                                                          │
│    target: "analysis_results DB"                                  │
│    alertOnAnomaly: true                                           │
│    alertThreshold: 5 (5개 이상이면 알림)                         │
│                                                                   │
│  실행:                                                            │
│    1. 분석 결과 DB 저장                                           │
│    2. anomalyCount(7) > alertThreshold(5) → 알림 전송            │
└──────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌──────────────────────────────────────────────────────────────────┐
│  RESULT: Job #1001 추적 정보                                │
│                                                                   │
│  Job Explorer에서 확인 가능:                                 │
│                                                                   │
│  Execution #1 (INITIAL)                                           │
│    ├── COLLECT   ✅ 1.2s  "3 files, 30002 records"               │
│    ├── ALGORITHM ✅ 2.1s  "7 anomalies (modified z-score 3.5)"   │
│    └── TRANSFER  ✅ 0.3s  "DB saved + alert sent"                │
│                                                                   │
│  Recipe Snapshot: { threshold: 3.5, method: "modified", ... }    │
│  Total Duration: 3.6s                                             │
│                                                                   │
│  만약 나중에 Recipe를 변경하고 재처리하면:                        │
│  Execution #2 (REPROCESS)                                         │
│    ├── ALGORITHM ✅ 1.8s  "12 anomalies (z-score 2.5)"           │
│    └── TRANSFER  ✅ 0.2s  "DB updated + alert sent"              │
│    Recipe Snapshot: { threshold: 2.5, method: "standard", ... }  │
│                                                                   │
│  → 두 실행의 Recipe를 비교해서 "왜 결과가 달라졌는지" 추적 가능  │
└──────────────────────────────────────────────────────────────────┘
```

---

## 6. Pipeline Configuration — 전체를 Web UI에서 조립

### 6.1 파이프라인 조립 화면

```
┌──────────────────────────────────────────────────────────────────┐
│  Pipeline Designer: 설비A 모니터링                                │
│──────────────────────────────────────────────────────────────────│
│                                                                   │
│  ┌─────────────────┐                                             │
│  │ 📡 TRIGGER      │                                             │
│  │                  │                                             │
│  │ Kafka Consumer   │                                             │
│  │ topic: equip.*   │                                             │
│  │ filter: DATA_    │                                             │
│  │         READY    │                                             │
│  │ [Edit Trigger]   │                                             │
│  └────────┬─────────┘                                             │
│           │                                                       │
│           ▼                                                       │
│  ┌─────────────────┐     ┌─────────────────┐                     │
│  │ 📥 COLLECT      │     │ ⚙️ Data Source   │ ← 클릭 시 열림    │
│  │                  │     │   Config         │                     │
│  │ File Collector   │────▶│                  │                     │
│  │                  │     │ basePath: /data/ │                     │
│  │ [Recipe v2]      │     │ pattern: *.csv   │                     │
│  └────────┬─────────┘     │ mode: ALL_NEW    │                     │
│           │               │ format: CSV      │                     │
│           │               │ encoding: UTF-8  │                     │
│           │               └─────────────────┘                     │
│           ▼                                                       │
│  ┌─────────────────┐     ┌─────────────────┐                     │
│  │ 🔬 ALGORITHM    │     │ ⚙️ Algorithm     │ ← 클릭 시 열림    │
│  │                  │     │   Recipe v3      │                     │
│  │ Z-Score 이상치   │────▶│                  │                     │
│  │                  │     │ target: pressure │                     │
│  │ [Recipe v3]      │     │ threshold: 3.5   │                     │
│  └────────┬─────────┘     │ method: modified │                     │
│           │               │ window: 200      │                     │
│           │               │                  │                     │
│           │               │ [Diff v2→v3]     │                     │
│           │               └─────────────────┘                     │
│           ▼                                                       │
│  ┌─────────────────┐     ┌─────────────────┐                     │
│  │ 📤 TRANSFER     │     │ ⚙️ Transfer      │                     │
│  │                  │     │   Config         │                     │
│  │ DB Insert +      │────▶│                  │                     │
│  │ Alert            │     │ target: DB       │                     │
│  │ [Recipe v1]      │     │ alertThreshold:5 │                     │
│  └─────────────────┘     └─────────────────┘                     │
│                                                                   │
│  Pipeline Settings:                                               │
│    On Error: ● Stop  ○ Skip  ○ Retry (3x)                       │
│    Concurrent Items: [ 4 ]                                       │
│                                                                   │
│                                  [Save Draft]  [Activate ▶]     │
└──────────────────────────────────────────────────────────────────┘
```

---

## 7. Multiple Algorithm Support (체인/분기)

하나의 파이프라인에 여러 알고리즘을 연결할 수 있다:

```
# 직렬 체인: A → B → C
COLLECT → ALGORITHM(전처리) → ALGORITHM(이상치탐지) → ALGORITHM(분류) → TRANSFER

# 병렬 분기 (Phase 2):
COLLECT ─┬→ ALGORITHM(이상치) → TRANSFER(DB)
         └→ ALGORITHM(통계)   → TRANSFER(Report)
```

### 7.1 직렬 체인 설정 예시

```yaml
pipelineSteps:
  - stepOrder: 1
    stageType: COLLECT
    ref: "file-collector-equip-a"

  - stepOrder: 2
    stageType: ALGORITHM
    ref: "null-remover"              # 전처리: null 제거
    recipe: { removeColumns: ["unused_col"], fillStrategy: "interpolate" }

  - stepOrder: 3
    stageType: ALGORITHM
    ref: "anomaly-zscore"            # 분석: 이상치 탐지
    recipe: { targetColumn: "pressure", threshold: 3.5 }

  - stepOrder: 4
    stageType: ALGORITHM
    ref: "severity-classifier"       # 분류: 심각도 분류
    recipe: { levels: ["INFO", "WARN", "CRITICAL"], rules: [...] }

  - stepOrder: 5
    stageType: TRANSFER
    ref: "db-insert-results"
```

---

## 8. Data Flow Context (Step 간 데이터 전달)

각 Step의 output이 다음 Step의 input이 된다.

```
┌──────────────────────────────────────────────────────────────┐
│  Step 간 데이터 전달: JobContext                         │
│                                                               │
│  COLLECT output:                                              │
│    {                                                          │
│      "data": [ {col1: v1, col2: v2}, ... ],   ← 실제 데이터 │
│      "metadata": {                                            │
│        "source": "file",                                     │
│        "files": ["run_001_temp.csv"],                        │
│        "recordCount": 15000,                                 │
│        "format": "csv"                                       │
│      }                                                       │
│    }                                                          │
│         │                                                     │
│         ▼ input으로 전달                                      │
│  ALGORITHM input:                                             │
│    위 output 그대로 + recipe 파라미터 적용                    │
│                                                               │
│  ALGORITHM output:                                            │
│    {                                                          │
│      "data": [ {index: 3421, value: 152.3, zScore: 4.2}, ],│
│      "metadata": {                                            │
│        "algorithmUsed": "modified-zscore",                   │
│        "anomalyCount": 7,                                    │
│        "processingTime": 2100                                │
│      }                                                       │
│    }                                                          │
│         │                                                     │
│         ▼ input으로 전달                                      │
│  TRANSFER input:                                              │
│    위 output 그대로 → DB 저장 / 파일 출력 / API 전송         │
└──────────────────────────────────────────────────────────────┘
```

대용량 데이터의 경우, 실제 데이터는 **임시 파일**로 전달하고
메타데이터만 JSON으로 주고받는다:

```json
{
  "dataRef": {
    "type": "FILE",
    "path": "/tmp/hermes/workitems/1001/step_1_output.parquet",
    "format": "parquet",
    "size": 52428800,
    "recordCount": 500000
  },
  "metadata": { ... }
}
```

---

## 9. 이 설계가 반영되어야 할 곳

| 컴포넌트 | 반영 내용 |
|---|---|
| `CollectorDefinition.inputSchema` | DataDescriptor + CollectionStrategy 스키마 포함 |
| `AlgorithmDefinition.inputSchema` | Algorithm 파라미터 전체 정의 |
| `CollectorInstance.config_json` | 실제 DataDescriptor 값 (Recipe) |
| `AlgorithmInstance.config_json` | 실제 Algorithm 파라미터 값 (Recipe) |
| `PipelineStage` | Step 간 데이터 전달 규칙 |
| `Plugin Protocol` | CONFIGURE 메시지에 DataDescriptor 포함 |
| `Web UI - Recipe Editor` | JSON Schema → auto-generated form |
| `Web UI - Pipeline Designer` | 각 노드 클릭 → Recipe Editor |
| `ExecutionSnapshot` | 실행 당시의 DataDescriptor + Recipe 보존 |
| `Job Explorer` | Step 별 input/output 미리보기 |
