namespace Hermes.Api.Options;

public sealed class DatabaseOptions
{
    public const string SectionName = "Database";

    public string Provider { get; set; } = "postgres";

    public string Schema { get; set; } = "hermes";

    public bool UseDocker { get; set; }

    public DatabaseConnectionStrings ConnectionStrings { get; set; } = new();
}

public sealed class DatabaseConnectionStrings
{
    public string Postgres { get; set; } = string.Empty;

    public string SqlServer { get; set; } = string.Empty;
}
