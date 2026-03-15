using Hermes.Api.Contracts;

namespace Hermes.Api.Services;

public interface IHermesReadStore
{
    IReadOnlyList<DefinitionSummaryDto> ListDefinitions(string kind);
    DefinitionSummaryDto? GetDefinition(string kind, Guid definitionId);
    IReadOnlyList<DefinitionVersionDto> ListDefinitionVersions(string kind, Guid definitionId);
    DefinitionSummaryDto CreateDefinition(string kind, DefinitionCreateRequest request);
    IReadOnlyList<InstanceSummaryDto> ListInstances(string kind);
    InstanceSummaryDto? GetInstance(string kind, Guid instanceId);
    InstanceSummaryDto CreateInstance(string kind, InstanceCreateRequest request);
    IReadOnlyList<RecipeVersionDto> ListRecipes(string kind, Guid instanceId);
    RecipeVersionDto CreateRecipe(string kind, Guid instanceId, RecipeCreateRequest request);
    IReadOnlyList<PipelineSummaryDto> ListPipelines();
    PipelineSummaryDto? GetPipeline(Guid pipelineId);
    PipelineSummaryDto CreatePipeline(PipelineCreateRequest request);
    IReadOnlyList<PipelineStageDto> ListPipelineStages(Guid pipelineId);
    PipelineStageDto CreatePipelineStage(Guid pipelineId, PipelineStageCreateRequest request);
    PipelineActivationDto ActivatePipeline(Guid pipelineId);
    PipelineActivationDto DeactivatePipeline(Guid pipelineId);
    PaginatedResponseDto<JobSummaryDto> ListJobs(int page, int pageSize);
    JobSummaryDto? GetJob(Guid jobId);
    MonitorStatsDto GetMonitorStats();
    IReadOnlyList<PipelineActivationDto> ListMonitorActivations();
    IReadOnlyList<JobSummaryDto> ListRecentJobs(int limit);
}
