using System.Text.Json.Serialization;

namespace Hermes.Common.Dto;

/// <summary>
/// Shared DTOs for Pipeline entities — used by both REST API and gRPC bridge.
/// These DTOs decouple the transport layer from the domain entities.
/// </summary>

public record PipelineDto(
    Guid Id,
    string Name,
    string? Description,
    string? MonitoringType,
    string MonitoringConfig,
    string Status,
    DateTimeOffset CreatedAt,
    DateTimeOffset UpdatedAt,
    List<PipelineStepDto> Steps);

public record PipelineStepDto(
    Guid Id,
    int StepOrder,
    string StepType,
    string RefType,
    Guid RefId,
    bool IsEnabled,
    string OnError,
    int RetryCount,
    int RetryDelaySeconds);

public record PipelineActivationDto(
    Guid Id,
    Guid PipelineInstanceId,
    string Status,
    DateTimeOffset StartedAt,
    DateTimeOffset? StoppedAt,
    DateTimeOffset? LastHeartbeatAt,
    string? WorkerId);

public record PipelineStatusDto(
    Guid PipelineId,
    string PipelineName,
    string Status,
    int StepCount,
    Guid? ActiveActivationId,
    string? ActivationStatus,
    int ActiveJobs,
    int QueuedJobs,
    long TotalProcessed,
    long TotalFailed);
