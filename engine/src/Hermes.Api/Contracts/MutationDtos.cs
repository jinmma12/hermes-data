namespace Hermes.Api.Contracts;

public sealed record DefinitionCreateRequest(
    string Code,
    string Name,
    string? Description,
    string? Category,
    string? IconUrl);

public sealed record PipelineCreateRequest(
    string Name,
    string? Description,
    string MonitoringType,
    Dictionary<string, object?> MonitoringConfig);

public sealed record PipelineStageCreateRequest(
    string StageType,
    string RefType,
    Guid RefId,
    int? StageOrder,
    string OnError,
    int RetryCount,
    int RetryDelaySeconds);
