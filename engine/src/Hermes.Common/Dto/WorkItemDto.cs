namespace Hermes.Common.Dto;

/// <summary>
/// Shared DTOs for WorkItem (Job) entities — used by both REST API and gRPC bridge.
/// </summary>

public record WorkItemDto(
    Guid Id,
    Guid PipelineInstanceId,
    string SourceType,
    string SourceKey,
    string SourceMetadata,
    string? DedupKey,
    DateTimeOffset DetectedAt,
    string Status,
    int ExecutionCount,
    DateTimeOffset? LastCompletedAt);

public record WorkItemExecutionDto(
    Guid Id,
    Guid WorkItemId,
    int ExecutionNo,
    string TriggerType,
    string? TriggerSource,
    string Status,
    DateTimeOffset StartedAt,
    DateTimeOffset? EndedAt,
    long? DurationMs);

public record StepExecutionDto(
    Guid Id,
    Guid PipelineStepId,
    string StepType,
    int StepOrder,
    string Status,
    DateTimeOffset? StartedAt,
    DateTimeOffset? EndedAt,
    long? DurationMs,
    string? OutputSummary,
    string? ErrorCode,
    string? ErrorMessage);

public record EventLogDto(
    Guid Id,
    string EventType,
    string EventCode,
    string? Message,
    string? DetailJson,
    DateTimeOffset CreatedAt);

public record ReprocessRequestDto(
    Guid Id,
    Guid WorkItemId,
    string RequestedBy,
    string? Reason,
    int? StartFromStep,
    bool UseLatestRecipe,
    string Status,
    Guid? ExecutionId);
