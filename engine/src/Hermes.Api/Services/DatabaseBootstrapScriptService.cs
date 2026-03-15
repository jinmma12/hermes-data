using Hermes.Api.Contracts;
using Hermes.Api.Options;
using Microsoft.Extensions.Options;

namespace Hermes.Api.Services;

public sealed class DatabaseBootstrapScriptService : IDatabaseBootstrapScriptService
{
    private static readonly string[] SupportedProviders = ["postgres", "sqlserver"];

    private readonly DatabaseOptions _options;
    private readonly IHostEnvironment _environment;

    public DatabaseBootstrapScriptService(IOptions<DatabaseOptions> options, IHostEnvironment environment)
    {
        _options = options.Value;
        _environment = environment;
    }

    public DatabaseInfoDto GetDatabaseInfo()
    {
        var bootstrapAssets = SupportedProviders
            .Select(GetBootstrapAssetPath)
            .ToArray();

        return new DatabaseInfoDto(
            NormalizeProvider(_options.Provider),
            NormalizeSchema(_options.Schema),
            _options.UseDocker,
            _options.UseDocker ? "docker" : "existing",
            SupportedProviders,
            bootstrapAssets);
    }

    public BootstrapScriptDto GetBootstrapScript(string provider, string schema)
    {
        var normalizedProvider = NormalizeProvider(provider);
        var normalizedSchema = NormalizeSchema(schema);

        if (!SupportedProviders.Contains(normalizedProvider, StringComparer.OrdinalIgnoreCase))
        {
            throw new InvalidOperationException($"Unsupported database provider: {provider}");
        }

        var script = normalizedProvider.Equals("sqlserver", StringComparison.OrdinalIgnoreCase)
            ? BuildSqlServerBootstrapScript(normalizedSchema)
            : BuildPostgresBootstrapScript(normalizedSchema);

        return new BootstrapScriptDto(
            normalizedProvider,
            normalizedSchema,
            "application/sql",
            script);
    }

    private string BuildSqlServerBootstrapScript(string schema)
    {
        return
$"""
/*
Hermes SQL Server bootstrap.
Apply this script to an existing database before enabling the Hermes API.
All Hermes-owned tables should live under [{schema}].
*/

IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name = N'{schema}')
BEGIN
    EXEC(N'CREATE SCHEMA [{schema}] AUTHORIZATION dbo;');
END;
GO

/*
Next parity steps:
- create [{schema}].collector_definitions and related tables
- add indexes, unique constraints, and foreign keys
- keep this bootstrap in sync with PostgreSQL init_query.sql and application models
*/
""";
    }

    private string BuildPostgresBootstrapScript(string schema)
    {
        var sourcePath = ResolveBootstrapScriptPath("postgres");
        var body = File.ReadAllText(sourcePath);

        return
$"""
-- Hermes PostgreSQL bootstrap wrapper
CREATE SCHEMA IF NOT EXISTS "{schema}";
SET search_path TO "{schema}", public;

{body}
""";
    }

    private string ResolveBootstrapScriptPath(string provider)
    {
        var asset = GetBootstrapAssetPath(provider);
        var fullPath = Path.GetFullPath(Path.Combine(_environment.ContentRootPath, asset));
        if (!File.Exists(fullPath))
        {
            throw new FileNotFoundException($"Bootstrap asset not found: {fullPath}");
        }

        return fullPath;
    }

    private static string GetBootstrapAssetPath(string provider) => provider.Equals("sqlserver", StringComparison.OrdinalIgnoreCase)
        ? "..\\..\\..\\database\\sqlserver\\init_query.sql"
        : "..\\..\\..\\database\\postgresql\\init_query.sql";

    private static string NormalizeProvider(string provider) =>
        string.IsNullOrWhiteSpace(provider) ? "postgres" : provider.Trim().ToLowerInvariant();

    private static string NormalizeSchema(string schema) =>
        string.IsNullOrWhiteSpace(schema) ? "hermes" : schema.Trim();
}
