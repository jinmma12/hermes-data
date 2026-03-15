namespace Hermes.Api.Contracts;

public sealed record DatabaseInfoDto(
    string Provider,
    string Schema,
    bool UseDocker,
    string ConnectionMode,
    IReadOnlyList<string> SupportedProviders,
    IReadOnlyList<string> BootstrapAssets);

public sealed record BootstrapScriptDto(
    string Provider,
    string Schema,
    string ContentType,
    string Script);
