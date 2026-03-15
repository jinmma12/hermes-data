using Hermes.Api.Contracts;
using Hermes.Api.Services;

namespace Hermes.Api.Endpoints;

public static class InstanceEndpoints
{
    private static readonly HashSet<string> InstanceKinds = new(StringComparer.OrdinalIgnoreCase)
    {
        "collectors",
        "algorithms",
        "transfers"
    };

    public static WebApplication MapHermesInstanceEndpoints(this WebApplication app)
    {
        var api = app.MapGroup("/api/v1/instances");

        api.MapGet("/{kind}", (string kind, IHermesReadStore store) =>
        {
            if (!InstanceKinds.Contains(kind))
            {
                return Results.NotFound(new { detail = $"Unknown instance type: {kind}" });
            }

            return Results.Ok(store.ListInstances(kind));
        });

        api.MapPost("/{kind}", (string kind, InstanceCreateRequest request, IHermesReadStore store) =>
        {
            if (!InstanceKinds.Contains(kind))
            {
                return Results.NotFound(new { detail = $"Unknown instance type: {kind}" });
            }

            try
            {
                var instance = store.CreateInstance(kind, request);
                return Results.Created($"/api/v1/instances/{kind}/{instance.Id}", instance);
            }
            catch (InvalidOperationException ex)
            {
                return Results.BadRequest(new { detail = ex.Message });
            }
        });

        api.MapGet("/{kind}/{instanceId:guid}", (string kind, Guid instanceId, IHermesReadStore store) =>
        {
            if (!InstanceKinds.Contains(kind))
            {
                return Results.NotFound(new { detail = $"Unknown instance type: {kind}" });
            }

            var instance = store.GetInstance(kind, instanceId);
            return instance is null ? Results.NotFound(new { detail = "Instance not found" }) : Results.Ok(instance);
        });

        api.MapGet("/{kind}/{instanceId:guid}/recipes", (string kind, Guid instanceId, IHermesReadStore store) =>
        {
            if (!InstanceKinds.Contains(kind))
            {
                return Results.NotFound(new { detail = $"Unknown instance type: {kind}" });
            }

            return Results.Ok(store.ListRecipes(kind, instanceId));
        });

        api.MapPost("/{kind}/{instanceId:guid}/recipes", (string kind, Guid instanceId, RecipeCreateRequest request, IHermesReadStore store) =>
        {
            if (!InstanceKinds.Contains(kind))
            {
                return Results.NotFound(new { detail = $"Unknown instance type: {kind}" });
            }

            try
            {
                var recipe = store.CreateRecipe(kind, instanceId, request);
                return Results.Created($"/api/v1/instances/{kind}/{instanceId}/recipes/{recipe.VersionNo}", recipe);
            }
            catch (KeyNotFoundException)
            {
                return Results.NotFound(new { detail = "Instance not found" });
            }
        });

        return app;
    }
}
