# Hermes - Domain Interfaces (C#)

> Complete interface contracts for the Hermes data processing platform.
> A developer can implement each interface without ambiguity by following
> the signatures, XML doc comments, and DTO definitions in this file.

---

## Table of Contents

1. [Enumerations](#1-enumerations)
2. [Domain Entities](#2-domain-entities)
3. [Value Objects](#3-value-objects)
4. [Domain Events](#4-domain-events)
5. [DTOs (Request / Response)](#5-dtos)
6. [Core Service Interfaces](#6-core-service-interfaces)
   - IPipelineManager
   - IRecipeEngine
   - IMonitoringEngine
   - IProcessingOrchestrator
   - IExecutionDispatcher
   - ISnapshotResolver
   - IConditionEvaluator
   - ISchemaRegistry
   - IBackPressureManager
   - ICircuitBreakerManager
   - IDeadLetterQueue
   - IPluginManager
   - INiFiBridge
   - IJobRepository
   - IEventLogger

---

## 1. Enumerations

```csharp
namespace Hermes.Domain.Enums;

/// <summary>Status of a definition (collector, algorithm, transfer).</summary>
public enum DefinitionStatus
{
    Draft,
    Published,
    Deprecated,
    Archived
}

/// <summary>Step type within a pipeline.</summary>
public enum StageType
{
    Collect,
    Algorithm,
    Transfer
}

/// <summary>How a step is executed.</summary>
public enum ExecutionType
{
    Plugin,
    Script,
    Http,
    Docker,
    NifiFlow,
    Internal
}

/// <summary>Pipeline lifecycle status.</summary>
public enum PipelineStatus
{
    Draft,
    Active,
    Paused,
    Archived
}

/// <summary>Pipeline activation runtime status.</summary>
public enum ActivationStatus
{
    Starting,
    Running,
    Stopping,
    Stopped,
    Error
}

/// <summary>What to do when a step fails.</summary>
public enum OnErrorPolicy
{
    Stop,
    Skip,
    Retry
}

/// <summary>How the pipeline is triggered.</summary>
public enum MonitoringType
{
    FileMonitor,
    ApiPoll,
    DbPoll,
    EventStream,
    Schedule,
    Manual
}

/// <summary>Where the source data came from.</summary>
public enum SourceType
{
    File,
    ApiResponse,
    DbChange,
    Event,
    Manual
}

/// <summary>Job processing status.</summary>
public enum JobStatus
{
    Detected,
    Queued,
    Processing,
    Completed,
    Failed,
    Skipped
}

/// <summary>What triggered a particular execution.</summary>
public enum TriggerType
{
    Initial,
    Retry,
    Reprocess
}

/// <summary>Status of a single execution run.</summary>
public enum ExecutionStatus
{
    Pending,
    Running,
    Completed,
    Failed,
    Cancelled,
    TimedOut
}

/// <summary>Status of a reprocess request.</summary>
public enum ReprocessRequestStatus
{
    Pending,
    Approved,
    Executing,
    Done,
    Rejected
}

/// <summary>Log event severity.</summary>
public enum EventLevel
{
    Debug,
    Info,
    Warn,
    Error
}

/// <summary>Plugin archetype.</summary>
public enum PluginType
{
    Collector,
    Algorithm,
    Transfer
}

/// <summary>Health status of a plugin or circuit breaker.</summary>
public enum HealthStatus
{
    Healthy,
    Degraded,
    Unhealthy,
    Unknown
}

/// <summary>Circuit breaker state.</summary>
public enum CircuitState
{
    Closed,
    Open,
    HalfOpen
}

/// <summary>Data source type inside a DataDescriptor.</summary>
public enum DataSourceType
{
    File,
    Api,
    Db,
    Kafka,
    Nifi,
    Custom
}

/// <summary>Data format type.</summary>
public enum DataFormatType
{
    Csv,
    Json,
    Jsonl,
    Xml,
    Yaml,
    Parquet,
    Binary,
    Auto
}

/// <summary>File collection mode.</summary>
public enum FileCollectionMode
{
    Single,
    Multi,
    Latest,
    AllNew
}

/// <summary>Trigger type for collection strategy.</summary>
public enum CollectionTriggerType
{
    Signal,
    Poll,
    Schedule,
    Manual
}

/// <summary>Post-collection action on source files.</summary>
public enum PostCollectionAction
{
    Keep,
    Move,
    Delete,
    Rename
}

/// <summary>Schema compatibility mode for evolution tracking.</summary>
public enum SchemaCompatibility
{
    None,
    Backward,
    Forward,
    Full
}
```

---

## 2. Domain Entities

```csharp
namespace Hermes.Domain.Entities;

using System;
using System.Text.Json;

// ---------------------------------------------------------------------------
// Definition Layer
// ---------------------------------------------------------------------------

/// <summary>
/// A registered processor type (collector, algorithm, or transfer).
/// Developers create definitions; operators create instances from them.
/// </summary>
public record ProcessorDefinition
{
    public Guid Id { get; init; }
    public string Code { get; init; } = string.Empty;
    public string Name { get; init; } = string.Empty;
    public string? Description { get; init; }
    public string? Category { get; init; }
    public string? IconUrl { get; init; }
    public PluginType Type { get; init; }
    public DefinitionStatus Status { get; init; }
    public DateTimeOffset CreatedAt { get; init; }
    public DateTimeOffset UpdatedAt { get; init; }
}

/// <summary>
/// A versioned schema snapshot for a processor definition.
/// Contains the JSON Schemas that drive the Recipe Editor UI.
/// </summary>
public record ProcessorDefinitionVersion
{
    public Guid Id { get; init; }
    public Guid DefinitionId { get; init; }
    public int VersionNo { get; init; }
    public JsonDocument InputSchema { get; init; } = null!;
    public JsonDocument? UiSchema { get; init; }
    public JsonDocument? OutputSchema { get; init; }
    public JsonDocument? DefaultConfig { get; init; }
    public ExecutionType ExecutionType { get; init; }
    public string? ExecutionRef { get; init; }
    public bool IsPublished { get; init; }
    public DateTimeOffset CreatedAt { get; init; }
}

// ---------------------------------------------------------------------------
// Instance Layer
// ---------------------------------------------------------------------------

/// <summary>
/// A configured processor instance created by an operator.
/// </summary>
public record ProcessorInstance
{
    public Guid Id { get; init; }
    public Guid DefinitionId { get; init; }
    public string Name { get; init; } = string.Empty;
    public string? Description { get; init; }
    public DefinitionStatus Status { get; init; }
    public DateTimeOffset CreatedAt { get; init; }
    public DateTimeOffset UpdatedAt { get; init; }
}

/// <summary>
/// A versioned configuration (Recipe) for a processor instance.
/// Each time an operator changes parameters, a new version is created.
/// </summary>
public record ProcessorInstanceVersion
{
    public Guid Id { get; init; }
    public Guid InstanceId { get; init; }
    public Guid DefVersionId { get; init; }
    public int VersionNo { get; init; }

    /// <summary>The Recipe: operator-supplied parameter values.</summary>
    public JsonDocument ConfigJson { get; init; } = null!;

    /// <summary>References to secrets (vault bindings, not raw values).</summary>
    public JsonDocument? SecretBindingJson { get; init; }

    public bool IsCurrent { get; init; }
    public string? CreatedBy { get; init; }
    public string? ChangeNote { get; init; }
    public DateTimeOffset CreatedAt { get; init; }
}

// ---------------------------------------------------------------------------
// Pipeline Layer
// ---------------------------------------------------------------------------

/// <summary>
/// A pipeline assembles a sequence of processor steps.
/// </summary>
public record PipelineInstance
{
    public Guid Id { get; init; }
    public string Name { get; init; } = string.Empty;
    public string? Description { get; init; }
    public MonitoringType MonitoringType { get; init; }
    public JsonDocument? MonitoringConfig { get; init; }
    public PipelineStatus Status { get; init; }
    public int MaxConcurrentItems { get; init; } = 4;
    public OnErrorPolicy DefaultOnError { get; init; } = OnErrorPolicy.Stop;
    public DateTimeOffset CreatedAt { get; init; }
    public DateTimeOffset UpdatedAt { get; init; }
}

/// <summary>
/// A single step within a pipeline, referencing a processor instance.
/// </summary>
public record PipelineStage
{
    public Guid Id { get; init; }
    public Guid PipelineInstanceId { get; init; }
    public int StepOrder { get; init; }
    public StageType StageType { get; init; }
    public StageType RefType { get; init; }
    public Guid RefId { get; init; }
    public bool IsEnabled { get; init; } = true;
    public OnErrorPolicy OnError { get; init; } = OnErrorPolicy.Stop;
    public int RetryCount { get; init; }
    public int RetryDelaySeconds { get; init; }
}

/// <summary>
/// An active run of a pipeline (one activation = one monitoring session).
/// </summary>
public record PipelineActivation
{
    public Guid Id { get; init; }
    public Guid PipelineInstanceId { get; init; }
    public ActivationStatus Status { get; init; }
    public DateTimeOffset StartedAt { get; init; }
    public DateTimeOffset? StoppedAt { get; init; }
    public DateTimeOffset? LastHeartbeatAt { get; init; }
    public DateTimeOffset? LastPolledAt { get; init; }
    public string? ErrorMessage { get; init; }
    public string? WorkerId { get; init; }
}

// ---------------------------------------------------------------------------
// Job Layer
// ---------------------------------------------------------------------------

/// <summary>
/// A single data item tracked through the pipeline.
/// Every file, API response, or event detected becomes a Job.
/// </summary>
public record Job
{
    public Guid Id { get; init; }
    public Guid PipelineActivationId { get; init; }
    public Guid PipelineInstanceId { get; init; }
    public SourceType SourceType { get; init; }
    public string SourceKey { get; init; } = string.Empty;
    public JsonDocument? SourceMetadata { get; init; }
    public string? DedupKey { get; init; }
    public DateTimeOffset DetectedAt { get; init; }
    public JobStatus Status { get; init; }
    public Guid? CurrentExecutionId { get; init; }
    public int ExecutionCount { get; init; }
    public DateTimeOffset? LastCompletedAt { get; init; }
}

/// <summary>
/// One processing run of a Job through the pipeline steps.
/// A Job may have multiple executions (initial + retries + reprocesses).
/// </summary>
public record JobExecution
{
    public Guid Id { get; init; }
    public Guid JobId { get; init; }
    public int ExecutionNo { get; init; }
    public TriggerType TriggerType { get; init; }
    public string? TriggerSource { get; init; }
    public ExecutionStatus Status { get; init; }
    public DateTimeOffset? StartedAt { get; init; }
    public DateTimeOffset? EndedAt { get; init; }
    public long? DurationMs { get; init; }
    public Guid? ReprocessRequestId { get; init; }
}

/// <summary>
/// Result of a single pipeline step within an execution.
/// </summary>
public record JobStepExecution
{
    public Guid Id { get; init; }
    public Guid ExecutionId { get; init; }
    public Guid PipelineStageId { get; init; }
    public StageType StageType { get; init; }
    public int StepOrder { get; init; }
    public ExecutionStatus Status { get; init; }
    public DateTimeOffset? StartedAt { get; init; }
    public DateTimeOffset? EndedAt { get; init; }
    public long? DurationMs { get; init; }
    public JsonDocument? InputSummary { get; init; }
    public JsonDocument? OutputSummary { get; init; }
    public string? ErrorCode { get; init; }
    public string? ErrorMessage { get; init; }
    public int RetryAttempt { get; init; }
}

/// <summary>
/// Frozen copy of all pipeline and recipe configuration at execution time.
/// Enables "what config was used?" auditing even after recipes change.
/// </summary>
public record ExecutionSnapshot
{
    public Guid Id { get; init; }
    public Guid ExecutionId { get; init; }
    public JsonDocument PipelineConfig { get; init; } = null!;
    public JsonDocument? CollectorConfig { get; init; }
    public JsonDocument? AlgorithmConfig { get; init; }
    public JsonDocument? TransferConfig { get; init; }
    public string? SnapshotHash { get; init; }
    public DateTimeOffset CreatedAt { get; init; }
}

/// <summary>
/// A request to reprocess one or more work items.
/// </summary>
public record ReprocessRequest
{
    public Guid Id { get; init; }
    public Guid JobId { get; init; }
    public string? RequestedBy { get; init; }
    public DateTimeOffset RequestedAt { get; init; }
    public string? Reason { get; init; }
    public int? StartFromStep { get; init; }
    public bool UseLatestRecipe { get; init; }
    public ReprocessRequestStatus Status { get; init; }
    public string? ApprovedBy { get; init; }
    public Guid? ExecutionId { get; init; }
}

/// <summary>
/// A single event in the execution log (structured logging for audit).
/// </summary>
public record ExecutionEventLog
{
    public Guid Id { get; init; }
    public Guid ExecutionId { get; init; }
    public Guid? StepExecutionId { get; init; }
    public EventLevel EventType { get; init; }
    public string? EventCode { get; init; }
    public string Message { get; init; } = string.Empty;
    public JsonDocument? DetailJson { get; init; }
    public DateTimeOffset CreatedAt { get; init; }
}
```

---

## 3. Value Objects

```csharp
namespace Hermes.Domain.ValueObjects;

using System;
using System.Collections.Generic;
using System.Text.Json;

/// <summary>
/// Describes a versioned algorithm/collector/transfer configuration
/// as set by an operator in the Recipe Editor.
/// </summary>
public record Recipe
{
    /// <summary>Version number (monotonically increasing per instance).</summary>
    public int Version { get; init; }

    /// <summary>The parameter values (JSON object).</summary>
    public JsonDocument Config { get; init; } = null!;

    /// <summary>Who created this version.</summary>
    public string? CreatedBy { get; init; }

    /// <summary>Operator-supplied change note.</summary>
    public string? ChangeNote { get; init; }

    /// <summary>When this version was created.</summary>
    public DateTimeOffset CreatedAt { get; init; }
}

/// <summary>
/// Describes where data lives and what format it is in.
/// Stored as part of a collector Recipe.
/// </summary>
public record DataDescriptor
{
    public DataSourceConfig Source { get; init; } = null!;
    public DataFormatConfig Format { get; init; } = null!;
    public JsonDocument? Schema { get; init; }
}

public record DataSourceConfig
{
    public DataSourceType Type { get; init; }
    public FileSourceConfig? File { get; init; }
    public ApiSourceConfig? Api { get; init; }
    public DbSourceConfig? Db { get; init; }
    public KafkaSourceConfig? Kafka { get; init; }
}

public record FileSourceConfig
{
    public string BasePath { get; init; } = string.Empty;
    public string? Pattern { get; init; }
    public string Encoding { get; init; } = "utf-8";
}

public record ApiSourceConfig
{
    public string Url { get; init; } = string.Empty;
    public string Method { get; init; } = "GET";
    public Dictionary<string, string>? Headers { get; init; }
}

public record DbSourceConfig
{
    public string ConnectionRef { get; init; } = string.Empty;
    public string Query { get; init; } = string.Empty;
}

public record KafkaSourceConfig
{
    public List<string> Brokers { get; init; } = new();
    public string Topic { get; init; } = string.Empty;
    public string? GroupId { get; init; }
}

public record DataFormatConfig
{
    public DataFormatType Type { get; init; }
    public CsvFormatOptions? Csv { get; init; }
    public JsonFormatOptions? Json { get; init; }
}

public record CsvFormatOptions
{
    public string Delimiter { get; init; } = ",";
    public bool Header { get; init; } = true;
    public char QuoteChar { get; init; } = '"';
}

public record JsonFormatOptions
{
    public string? RootPath { get; init; }
    public string Encoding { get; init; } = "utf-8";
}

/// <summary>
/// Describes how data should be collected (trigger, file mode, post-action).
/// </summary>
public record CollectionStrategy
{
    public TriggerConfig Trigger { get; init; } = null!;
    public FileCollectionConfig? FileCollection { get; init; }
    public PostCollectionConfig? PostCollection { get; init; }
}

public record TriggerConfig
{
    public CollectionTriggerType Type { get; init; }
    public string? PollInterval { get; init; }
    public string? CronExpression { get; init; }
    public SignalConfig? Signal { get; init; }
}

public record SignalConfig
{
    public string Source { get; init; } = string.Empty;
    public string? Topic { get; init; }
    public string? Filter { get; init; }
}

public record FileCollectionConfig
{
    public FileCollectionMode Mode { get; init; }
    public string? Ordering { get; init; }
    public FileFilterConfig? Filter { get; init; }
    public CompletionCheckConfig? CompletionCheck { get; init; }
}

public record FileFilterConfig
{
    public long? MinSizeBytes { get; init; }
    public string? MaxAge { get; init; }
    public string? ExcludePattern { get; init; }
}

public record CompletionCheckConfig
{
    public string Type { get; init; } = "NONE";
    public string? MarkerFile { get; init; }
    public int? StableSeconds { get; init; }
}

public record PostCollectionConfig
{
    public PostCollectionAction Action { get; init; }
    public string? MoveTo { get; init; }
    public string? RenameSuffix { get; init; }
}

/// <summary>
/// Retry policy for step execution.
/// </summary>
public record RetryPolicy
{
    public int MaxAttempts { get; init; } = 3;
    public TimeSpan InitialDelay { get; init; } = TimeSpan.FromSeconds(5);
    public double BackoffMultiplier { get; init; } = 2.0;
    public TimeSpan MaxDelay { get; init; } = TimeSpan.FromMinutes(5);
    public List<string>? RetryableErrorCodes { get; init; }
}

/// <summary>
/// Validation result for pipeline or recipe validation.
/// </summary>
public record ValidationResult
{
    public bool IsValid { get; init; }
    public List<ValidationError> Errors { get; init; } = new();
    public List<ValidationWarning> Warnings { get; init; } = new();
}

public record ValidationError
{
    public string Field { get; init; } = string.Empty;
    public string Code { get; init; } = string.Empty;
    public string Message { get; init; } = string.Empty;
}

public record ValidationWarning
{
    public string Field { get; init; } = string.Empty;
    public string Code { get; init; } = string.Empty;
    public string Message { get; init; } = string.Empty;
}
```

---

## 4. Domain Events

```csharp
namespace Hermes.Domain.Events;

using System;
using System.Text.Json;

/// <summary>Base type for all domain events.</summary>
public abstract record HermesDomainEvent
{
    public Guid EventId { get; init; } = Guid.NewGuid();
    public DateTimeOffset OccurredAt { get; init; } = DateTimeOffset.UtcNow;
    public string? CorrelationId { get; init; }
}

// -- Job events --------------------------------------------------------

public record JobCreated : HermesDomainEvent
{
    public Guid JobId { get; init; }
    public Guid PipelineInstanceId { get; init; }
    public string SourceKey { get; init; } = string.Empty;
    public SourceType SourceType { get; init; }
}

public record JobStatusChanged : HermesDomainEvent
{
    public Guid JobId { get; init; }
    public JobStatus PreviousStatus { get; init; }
    public JobStatus NewStatus { get; init; }
}

public record JobFailed : HermesDomainEvent
{
    public Guid JobId { get; init; }
    public Guid ExecutionId { get; init; }
    public string? ErrorCode { get; init; }
    public string? ErrorMessage { get; init; }
    public int StepOrder { get; init; }
    public bool IsRetryable { get; init; }
}

public record JobCompleted : HermesDomainEvent
{
    public Guid JobId { get; init; }
    public Guid ExecutionId { get; init; }
    public long DurationMs { get; init; }
    public int TotalRecordsProcessed { get; init; }
}

public record JobReprocessRequested : HermesDomainEvent
{
    public Guid JobId { get; init; }
    public Guid ReprocessRequestId { get; init; }
    public string? RequestedBy { get; init; }
    public string? Reason { get; init; }
}

// -- Recipe events ----------------------------------------------------------

public record RecipeChanged : HermesDomainEvent
{
    public Guid InstanceId { get; init; }
    public PluginType PluginType { get; init; }
    public int PreviousVersion { get; init; }
    public int NewVersion { get; init; }
    public string? ChangedBy { get; init; }
    public string? ChangeNote { get; init; }
}

public record RecipePublished : HermesDomainEvent
{
    public Guid InstanceId { get; init; }
    public int Version { get; init; }
    public string? PublishedBy { get; init; }
}

public record RecipeRolledBack : HermesDomainEvent
{
    public Guid InstanceId { get; init; }
    public int FromVersion { get; init; }
    public int ToVersion { get; init; }
    public string? RolledBackBy { get; init; }
}

// -- Schema events ----------------------------------------------------------

public record SchemaChanged : HermesDomainEvent
{
    public Guid DefinitionId { get; init; }
    public int PreviousVersion { get; init; }
    public int NewVersion { get; init; }
    public SchemaCompatibility Compatibility { get; init; }
    public List<string> BreakingChanges { get; init; } = new();
}

public record SchemaValidationFailed : HermesDomainEvent
{
    public Guid JobId { get; init; }
    public string SchemaId { get; init; } = string.Empty;
    public List<string> ValidationErrors { get; init; } = new();
}

// -- Pipeline events --------------------------------------------------------

public record PipelineActivated : HermesDomainEvent
{
    public Guid PipelineInstanceId { get; init; }
    public Guid ActivationId { get; init; }
    public string? WorkerId { get; init; }
}

public record PipelineDeactivated : HermesDomainEvent
{
    public Guid PipelineInstanceId { get; init; }
    public Guid ActivationId { get; init; }
    public string? Reason { get; init; }
}

public record PipelineError : HermesDomainEvent
{
    public Guid PipelineInstanceId { get; init; }
    public Guid ActivationId { get; init; }
    public string ErrorMessage { get; init; } = string.Empty;
}

// -- Plugin events ----------------------------------------------------------

public record PluginHealthChanged : HermesDomainEvent
{
    public string PluginName { get; init; } = string.Empty;
    public HealthStatus PreviousStatus { get; init; }
    public HealthStatus NewStatus { get; init; }
}

// -- Circuit Breaker events -------------------------------------------------

public record CircuitBreakerTripped : HermesDomainEvent
{
    public string CircuitName { get; init; } = string.Empty;
    public string Reason { get; init; } = string.Empty;
    public int FailureCount { get; init; }
}

public record CircuitBreakerReset : HermesDomainEvent
{
    public string CircuitName { get; init; } = string.Empty;
    public string? ResetBy { get; init; }
}
```

---

## 5. DTOs

```csharp
namespace Hermes.Domain.DTOs;

using System;
using System.Collections.Generic;
using System.Text.Json;

// ---------------------------------------------------------------------------
// Pipeline DTOs
// ---------------------------------------------------------------------------

public record CreatePipelineRequest
{
    public string Name { get; init; } = string.Empty;
    public string? Description { get; init; }
    public MonitoringType MonitoringType { get; init; }
    public JsonDocument? MonitoringConfig { get; init; }
    public int MaxConcurrentItems { get; init; } = 4;
    public OnErrorPolicy DefaultOnError { get; init; } = OnErrorPolicy.Stop;
}

public record AddStepRequest
{
    public StageType StageType { get; init; }
    public Guid RefId { get; init; }
    public int? StepOrder { get; init; }
    public bool IsEnabled { get; init; } = true;
    public OnErrorPolicy OnError { get; init; } = OnErrorPolicy.Stop;
    public int RetryCount { get; init; }
    public int RetryDelaySeconds { get; init; }
}

public record PipelineStatusResponse
{
    public Guid PipelineId { get; init; }
    public string Name { get; init; } = string.Empty;
    public PipelineStatus Status { get; init; }
    public ActivationStatus? ActivationStatus { get; init; }
    public DateTimeOffset? LastHeartbeatAt { get; init; }
    public long TotalJobs { get; init; }
    public long CompletedJobs { get; init; }
    public long FailedJobs { get; init; }
    public long InProgressJobs { get; init; }
    public string? WorkerId { get; init; }
}

// ---------------------------------------------------------------------------
// Recipe DTOs
// ---------------------------------------------------------------------------

public record CreateRecipeRequest
{
    public Guid InstanceId { get; init; }
    public JsonDocument Config { get; init; } = null!;
    public string? CreatedBy { get; init; }
    public string? ChangeNote { get; init; }
}

public record RecipeDiffResponse
{
    public int FromVersion { get; init; }
    public int ToVersion { get; init; }
    public List<RecipeFieldDiff> Changes { get; init; } = new();
}

public record RecipeFieldDiff
{
    /// <summary>JSON pointer to the changed field (e.g. "/threshold").</summary>
    public string Path { get; init; } = string.Empty;

    /// <summary>Previous value as a string representation.</summary>
    public string? OldValue { get; init; }

    /// <summary>New value as a string representation.</summary>
    public string? NewValue { get; init; }

    /// <summary>Type of change: "added", "removed", "modified".</summary>
    public string ChangeType { get; init; } = string.Empty;
}

// ---------------------------------------------------------------------------
// Job DTOs
// ---------------------------------------------------------------------------

public record JobListRequest
{
    public Guid? PipelineId { get; init; }
    public JobStatus? Status { get; init; }
    public SourceType? SourceType { get; init; }
    public string? SourceKeyPattern { get; init; }
    public DateTimeOffset? DetectedAfter { get; init; }
    public DateTimeOffset? DetectedBefore { get; init; }
    public string? SortBy { get; init; } = "detected_at";
    public bool SortDescending { get; init; } = true;
    public int Page { get; init; } = 1;
    public int PageSize { get; init; } = 50;
}

public record JobResponse
{
    public Guid Id { get; init; }
    public Guid PipelineInstanceId { get; init; }
    public string? PipelineName { get; init; }
    public SourceType SourceType { get; init; }
    public string SourceKey { get; init; } = string.Empty;
    public JobStatus Status { get; init; }
    public int ExecutionCount { get; init; }
    public DateTimeOffset DetectedAt { get; init; }
    public DateTimeOffset? LastCompletedAt { get; init; }
    public List<JobExecutionSummary> Executions { get; init; } = new();
}

public record JobExecutionSummary
{
    public Guid Id { get; init; }
    public int ExecutionNo { get; init; }
    public TriggerType TriggerType { get; init; }
    public ExecutionStatus Status { get; init; }
    public long? DurationMs { get; init; }
    public DateTimeOffset? StartedAt { get; init; }
    public List<StepExecutionSummary> Steps { get; init; } = new();
}

public record StepExecutionSummary
{
    public Guid Id { get; init; }
    public StageType StageType { get; init; }
    public int StepOrder { get; init; }
    public ExecutionStatus Status { get; init; }
    public long? DurationMs { get; init; }
    public string? ErrorMessage { get; init; }
}

public record PagedResult<T>
{
    public List<T> Items { get; init; } = new();
    public int TotalCount { get; init; }
    public int Page { get; init; }
    public int PageSize { get; init; }
    public int TotalPages => (int)Math.Ceiling((double)TotalCount / PageSize);
    public bool HasNextPage => Page < TotalPages;
    public bool HasPreviousPage => Page > 1;
}

// ---------------------------------------------------------------------------
// Reprocess DTOs
// ---------------------------------------------------------------------------

public record ReprocessJobRequest
{
    public string? Reason { get; init; }
    public int? StartFromStep { get; init; }
    public bool UseLatestRecipe { get; init; } = true;
    public string? RequestedBy { get; init; }
}

public record BulkReprocessRequest
{
    public List<Guid> JobIds { get; init; } = new();
    public string? Reason { get; init; }
    public bool UseLatestRecipe { get; init; } = true;
    public string? RequestedBy { get; init; }
}

public record BulkReprocessResponse
{
    public int TotalRequested { get; init; }
    public int Accepted { get; init; }
    public int Rejected { get; init; }
    public List<BulkReprocessItemResult> Results { get; init; } = new();
}

public record BulkReprocessItemResult
{
    public Guid JobId { get; init; }
    public bool Accepted { get; init; }
    public Guid? ReprocessRequestId { get; init; }
    public string? RejectionReason { get; init; }
}

// ---------------------------------------------------------------------------
// System Stats DTOs
// ---------------------------------------------------------------------------

public record SystemStatsResponse
{
    public int ActivePipelines { get; init; }
    public int TotalPipelines { get; init; }
    public long TotalJobs { get; init; }
    public long JobsToday { get; init; }
    public long FailedJobsToday { get; init; }
    public double AverageProcessingTimeMs { get; init; }
    public int RegisteredPlugins { get; init; }
    public int HealthyPlugins { get; init; }
    public DateTimeOffset Timestamp { get; init; }
}

// ---------------------------------------------------------------------------
// Plugin DTOs
// ---------------------------------------------------------------------------

public record PluginRegistration
{
    public string Name { get; init; } = string.Empty;
    public string DisplayName { get; init; } = string.Empty;
    public string Version { get; init; } = string.Empty;
    public PluginType Type { get; init; }
    public string? Description { get; init; }
    public string? GrpcEndpoint { get; init; }
    public string? ContainerImage { get; init; }
    public JsonDocument? InputSchema { get; init; }
    public JsonDocument? UiSchema { get; init; }
    public JsonDocument? OutputSchema { get; init; }
}

public record PluginHealthReport
{
    public string PluginName { get; init; } = string.Empty;
    public HealthStatus Status { get; init; }
    public string? Message { get; init; }
    public DateTimeOffset CheckedAt { get; init; }
    public long ResponseTimeMs { get; init; }
}

// ---------------------------------------------------------------------------
// Schema Registry DTOs
// ---------------------------------------------------------------------------

public record SchemaRegistryEntry
{
    public string SchemaId { get; init; } = string.Empty;
    public int Version { get; init; }
    public JsonDocument Schema { get; init; } = null!;
    public SchemaCompatibility Compatibility { get; init; }
    public DateTimeOffset RegisteredAt { get; init; }
}

// ---------------------------------------------------------------------------
// Dead Letter Queue DTOs
// ---------------------------------------------------------------------------

public record DeadLetterEntry
{
    public Guid Id { get; init; }
    public Guid JobId { get; init; }
    public Guid? ExecutionId { get; init; }
    public string ErrorCode { get; init; } = string.Empty;
    public string ErrorMessage { get; init; } = string.Empty;
    public JsonDocument? Payload { get; init; }
    public int ReplayCount { get; init; }
    public DateTimeOffset EnqueuedAt { get; init; }
    public DateTimeOffset? LastReplayedAt { get; init; }
}

public record DeadLetterListRequest
{
    public Guid? PipelineId { get; init; }
    public string? ErrorCode { get; init; }
    public DateTimeOffset? Since { get; init; }
    public int Page { get; init; } = 1;
    public int PageSize { get; init; } = 50;
}
```

---

## 6. Core Service Interfaces

### 6.1 IPipelineManager

```csharp
namespace Hermes.Domain.Interfaces;

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

/// <summary>
/// Manages the full lifecycle of pipelines: creation, step management,
/// validation, activation, and deactivation.
/// </summary>
public interface IPipelineManager
{
    /// <summary>
    /// Create a new pipeline in DRAFT status.
    /// </summary>
    /// <param name="request">Pipeline metadata and monitoring configuration.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The newly created pipeline instance.</returns>
    Task<PipelineInstance> CreateAsync(CreatePipelineRequest request, CancellationToken ct = default);

    /// <summary>
    /// Retrieve a pipeline by its unique identifier.
    /// </summary>
    /// <param name="pipelineId">Pipeline identifier.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The pipeline instance, or null if not found.</returns>
    Task<PipelineInstance?> GetByIdAsync(Guid pipelineId, CancellationToken ct = default);

    /// <summary>
    /// List all pipelines, optionally filtered by status.
    /// </summary>
    /// <param name="status">Optional status filter.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Matching pipelines.</returns>
    Task<IReadOnlyList<PipelineInstance>> ListAsync(PipelineStatus? status = null, CancellationToken ct = default);

    /// <summary>
    /// Update pipeline metadata (name, description, monitoring config).
    /// Does not affect steps or recipes.
    /// </summary>
    Task<PipelineInstance> UpdateAsync(Guid pipelineId, CreatePipelineRequest request, CancellationToken ct = default);

    /// <summary>
    /// Add a processing step to the pipeline at the given order position.
    /// If <paramref name="request"/>.StepOrder is null, the step is appended.
    /// </summary>
    Task<PipelineStage> AddStepAsync(Guid pipelineId, AddStepRequest request, CancellationToken ct = default);

    /// <summary>
    /// Remove a step from the pipeline.  Subsequent steps are reordered.
    /// </summary>
    Task RemoveStepAsync(Guid pipelineId, Guid stepId, CancellationToken ct = default);

    /// <summary>
    /// Reorder all steps in one atomic operation.
    /// <paramref name="stepIds"/> must contain every step ID exactly once.
    /// </summary>
    Task ReorderStepsAsync(Guid pipelineId, List<Guid> stepIds, CancellationToken ct = default);

    /// <summary>
    /// Retrieve all steps for a pipeline in order.
    /// </summary>
    Task<IReadOnlyList<PipelineStage>> GetStepsAsync(Guid pipelineId, CancellationToken ct = default);

    /// <summary>
    /// Validate the pipeline: checks that all referenced instances exist,
    /// schemas are compatible between adjacent steps, and monitoring config
    /// is well-formed.
    /// </summary>
    /// <returns>Validation result with errors and warnings.</returns>
    Task<ValidationResult> ValidateAsync(Guid pipelineId, CancellationToken ct = default);

    /// <summary>
    /// Activate the pipeline: start its monitoring engine and begin
    /// detecting new data.  Transitions status from DRAFT/PAUSED to ACTIVE.
    /// </summary>
    /// <returns>The created activation record.</returns>
    Task<PipelineActivation> ActivateAsync(Guid pipelineId, CancellationToken ct = default);

    /// <summary>
    /// Deactivate the pipeline: stop monitoring, drain in-flight items,
    /// and transition to PAUSED.
    /// </summary>
    Task DeactivateAsync(Guid pipelineId, CancellationToken ct = default);

    /// <summary>
    /// Get the current runtime status of a pipeline including activation
    /// details and work item counts.
    /// </summary>
    Task<PipelineStatusResponse> GetStatusAsync(Guid pipelineId, CancellationToken ct = default);
}
```

### 6.2 IRecipeEngine

```csharp
/// <summary>
/// Manages versioned Recipe configurations for processor instances.
/// Recipes are the operator-facing parameter sets that drive plugin execution.
/// </summary>
public interface IRecipeEngine
{
    /// <summary>
    /// Create a new Recipe version for a processor instance.
    /// The new version is created in draft state and is not yet current.
    /// </summary>
    /// <param name="request">Instance ID, config values, author, and change note.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The created recipe (ProcessorInstanceVersion).</returns>
    Task<ProcessorInstanceVersion> CreateVersionAsync(CreateRecipeRequest request, CancellationToken ct = default);

    /// <summary>
    /// Get a specific Recipe version for an instance.
    /// </summary>
    Task<ProcessorInstanceVersion?> GetVersionAsync(Guid instanceId, int versionNo, CancellationToken ct = default);

    /// <summary>
    /// Get the current (published) Recipe for an instance.
    /// </summary>
    Task<ProcessorInstanceVersion?> GetCurrentAsync(Guid instanceId, CancellationToken ct = default);

    /// <summary>
    /// List all Recipe versions for an instance, newest first.
    /// </summary>
    Task<IReadOnlyList<ProcessorInstanceVersion>> ListVersionsAsync(Guid instanceId, CancellationToken ct = default);

    /// <summary>
    /// Compute a field-by-field diff between two Recipe versions.
    /// </summary>
    /// <param name="instanceId">The processor instance.</param>
    /// <param name="fromVersion">Earlier version number.</param>
    /// <param name="toVersion">Later version number.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Structured diff showing added, removed, and modified fields.</returns>
    Task<RecipeDiffResponse> DiffAsync(Guid instanceId, int fromVersion, int toVersion, CancellationToken ct = default);

    /// <summary>
    /// Validate a Recipe's config values against the definition's input schema.
    /// </summary>
    Task<ValidationResult> ValidateAsync(Guid instanceId, JsonDocument config, CancellationToken ct = default);

    /// <summary>
    /// Publish a draft Recipe version, making it the current active version.
    /// The previously current version is demoted.
    /// </summary>
    /// <param name="instanceId">The processor instance.</param>
    /// <param name="versionNo">The draft version number to publish.</param>
    /// <param name="publishedBy">Identity of the user publishing.</param>
    /// <param name="ct">Cancellation token.</param>
    Task PublishAsync(Guid instanceId, int versionNo, string? publishedBy = null, CancellationToken ct = default);

    /// <summary>
    /// Rollback the current Recipe to a previous version.
    /// Creates a new version that copies the target version's config.
    /// </summary>
    /// <param name="instanceId">The processor instance.</param>
    /// <param name="targetVersion">The version number to restore.</param>
    /// <param name="rolledBackBy">Identity of the user rolling back.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The newly created version (copy of target).</returns>
    Task<ProcessorInstanceVersion> RollbackAsync(Guid instanceId, int targetVersion, string? rolledBackBy = null, CancellationToken ct = default);
}
```

### 6.3 IMonitoringEngine

```csharp
/// <summary>
/// Runs the monitoring loop for active pipelines: watches for new data,
/// evaluates conditions, and creates Jobs.
/// </summary>
public interface IMonitoringEngine
{
    /// <summary>
    /// Start monitoring for a specific pipeline activation.
    /// This launches the appropriate monitor (file watcher, API poller, etc.)
    /// and begins detecting new data.
    /// </summary>
    /// <param name="activationId">The pipeline activation to monitor.</param>
    /// <param name="ct">Cancellation token that stops the monitoring loop.</param>
    Task StartAsync(Guid activationId, CancellationToken ct = default);

    /// <summary>
    /// Gracefully stop monitoring for an activation.
    /// In-flight detections are completed but no new polls are started.
    /// </summary>
    Task StopAsync(Guid activationId, CancellationToken ct = default);

    /// <summary>
    /// Register a custom monitor implementation for a specific monitoring type.
    /// </summary>
    /// <param name="monitoringType">The type this monitor handles.</param>
    /// <param name="factory">Factory that creates the monitor from config.</param>
    void RegisterMonitor(MonitoringType monitoringType, Func<JsonDocument, IDataMonitor> factory);

    /// <summary>
    /// Check whether monitoring is currently running for a given activation.
    /// </summary>
    Task<bool> IsRunningAsync(Guid activationId, CancellationToken ct = default);

    /// <summary>
    /// Get the last heartbeat timestamp for an activation's monitor.
    /// Returns null if the monitor has never sent a heartbeat.
    /// </summary>
    Task<DateTimeOffset?> GetLastHeartbeatAsync(Guid activationId, CancellationToken ct = default);
}

/// <summary>
/// A pluggable data monitor that detects new data events.
/// Implementations exist for file watching, API polling, DB change detection, etc.
/// </summary>
public interface IDataMonitor
{
    /// <summary>
    /// Poll for new data events.  Called periodically by the MonitoringEngine.
    /// </summary>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Zero or more detected data events.</returns>
    Task<IReadOnlyList<DataEvent>> PollAsync(CancellationToken ct = default);
}

/// <summary>
/// A detected data event from a monitor (e.g. new file appeared, API returned new records).
/// </summary>
public record DataEvent
{
    public SourceType SourceType { get; init; }
    public string Key { get; init; } = string.Empty;
    public JsonDocument? Metadata { get; init; }
    public DateTimeOffset DetectedAt { get; init; }
}
```

### 6.4 IProcessingOrchestrator

```csharp
/// <summary>
/// Orchestrates the execution of a Job through its pipeline steps.
/// Manages the step-by-step processing, snapshot capture, and result recording.
/// </summary>
public interface IProcessingOrchestrator
{
    /// <summary>
    /// Process a single Job through the pipeline.
    /// Executes each enabled step in order, capturing snapshots and recording results.
    /// </summary>
    /// <param name="jobId">The Job to process.</param>
    /// <param name="trigger">What triggered this processing (initial, retry, reprocess).</param>
    /// <param name="startFromStep">1-based step order to start from (default 1 = beginning).</param>
    /// <param name="useLatestRecipe">True to use current recipe; false to use original snapshot.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The completed execution record.</returns>
    Task<JobExecution> ProcessAsync(
        Guid jobId,
        TriggerType trigger,
        int startFromStep = 1,
        bool useLatestRecipe = true,
        CancellationToken ct = default);

    /// <summary>
    /// Reprocess a single Job.  Creates a ReprocessRequest and then executes it.
    /// </summary>
    /// <param name="jobId">The Job to reprocess.</param>
    /// <param name="request">Reprocess parameters (reason, start step, recipe policy).</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The new execution record.</returns>
    Task<JobExecution> ReprocessAsync(Guid jobId, ReprocessJobRequest request, CancellationToken ct = default);

    /// <summary>
    /// Reprocess multiple Jobs in batch.  Items are processed concurrently
    /// up to the pipeline's MaxConcurrentItems limit.
    /// </summary>
    Task<BulkReprocessResponse> BulkReprocessAsync(BulkReprocessRequest request, CancellationToken ct = default);

    /// <summary>
    /// Cancel a running execution.  If the plugin supports cancellation,
    /// a cancellation signal is sent; otherwise the execution is marked as cancelled
    /// and the plugin process is terminated.
    /// </summary>
    Task CancelExecutionAsync(Guid executionId, CancellationToken ct = default);

    /// <summary>
    /// Stream real-time execution events for a running Job.
    /// Returns log messages, progress updates, and step completions as they occur.
    /// </summary>
    IAsyncEnumerable<ExecutionEvent> StreamExecutionEventsAsync(
        Guid executionId,
        CancellationToken ct = default);
}

/// <summary>
/// A real-time event emitted during execution (for WebSocket streaming to the UI).
/// </summary>
public record ExecutionEvent
{
    public string EventType { get; init; } = string.Empty;
    public Guid ExecutionId { get; init; }
    public Guid? StepExecutionId { get; init; }
    public JsonDocument? Data { get; init; }
    public DateTimeOffset Timestamp { get; init; }
}
```

### 6.5 IExecutionDispatcher

```csharp
/// <summary>
/// Dispatches step execution to the appropriate runtime: in-process plugin,
/// subprocess, HTTP call, Docker container, or NiFi flow.
/// </summary>
public interface IExecutionDispatcher
{
    /// <summary>
    /// Execute a single pipeline step using the configured execution type.
    /// </summary>
    /// <param name="executionType">How to execute (Plugin, Script, Http, Docker, NifiFlow, Internal).</param>
    /// <param name="executionRef">Reference to the executable (plugin name, script path, URL, image, flow ID).</param>
    /// <param name="config">Resolved configuration (Recipe values + secrets).</param>
    /// <param name="inputData">Output from the previous step (null for the first step).</param>
    /// <param name="context">Execution context (work item ID, step info, etc.).</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Step execution result including output data and summary.</returns>
    Task<StepExecutionResult> ExecuteAsync(
        ExecutionType executionType,
        string executionRef,
        JsonDocument config,
        JsonDocument? inputData,
        ExecutionContext context,
        CancellationToken ct = default);

    /// <summary>
    /// Execute with streaming output.  The caller receives results as they
    /// are produced by the plugin (useful for large data and real-time UI updates).
    /// </summary>
    IAsyncEnumerable<StepExecutionEvent> ExecuteStreamingAsync(
        ExecutionType executionType,
        string executionRef,
        JsonDocument config,
        JsonDocument? inputData,
        ExecutionContext context,
        CancellationToken ct = default);

    /// <summary>
    /// Check whether the dispatcher can handle the given execution type.
    /// </summary>
    bool CanDispatch(ExecutionType executionType);
}

/// <summary>
/// Context provided to the execution dispatcher for each step.
/// </summary>
public record ExecutionContext
{
    public Guid JobId { get; init; }
    public int ExecutionNo { get; init; }
    public StageType StageType { get; init; }
    public int StepOrder { get; init; }
    public Guid PipelineId { get; init; }
    public string? PipelineName { get; init; }
    public TriggerType TriggerType { get; init; }
    public string? TriggerSource { get; init; }
    public DateTimeOffset StartedAt { get; init; }
    public int RecipeVersion { get; init; }
    public Dictionary<string, string>? Metadata { get; init; }
}

/// <summary>
/// Result of executing a single step.
/// </summary>
public record StepExecutionResult
{
    public ExecutionStatus Status { get; init; }
    public JsonDocument? OutputData { get; init; }
    public JsonDocument? OutputSummary { get; init; }
    public string? ErrorCode { get; init; }
    public string? ErrorMessage { get; init; }
    public bool IsRetryable { get; init; }
    public long DurationMs { get; init; }
    public long RecordsProcessed { get; init; }
}

/// <summary>
/// A streaming event from step execution (log, output record, progress, etc.).
/// </summary>
public record StepExecutionEvent
{
    public string EventType { get; init; } = string.Empty;  // "log", "output", "progress", "error", "done"
    public JsonDocument? Payload { get; init; }
    public DateTimeOffset Timestamp { get; init; }
}
```

### 6.6 ISnapshotResolver

```csharp
/// <summary>
/// Captures and resolves execution snapshots: frozen copies of all pipeline
/// and recipe configuration at execution time.
/// </summary>
public interface ISnapshotResolver
{
    /// <summary>
    /// Capture a snapshot of the current pipeline configuration, including
    /// all step configs and their active recipes.  Secrets are resolved
    /// and included in the snapshot.
    /// </summary>
    /// <param name="pipelineId">The pipeline to snapshot.</param>
    /// <param name="steps">The ordered pipeline steps.</param>
    /// <param name="useLatestRecipe">True to use current recipe; false to use a previous snapshot.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The captured snapshot.</returns>
    Task<ExecutionSnapshot> CaptureAsync(
        Guid pipelineId,
        IReadOnlyList<PipelineStage> steps,
        bool useLatestRecipe = true,
        CancellationToken ct = default);

    /// <summary>
    /// Resolve a previously captured snapshot: return the config for a
    /// specific step within the snapshot.
    /// </summary>
    /// <param name="snapshotId">The snapshot identifier.</param>
    /// <param name="stepOrder">The step order to resolve config for.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Resolved step configuration.</returns>
    Task<ResolvedStepConfig> ResolveAsync(Guid snapshotId, int stepOrder, CancellationToken ct = default);

    /// <summary>
    /// Compare two snapshots and return the differences.
    /// Useful for understanding why a reprocess produced different results.
    /// </summary>
    Task<RecipeDiffResponse> CompareSnapshotsAsync(Guid snapshotId1, Guid snapshotId2, CancellationToken ct = default);
}

/// <summary>
/// Fully resolved configuration for a pipeline step, ready for execution.
/// </summary>
public record ResolvedStepConfig
{
    public ExecutionType ExecutionType { get; init; }
    public string ExecutionRef { get; init; } = string.Empty;
    public JsonDocument ResolvedConfig { get; init; } = null!;
    public int RecipeVersion { get; init; }
}
```

### 6.7 IConditionEvaluator

```csharp
/// <summary>
/// Evaluates whether a detected data event should create a Job,
/// and generates deduplication keys to prevent duplicate processing.
/// </summary>
public interface IConditionEvaluator
{
    /// <summary>
    /// Evaluate whether a data event matches the pipeline's trigger conditions.
    /// </summary>
    /// <param name="dataEvent">The detected event.</param>
    /// <param name="monitoringConfig">The pipeline's monitoring configuration.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>True if a Job should be created.</returns>
    Task<bool> ShouldCreateJobAsync(
        DataEvent dataEvent,
        JsonDocument monitoringConfig,
        CancellationToken ct = default);

    /// <summary>
    /// Generate a deterministic deduplication key for a data event.
    /// Two events with the same dedup key are considered the same data item
    /// and will not produce duplicate Jobs.
    /// </summary>
    /// <param name="dataEvent">The detected event.</param>
    /// <param name="pipelineId">The pipeline context.</param>
    /// <returns>A stable dedup key string.</returns>
    string GenerateDedupKey(DataEvent dataEvent, Guid pipelineId);
}
```

### 6.8 ISchemaRegistry

```csharp
/// <summary>
/// Tracks data schemas across the platform, validates data against schemas,
/// and detects breaking changes in schema evolution.
/// </summary>
public interface ISchemaRegistry
{
    /// <summary>
    /// Register or update a schema.  If the schema already exists, a new
    /// version is created and compatibility is checked.
    /// </summary>
    /// <param name="schemaId">Unique schema identifier (e.g. "orders.v1").</param>
    /// <param name="schema">The JSON Schema document.</param>
    /// <param name="compatibility">Required compatibility mode for evolution.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The registered schema entry with its version.</returns>
    Task<SchemaRegistryEntry> RegisterAsync(
        string schemaId,
        JsonDocument schema,
        SchemaCompatibility compatibility = SchemaCompatibility.Backward,
        CancellationToken ct = default);

    /// <summary>
    /// Get a specific version of a schema.
    /// </summary>
    Task<SchemaRegistryEntry?> GetAsync(string schemaId, int? version = null, CancellationToken ct = default);

    /// <summary>
    /// List all registered schema IDs with their latest version.
    /// </summary>
    Task<IReadOnlyList<SchemaRegistryEntry>> ListAsync(CancellationToken ct = default);

    /// <summary>
    /// Discover schemas from a plugin by invoking its Discover RPC.
    /// Discovered schemas are registered automatically.
    /// </summary>
    /// <param name="pluginName">Name of the plugin to discover from.</param>
    /// <param name="config">Plugin configuration for connecting to the data source.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>List of discovered and registered schemas.</returns>
    Task<IReadOnlyList<SchemaRegistryEntry>> DiscoverFromPluginAsync(
        string pluginName,
        JsonDocument config,
        CancellationToken ct = default);

    /// <summary>
    /// Validate a data record against a registered schema.
    /// </summary>
    /// <param name="schemaId">The schema to validate against.</param>
    /// <param name="data">The data record to validate.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Validation result with any schema violations.</returns>
    Task<ValidationResult> ValidateAsync(string schemaId, JsonDocument data, CancellationToken ct = default);

    /// <summary>
    /// Check the compatibility of a proposed schema change against the
    /// current schema and its configured compatibility mode.
    /// </summary>
    /// <param name="schemaId">The schema identifier.</param>
    /// <param name="proposedSchema">The new schema version to check.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Validation result: IsValid=true if the change is compatible.</returns>
    Task<ValidationResult> CheckCompatibilityAsync(
        string schemaId,
        JsonDocument proposedSchema,
        CancellationToken ct = default);

    /// <summary>
    /// Get the evolution history of a schema (all versions with diffs).
    /// </summary>
    Task<IReadOnlyList<SchemaRegistryEntry>> GetHistoryAsync(string schemaId, CancellationToken ct = default);
}
```

### 6.9 IBackPressureManager

```csharp
/// <summary>
/// Manages back-pressure across the processing pipeline.
/// Prevents overwhelming downstream systems when work items accumulate
/// faster than they can be processed.
/// </summary>
public interface IBackPressureManager
{
    /// <summary>
    /// Check whether a pipeline is currently under back-pressure.
    /// </summary>
    /// <param name="pipelineId">The pipeline to check.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Current back-pressure status and metrics.</returns>
    Task<BackPressureStatus> CheckAsync(Guid pipelineId, CancellationToken ct = default);

    /// <summary>
    /// Apply throttling to a pipeline.  Reduces the rate at which new
    /// Jobs are dequeued for processing.
    /// </summary>
    /// <param name="pipelineId">The pipeline to throttle.</param>
    /// <param name="maxConcurrent">Maximum concurrent items to process.</param>
    /// <param name="delayBetweenItems">Minimum delay between starting new items.</param>
    /// <param name="ct">Cancellation token.</param>
    Task ThrottleAsync(
        Guid pipelineId,
        int? maxConcurrent = null,
        TimeSpan? delayBetweenItems = null,
        CancellationToken ct = default);

    /// <summary>
    /// Release back-pressure on a pipeline, restoring normal throughput.
    /// </summary>
    Task ReleaseAsync(Guid pipelineId, CancellationToken ct = default);

    /// <summary>
    /// Wait until back-pressure is relieved before proceeding.
    /// Used by the processing orchestrator before starting a new work item.
    /// </summary>
    /// <param name="pipelineId">The pipeline to wait for.</param>
    /// <param name="ct">Cancellation token.</param>
    Task WaitForCapacityAsync(Guid pipelineId, CancellationToken ct = default);
}

/// <summary>
/// Current back-pressure status for a pipeline.
/// </summary>
public record BackPressureStatus
{
    public Guid PipelineId { get; init; }
    public bool IsThrottled { get; init; }
    public int QueueDepth { get; init; }
    public int ActiveItems { get; init; }
    public int MaxConcurrent { get; init; }
    public double UtilizationPercent { get; init; }
    public TimeSpan? DelayBetweenItems { get; init; }
}
```

### 6.10 ICircuitBreakerManager

```csharp
/// <summary>
/// Manages circuit breakers for external dependencies (APIs, databases,
/// plugins).  Prevents cascading failures by fast-failing when a dependency
/// is known to be down.
/// </summary>
public interface ICircuitBreakerManager
{
    /// <summary>
    /// Get the current state of a named circuit breaker.
    /// </summary>
    /// <param name="circuitName">Unique name for the circuit (e.g. "plugin:rest-api-collector").</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Current circuit state and failure statistics.</returns>
    Task<CircuitBreakerStatus> GetStateAsync(string circuitName, CancellationToken ct = default);

    /// <summary>
    /// Record a successful call through the circuit.  Resets failure counters
    /// and transitions from HalfOpen to Closed if applicable.
    /// </summary>
    Task RecordSuccessAsync(string circuitName, CancellationToken ct = default);

    /// <summary>
    /// Record a failed call.  Increments failure counters and may trip the
    /// circuit to Open state if the failure threshold is exceeded.
    /// </summary>
    /// <param name="circuitName">The circuit name.</param>
    /// <param name="exception">The exception that caused the failure.</param>
    /// <param name="ct">Cancellation token.</param>
    Task RecordFailureAsync(string circuitName, Exception? exception = null, CancellationToken ct = default);

    /// <summary>
    /// Manually trip a circuit breaker to Open state.
    /// </summary>
    /// <param name="circuitName">The circuit to trip.</param>
    /// <param name="reason">Why the circuit is being tripped.</param>
    /// <param name="duration">How long to keep the circuit open before transitioning to HalfOpen.</param>
    /// <param name="ct">Cancellation token.</param>
    Task TripAsync(string circuitName, string reason, TimeSpan? duration = null, CancellationToken ct = default);

    /// <summary>
    /// Manually reset a circuit breaker to Closed state.
    /// </summary>
    /// <param name="circuitName">The circuit to reset.</param>
    /// <param name="resetBy">Who is resetting the circuit.</param>
    /// <param name="ct">Cancellation token.</param>
    Task ResetAsync(string circuitName, string? resetBy = null, CancellationToken ct = default);

    /// <summary>
    /// Check whether a call should be allowed through the circuit.
    /// Returns false if the circuit is Open (fast-fail).
    /// </summary>
    Task<bool> AllowRequestAsync(string circuitName, CancellationToken ct = default);

    /// <summary>
    /// List all circuit breakers and their current states.
    /// </summary>
    Task<IReadOnlyList<CircuitBreakerStatus>> ListAllAsync(CancellationToken ct = default);
}

/// <summary>
/// Current status of a circuit breaker.
/// </summary>
public record CircuitBreakerStatus
{
    public string CircuitName { get; init; } = string.Empty;
    public CircuitState State { get; init; }
    public int FailureCount { get; init; }
    public int SuccessCount { get; init; }
    public int ConsecutiveFailures { get; init; }
    public int FailureThreshold { get; init; }
    public DateTimeOffset? LastFailureAt { get; init; }
    public DateTimeOffset? LastSuccessAt { get; init; }
    public DateTimeOffset? OpenUntil { get; init; }
    public string? LastFailureReason { get; init; }
}
```

### 6.11 IDeadLetterQueue

```csharp
/// <summary>
/// Manages permanently failed work items that could not be processed
/// after all retry attempts.  Supports inspection, replay, and discard.
/// </summary>
public interface IDeadLetterQueue
{
    /// <summary>
    /// Enqueue a failed work item into the dead letter queue.
    /// Called by the processing orchestrator after all retries are exhausted.
    /// </summary>
    /// <param name="jobId">The failed work item.</param>
    /// <param name="executionId">The execution that failed.</param>
    /// <param name="errorCode">Machine-readable error code.</param>
    /// <param name="errorMessage">Human-readable error message.</param>
    /// <param name="payload">The input data that caused the failure (for replay).</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The created dead letter entry.</returns>
    Task<DeadLetterEntry> EnqueueAsync(
        Guid jobId,
        Guid executionId,
        string errorCode,
        string errorMessage,
        JsonDocument? payload = null,
        CancellationToken ct = default);

    /// <summary>
    /// List dead letter entries with optional filters and pagination.
    /// </summary>
    Task<PagedResult<DeadLetterEntry>> ListAsync(DeadLetterListRequest request, CancellationToken ct = default);

    /// <summary>
    /// Get a single dead letter entry by ID.
    /// </summary>
    Task<DeadLetterEntry?> GetByIdAsync(Guid entryId, CancellationToken ct = default);

    /// <summary>
    /// Replay a dead letter entry: resubmit the work item for processing.
    /// The entry's ReplayCount is incremented.
    /// </summary>
    /// <param name="entryId">The dead letter entry to replay.</param>
    /// <param name="useLatestRecipe">Whether to use the latest recipe on replay.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The new execution created by the replay.</returns>
    Task<JobExecution> ReplayAsync(Guid entryId, bool useLatestRecipe = true, CancellationToken ct = default);

    /// <summary>
    /// Replay all dead letter entries matching the given filter.
    /// </summary>
    Task<BulkReprocessResponse> ReplayBulkAsync(DeadLetterListRequest filter, CancellationToken ct = default);

    /// <summary>
    /// Discard a dead letter entry (acknowledge the failure, no further action).
    /// </summary>
    /// <param name="entryId">The entry to discard.</param>
    /// <param name="reason">Why the entry is being discarded.</param>
    /// <param name="ct">Cancellation token.</param>
    Task DiscardAsync(Guid entryId, string? reason = null, CancellationToken ct = default);

    /// <summary>
    /// Get aggregate statistics for the dead letter queue.
    /// </summary>
    Task<DeadLetterStats> GetStatsAsync(Guid? pipelineId = null, CancellationToken ct = default);
}

/// <summary>
/// Aggregate statistics for the dead letter queue.
/// </summary>
public record DeadLetterStats
{
    public long TotalEntries { get; init; }
    public long EntriesLast24h { get; init; }
    public long ReplayedCount { get; init; }
    public long DiscardedCount { get; init; }

    /// <summary>Top error codes with their counts.</summary>
    public Dictionary<string, int> TopErrorCodes { get; init; } = new();
}
```

### 6.12 IPluginManager

```csharp
/// <summary>
/// Manages plugin discovery, registration, lifecycle, and health monitoring.
/// Communicates with plugins via gRPC (HermesPluginService).
/// </summary>
public interface IPluginManager
{
    /// <summary>
    /// Discover all available plugins from configured sources (local directory,
    /// container registry, plugin marketplace).
    /// </summary>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>List of discovered plugin specs.</returns>
    Task<IReadOnlyList<PluginRegistration>> DiscoverAsync(CancellationToken ct = default);

    /// <summary>
    /// Register a plugin with Hermes Core.  This creates or updates the
    /// corresponding ProcessorDefinition and ProcessorDefinitionVersion.
    /// </summary>
    /// <param name="registration">Plugin registration details (endpoint, schemas).</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The created or updated definition.</returns>
    Task<ProcessorDefinition> RegisterAsync(PluginRegistration registration, CancellationToken ct = default);

    /// <summary>
    /// Unregister a plugin.  Does not delete existing instances or history.
    /// Marks the definition as Deprecated.
    /// </summary>
    Task UnregisterAsync(string pluginName, CancellationToken ct = default);

    /// <summary>
    /// Execute a plugin's Check RPC to validate connectivity and configuration.
    /// </summary>
    /// <param name="pluginName">The registered plugin name.</param>
    /// <param name="config">Configuration to validate.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Check result (succeeded / failed with details).</returns>
    Task<PluginCheckResult> CheckAsync(string pluginName, JsonDocument config, CancellationToken ct = default);

    /// <summary>
    /// Execute a plugin's Discover RPC to discover available schemas/streams.
    /// </summary>
    Task<IReadOnlyList<DiscoveredStream>> DiscoverSchemasAsync(
        string pluginName,
        JsonDocument config,
        CancellationToken ct = default);

    /// <summary>
    /// Execute a plugin with the given configuration and input data.
    /// Returns the full result after execution completes.
    /// </summary>
    Task<StepExecutionResult> ExecuteAsync(
        string pluginName,
        JsonDocument config,
        JsonDocument? inputData,
        ExecutionContext context,
        CancellationToken ct = default);

    /// <summary>
    /// Execute a plugin with streaming output.
    /// </summary>
    IAsyncEnumerable<StepExecutionEvent> ExecuteStreamingAsync(
        string pluginName,
        JsonDocument config,
        JsonDocument? inputData,
        ExecutionContext context,
        CancellationToken ct = default);

    /// <summary>
    /// Check the health of a specific plugin.
    /// </summary>
    Task<PluginHealthReport> HealthCheckAsync(string pluginName, CancellationToken ct = default);

    /// <summary>
    /// Check the health of all registered plugins.
    /// </summary>
    Task<IReadOnlyList<PluginHealthReport>> HealthCheckAllAsync(CancellationToken ct = default);

    /// <summary>
    /// Get the list of all registered plugins and their current status.
    /// </summary>
    Task<IReadOnlyList<PluginRegistration>> ListRegisteredAsync(CancellationToken ct = default);
}

/// <summary>
/// Result of a plugin Check RPC.
/// </summary>
public record PluginCheckResult
{
    public bool Succeeded { get; init; }
    public string? Message { get; init; }
    public Dictionary<string, string>? FieldErrors { get; init; }
}

/// <summary>
/// A discovered data stream from a plugin's Discover RPC.
/// </summary>
public record DiscoveredStream
{
    public string StreamId { get; init; } = string.Empty;
    public string Name { get; init; } = string.Empty;
    public JsonDocument? Schema { get; init; }
    public List<string> SupportedSyncModes { get; init; } = new();
    public string? DefaultCursorField { get; init; }
    public List<string> PrimaryKeyFields { get; init; } = new();
    public long EstimatedRecordCount { get; init; }
}
```

### 6.13 INiFiBridge

```csharp
/// <summary>
/// Bridge between Hermes and Apache NiFi for using NiFi as an execution backend.
/// Hermes manages recipes and tracking; NiFi handles heavy-duty data processing.
/// </summary>
public interface INiFiBridge
{
    /// <summary>
    /// Synchronise Hermes pipeline configuration with a NiFi process group.
    /// Creates or updates NiFi processors to match the pipeline steps.
    /// </summary>
    /// <param name="pipelineId">The Hermes pipeline to sync.</param>
    /// <param name="processGroupId">The NiFi process group ID.</param>
    /// <param name="ct">Cancellation token.</param>
    Task SyncAsync(Guid pipelineId, string processGroupId, CancellationToken ct = default);

    /// <summary>
    /// Push a Recipe update to NiFi processor properties.
    /// </summary>
    /// <param name="pipelineStepId">The step whose recipe changed.</param>
    /// <param name="recipe">The recipe to push.</param>
    /// <param name="nifiProcessorId">The NiFi processor to update.</param>
    /// <param name="ct">Cancellation token.</param>
    Task PushRecipeAsync(
        Guid pipelineStepId,
        ProcessorInstanceVersion recipe,
        string nifiProcessorId,
        CancellationToken ct = default);

    /// <summary>
    /// Trigger a NiFi flow to process a specific work item.
    /// Sends the input data via NiFi's input port and waits for output.
    /// </summary>
    /// <param name="processGroupId">The NiFi process group to trigger.</param>
    /// <param name="inputData">Data to feed into NiFi.</param>
    /// <param name="context">Execution context for tracking.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>The NiFi execution result.</returns>
    Task<StepExecutionResult> TriggerFlowAsync(
        string processGroupId,
        JsonDocument inputData,
        ExecutionContext context,
        CancellationToken ct = default);

    /// <summary>
    /// Monitor a running NiFi flow and stream back status updates.
    /// </summary>
    /// <param name="processGroupId">The NiFi process group to monitor.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Stream of NiFi status events.</returns>
    IAsyncEnumerable<NiFiStatusEvent> MonitorFlowAsync(
        string processGroupId,
        CancellationToken ct = default);

    /// <summary>
    /// Get the current status of a NiFi process group.
    /// </summary>
    Task<NiFiFlowStatus> GetFlowStatusAsync(string processGroupId, CancellationToken ct = default);
}

/// <summary>
/// A status event from a NiFi flow.
/// </summary>
public record NiFiStatusEvent
{
    public string EventType { get; init; } = string.Empty;
    public string ProcessGroupId { get; init; } = string.Empty;
    public JsonDocument? Data { get; init; }
    public DateTimeOffset Timestamp { get; init; }
}

/// <summary>
/// Current status of a NiFi process group.
/// </summary>
public record NiFiFlowStatus
{
    public string ProcessGroupId { get; init; } = string.Empty;
    public string State { get; init; } = string.Empty;  // RUNNING, STOPPED, etc.
    public int ActiveThreads { get; init; }
    public long QueuedFlowFiles { get; init; }
    public long QueuedBytes { get; init; }
    public long BytesRead { get; init; }
    public long BytesWritten { get; init; }
}
```

### 6.14 IJobRepository

```csharp
/// <summary>
/// Persistence interface for Job and related execution entities.
/// Provides efficient querying, filtering, and pagination.
/// </summary>
public interface IJobRepository
{
    // -- Job CRUD -------------------------------------------------------

    /// <summary>Create a new Job.</summary>
    Task<Job> CreateAsync(Job job, CancellationToken ct = default);

    /// <summary>Get a Job by its unique identifier.</summary>
    Task<Job?> GetByIdAsync(Guid jobId, CancellationToken ct = default);

    /// <summary>Find a Job by its dedup key within a pipeline.</summary>
    Task<Job?> GetByDedupKeyAsync(Guid pipelineId, string dedupKey, CancellationToken ct = default);

    /// <summary>Check whether a dedup key already exists for a pipeline.</summary>
    Task<bool> ExistsByDedupKeyAsync(Guid pipelineId, string dedupKey, CancellationToken ct = default);

    /// <summary>List Jobs with filtering, sorting, and pagination.</summary>
    Task<PagedResult<Job>> ListAsync(JobListRequest request, CancellationToken ct = default);

    /// <summary>Update a Job's status and related fields.</summary>
    Task<Job> UpdateAsync(Job job, CancellationToken ct = default);

    // -- Execution CRUD ------------------------------------------------------

    /// <summary>Create a new execution record for a Job.</summary>
    Task<JobExecution> CreateExecutionAsync(JobExecution execution, CancellationToken ct = default);

    /// <summary>Get an execution by ID.</summary>
    Task<JobExecution?> GetExecutionAsync(Guid executionId, CancellationToken ct = default);

    /// <summary>List all executions for a Job, ordered by execution_no.</summary>
    Task<IReadOnlyList<JobExecution>> ListExecutionsAsync(Guid jobId, CancellationToken ct = default);

    /// <summary>Update an execution record (status, timestamps).</summary>
    Task<JobExecution> UpdateExecutionAsync(JobExecution execution, CancellationToken ct = default);

    // -- Step Execution CRUD -------------------------------------------------

    /// <summary>Create a step execution record.</summary>
    Task<JobStepExecution> CreateStepExecutionAsync(JobStepExecution stepExecution, CancellationToken ct = default);

    /// <summary>List step executions for a given execution, ordered by stage_order.</summary>
    Task<IReadOnlyList<JobStepExecution>> ListStepExecutionsAsync(Guid executionId, CancellationToken ct = default);

    /// <summary>Update a step execution (status, output, error).</summary>
    Task<JobStepExecution> UpdateStepExecutionAsync(JobStepExecution stepExecution, CancellationToken ct = default);

    // -- Snapshot ------------------------------------------------------------

    /// <summary>Save an execution snapshot.</summary>
    Task<ExecutionSnapshot> SaveSnapshotAsync(ExecutionSnapshot snapshot, CancellationToken ct = default);

    /// <summary>Get the snapshot for an execution.</summary>
    Task<ExecutionSnapshot?> GetSnapshotAsync(Guid executionId, CancellationToken ct = default);

    // -- Aggregate queries ---------------------------------------------------

    /// <summary>Count Jobs by status for a given pipeline.</summary>
    Task<Dictionary<JobStatus, long>> CountByStatusAsync(Guid pipelineId, CancellationToken ct = default);

    /// <summary>Get the average processing time for completed items in a pipeline.</summary>
    Task<double> GetAverageProcessingTimeAsync(Guid pipelineId, CancellationToken ct = default);
}
```

### 6.15 IEventLogger

```csharp
/// <summary>
/// Structured event logging for execution audit trails.
/// Events are stored in the ExecutionEventLog table and streamed to
/// WebSocket clients for real-time UI updates.
/// </summary>
public interface IEventLogger
{
    /// <summary>
    /// Log a single event during execution.
    /// </summary>
    /// <param name="executionId">The execution this event belongs to.</param>
    /// <param name="level">Severity level.</param>
    /// <param name="eventCode">Machine-readable event code (e.g. "COLLECT_START").</param>
    /// <param name="message">Human-readable message.</param>
    /// <param name="stepExecutionId">Optional: the step this event belongs to.</param>
    /// <param name="detail">Optional: structured payload.</param>
    /// <param name="ct">Cancellation token.</param>
    Task LogAsync(
        Guid executionId,
        EventLevel level,
        string eventCode,
        string message,
        Guid? stepExecutionId = null,
        JsonDocument? detail = null,
        CancellationToken ct = default);

    /// <summary>
    /// Convenience: log an INFO event.
    /// </summary>
    Task InfoAsync(Guid executionId, string eventCode, string message, Guid? stepExecutionId = null, CancellationToken ct = default);

    /// <summary>
    /// Convenience: log a WARN event.
    /// </summary>
    Task WarnAsync(Guid executionId, string eventCode, string message, Guid? stepExecutionId = null, CancellationToken ct = default);

    /// <summary>
    /// Convenience: log an ERROR event.
    /// </summary>
    Task ErrorAsync(Guid executionId, string eventCode, string message, Guid? stepExecutionId = null, JsonDocument? detail = null, CancellationToken ct = default);

    /// <summary>
    /// Retrieve all events for an execution, ordered by timestamp.
    /// </summary>
    /// <param name="executionId">The execution to query.</param>
    /// <param name="level">Optional: filter by minimum severity.</param>
    /// <param name="ct">Cancellation token.</param>
    /// <returns>Ordered list of execution events.</returns>
    Task<IReadOnlyList<ExecutionEventLog>> GetEventsAsync(
        Guid executionId,
        EventLevel? level = null,
        CancellationToken ct = default);

    /// <summary>
    /// Stream events for an execution in real-time.
    /// New events are yielded as they are logged.
    /// </summary>
    IAsyncEnumerable<ExecutionEventLog> StreamEventsAsync(
        Guid executionId,
        CancellationToken ct = default);

    /// <summary>
    /// Get events for a specific step execution.
    /// </summary>
    Task<IReadOnlyList<ExecutionEventLog>> GetStepEventsAsync(
        Guid stepExecutionId,
        CancellationToken ct = default);
}
```

---

## Appendix: Namespace Summary

| Namespace | Contents |
|---|---|
| `Hermes.Domain.Enums` | All enumerations |
| `Hermes.Domain.Entities` | Entity records matching the SQL schema |
| `Hermes.Domain.ValueObjects` | Recipe, DataDescriptor, CollectionStrategy, RetryPolicy, ValidationResult |
| `Hermes.Domain.Events` | Domain events for event-driven architecture |
| `Hermes.Domain.DTOs` | Request/Response DTOs for service methods |
| `Hermes.Domain.Interfaces` | All service interfaces (this section) |
| `Hermes.Plugin.V1` | gRPC-generated types (from hermes_plugin.proto) |
