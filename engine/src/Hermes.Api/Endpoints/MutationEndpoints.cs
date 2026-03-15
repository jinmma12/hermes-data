using Hermes.Api.Contracts;
using Hermes.Api.Services;

namespace Hermes.Api.Endpoints;

public static class MutationEndpoints
{
    private static readonly HashSet<string> DefinitionKinds = new(StringComparer.OrdinalIgnoreCase)
    {
        "collectors",
        "algorithms",
        "transfers"
    };

    public static WebApplication MapHermesMutationEndpoints(this WebApplication app)
    {
        var api = app.MapGroup("/api/v1");

        api.MapPost("/definitions/{kind}", (string kind, DefinitionCreateRequest request, IHermesReadStore store) =>
        {
            if (!DefinitionKinds.Contains(kind))
            {
                return Results.NotFound(new { detail = $"Unknown definition type: {kind}" });
            }

            try
            {
                var definition = store.CreateDefinition(kind, request);
                return Results.Created($"/api/v1/definitions/{kind}/{definition.Id}", definition);
            }
            catch (InvalidOperationException ex)
            {
                return Results.BadRequest(new { detail = ex.Message });
            }
        });

        api.MapPost("/pipelines", (PipelineCreateRequest request, IHermesReadStore store) =>
        {
            var pipeline = store.CreatePipeline(request);
            return Results.Created($"/api/v1/pipelines/{pipeline.Id}", pipeline);
        });

        api.MapPost("/pipelines/{pipelineId:guid}/stages", (Guid pipelineId, PipelineStageCreateRequest request, IHermesReadStore store) =>
        {
            try
            {
                var stage = store.CreatePipelineStage(pipelineId, request);
                return Results.Created($"/api/v1/pipelines/{pipelineId}/stages", stage);
            }
            catch (KeyNotFoundException)
            {
                return Results.NotFound(new { detail = "Pipeline not found" });
            }
        });

        api.MapPost("/pipelines/{pipelineId:guid}/activate", (Guid pipelineId, IHermesReadStore store) =>
        {
            try
            {
                var activation = store.ActivatePipeline(pipelineId);
                return Results.Ok(activation);
            }
            catch (KeyNotFoundException)
            {
                return Results.NotFound(new { detail = "Pipeline not found" });
            }
        });

        api.MapPost("/pipelines/{pipelineId:guid}/deactivate", (Guid pipelineId, IHermesReadStore store) =>
        {
            try
            {
                var activation = store.DeactivatePipeline(pipelineId);
                return Results.Ok(activation);
            }
            catch (KeyNotFoundException)
            {
                return Results.NotFound(new { detail = "Pipeline not found" });
            }
            catch (InvalidOperationException ex)
            {
                return Results.BadRequest(new { detail = ex.Message });
            }
        });

        return app;
    }
}
