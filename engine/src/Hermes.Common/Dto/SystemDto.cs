namespace Hermes.Common.Dto;

/// <summary>
/// Shared DTOs for system health, metrics, and engine status.
/// </summary>

public record EngineHealthDto(
    string Status,
    long UptimeSeconds,
    int ActivePipelines,
    int JobsProcessing,
    int JobsQueued,
    long MemoryUsedMb,
    int ThreadCount,
    string EngineVersion,
    DateTimeOffset Timestamp);

public record SystemStatsDto(
    int TotalPipelines,
    int ActivePipelines,
    long TotalWorkItems,
    long CompletedWorkItems,
    long FailedWorkItems,
    double SuccessRate);

public record EngineEventDto(
    string EventId,
    string EventType,
    string? PipelineId,
    string? JobId,
    string? ExecutionId,
    DateTimeOffset Timestamp,
    string Message,
    string? DetailJson,
    string Severity);
