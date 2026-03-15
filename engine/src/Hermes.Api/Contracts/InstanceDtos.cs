namespace Hermes.Api.Contracts;

public sealed record InstanceSummaryDto(
    Guid Id,
    Guid DefinitionId,
    string Name,
    string? Description,
    string Status,
    string CreatedAt);

public sealed record RecipeVersionDto(
    Guid Id,
    Guid InstanceId,
    Guid DefVersionId,
    int VersionNo,
    Dictionary<string, object?> ConfigJson,
    Dictionary<string, object?> SecretBindingJson,
    bool IsCurrent,
    string? CreatedBy,
    string? ChangeNote,
    string CreatedAt);

public sealed record InstanceCreateRequest(
    Guid DefinitionId,
    string Name,
    string? Description);

public sealed record RecipeCreateRequest(
    Dictionary<string, object?> ConfigJson,
    string? ChangeNote,
    string? CreatedBy);
