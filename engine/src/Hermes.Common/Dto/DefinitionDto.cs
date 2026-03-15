namespace Hermes.Common.Dto;

/// <summary>
/// Shared DTOs for Definition and Instance entities.
/// </summary>

public record DefinitionDto(
    Guid Id,
    string Code,
    string Name,
    string? Description,
    string? Category,
    string? IconUrl,
    string Status,
    int VersionCount);

public record DefinitionVersionDto(
    Guid Id,
    int VersionNo,
    string InputSchema,
    string UiSchema,
    string OutputSchema,
    string DefaultConfig,
    string ExecutionType,
    string? ExecutionRef,
    bool IsPublished,
    DateTimeOffset CreatedAt);

public record InstanceDto(
    Guid Id,
    Guid DefinitionId,
    string Name,
    string? Description,
    string Status,
    int VersionCount);

public record InstanceVersionDto(
    Guid Id,
    int VersionNo,
    string ConfigJson,
    bool IsCurrent,
    string? CreatedBy,
    string? ChangeNote,
    DateTimeOffset CreatedAt);

public record RecipeDiffDto(
    int FromVersion,
    int ToVersion,
    List<DiffEntryDto> Changes);

public record DiffEntryDto(
    string Path,
    string ChangeType,
    string? OldValue,
    string? NewValue);
