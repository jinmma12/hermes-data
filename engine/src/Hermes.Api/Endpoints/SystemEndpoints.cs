using Hermes.Api.Options;
using Hermes.Api.Services;
using Microsoft.Extensions.Options;

namespace Hermes.Api.Endpoints;

public static class SystemEndpoints
{
    public static WebApplication MapHermesSystemEndpoints(this WebApplication app)
    {
        app.MapGet("/", () => Results.Ok(new
        {
            name = "Hermes API",
            tagline = "The messenger for your data.",
            version = "0.2.0",
            runtime = ".NET 8",
            docs = "OpenAPI bootstrap pending"
        }));

        app.MapGet("/health/live", () => Results.Ok(new
        {
            status = "ok",
            service = "hermes-api"
        }));

        app.MapGet("/health/ready", () => Results.Ok(new
        {
            status = "ready",
            service = "hermes-api",
            checks = new[]
            {
                "http"
            }
        }));

        var api = app.MapGroup("/api/v1");

        api.MapGet("/system/info", () => Results.Ok(new
        {
            api = "Hermes.Api",
            engine = "Hermes.Engine",
            migration = "Python FastAPI to ASP.NET Core in progress"
        }));

        api.MapGet("/system/database", (IDatabaseBootstrapScriptService scripts) =>
            Results.Ok(scripts.GetDatabaseInfo()));

        api.MapGet("/system/database/bootstrap-script", (
            string? provider,
            string? schema,
            IDatabaseBootstrapScriptService scripts,
            IOptions<DatabaseOptions> options) =>
        {
            try
            {
                var bootstrap = scripts.GetBootstrapScript(
                    provider ?? options.Value.Provider,
                    schema ?? options.Value.Schema);

                return Results.Ok(bootstrap);
            }
            catch (InvalidOperationException ex)
            {
                return Results.BadRequest(new { detail = ex.Message });
            }
            catch (FileNotFoundException ex)
            {
                return Results.Problem(ex.Message);
            }
        });

        return app;
    }
}
