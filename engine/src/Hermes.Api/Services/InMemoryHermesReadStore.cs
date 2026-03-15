using Hermes.Api.Contracts;

namespace Hermes.Api.Services;

public sealed class InMemoryHermesReadStore : IHermesReadStore
{
    private readonly object _lock = new();
    private readonly Dictionary<string, List<DefinitionSummaryDto>> _definitions;
    private readonly Dictionary<string, List<DefinitionVersionDto>> _definitionVersions;
    private readonly Dictionary<string, List<InstanceSummaryDto>> _instances;
    private readonly Dictionary<string, List<RecipeVersionDto>> _recipes;
    private readonly List<PipelineSummaryDto> _pipelines;
    private readonly Dictionary<Guid, List<PipelineStageDto>> _pipelineStages;
    private readonly List<PipelineActivationDto> _activations;
    private readonly List<JobSummaryDto> _jobs;

    public InMemoryHermesReadStore()
    {
        var now = "2026-03-15T00:00:00Z";

        var collectorId = Guid.Parse("11111111-1111-1111-1111-111111111111");
        var sqlServerCollectorId = Guid.Parse("11111111-2222-2222-2222-222222222222");
        var algorithmId = Guid.Parse("22222222-2222-2222-2222-222222222222");
        var transferId = Guid.Parse("33333333-3333-3333-3333-333333333333");

        _definitions = new(StringComparer.OrdinalIgnoreCase)
        {
            ["collectors"] =
            [
                new(collectorId, "rest-api", "REST API Collector", "Collect from REST endpoints", "collection", null, "ACTIVE", now),
                new(sqlServerCollectorId, "sqlserver-table", "SQL Server Table Collector", "Poll rows from an existing SQL Server table using a watermark column", "collection", null, "ACTIVE", now)
            ],
            ["algorithms"] =
            [
                new(algorithmId, "json-transform", "JSON Transform", "Transform JSON payloads", "algorithm", null, "ACTIVE", now)
            ],
            ["transfers"] =
            [
                new(transferId, "file-output", "File Output", "Write processed content to disk", "transfer", null, "ACTIVE", now)
            ]
        };

        _definitionVersions = new(StringComparer.OrdinalIgnoreCase)
        {
            ["collectors"] =
            [
                new(
                    Guid.Parse("aaaaaaaa-1111-1111-1111-111111111111"),
                    collectorId,
                    1,
                    new() { ["url"] = "string", ["method"] = "string" },
                    new() { ["url"] = "text", ["method"] = "select" },
                    new() { ["records"] = "array" },
                    new() { ["method"] = "GET" },
                    "PLUGIN",
                    "builtin.collectors.rest-api",
                    true,
                    now),
                new(
                    Guid.Parse("aaaaaaaa-2222-2222-2222-222222222222"),
                    sqlServerCollectorId,
                    1,
                    new()
                    {
                        ["connection_string"] = "string",
                        ["schema"] = "string",
                        ["table"] = "string",
                        ["watermark_column"] = "string",
                        ["poll_interval_seconds"] = "number"
                    },
                    new()
                    {
                        ["connection_string"] = "password",
                        ["schema"] = "text",
                        ["table"] = "text",
                        ["watermark_column"] = "text",
                        ["poll_interval_seconds"] = "number"
                    },
                    new()
                    {
                        ["rows"] = "array"
                    },
                    new()
                    {
                        ["schema"] = "dbo",
                        ["poll_interval_seconds"] = 30
                    },
                    "PLUGIN",
                    "builtin.collectors.sqlserver-table",
                    true,
                    now)
            ],
            ["algorithms"] =
            [
                new(
                    Guid.Parse("bbbbbbbb-2222-2222-2222-222222222222"),
                    algorithmId,
                    1,
                    new() { ["expression"] = "string" },
                    new() { ["expression"] = "text" },
                    new() { ["transformed"] = "object" },
                    new() { ["expression"] = "{ data }" },
                    "PLUGIN",
                    "builtin.algorithms.json-transform",
                    true,
                    now)
            ],
            ["transfers"] =
            [
                new(
                    Guid.Parse("cccccccc-3333-3333-3333-333333333333"),
                    transferId,
                    1,
                    new() { ["path"] = "string" },
                    new() { ["path"] = "text" },
                    new() { ["written"] = "boolean" },
                    new() { ["path"] = "/tmp/output" },
                    "PLUGIN",
                    "builtin.transfers.file-output",
                    true,
                    now)
            ]
        };

        _instances = new(StringComparer.OrdinalIgnoreCase)
        {
            ["collectors"] =
            [
                new(
                    Guid.Parse("99999999-1111-1111-1111-111111111111"),
                    collectorId,
                    "Vendor Orders Collector",
                    "Prototype collector instance for vendor orders",
                    "ACTIVE",
                    now)
            ],
            ["algorithms"] =
            [
                new(
                    Guid.Parse("99999999-2222-2222-2222-222222222222"),
                    algorithmId,
                    "Vendor Orders Transform",
                    "Prototype algorithm instance",
                    "ACTIVE",
                    now)
            ],
            ["transfers"] =
            [
                new(
                    Guid.Parse("99999999-3333-3333-3333-333333333333"),
                    transferId,
                    "Vendor Orders File Output",
                    "Prototype transfer instance",
                    "ACTIVE",
                    now)
            ]
        };

        _recipes = new(StringComparer.OrdinalIgnoreCase)
        {
            ["collectors"] =
            [
                new(
                    Guid.Parse("12121212-1111-1111-1111-111111111111"),
                    Guid.Parse("99999999-1111-1111-1111-111111111111"),
                    Guid.Parse("aaaaaaaa-1111-1111-1111-111111111111"),
                    1,
                    new()
                    {
                        ["provider"] = "sqlserver",
                        ["connection_string"] = "Server=sql01;Database=legacy_ops;Integrated Security=True;TrustServerCertificate=True",
                        ["schema"] = "dbo",
                        ["table"] = "Orders",
                        ["watermark_column"] = "UpdatedAt",
                        ["poll_interval_seconds"] = 30
                    },
                    new(),
                    true,
                    "system",
                    "Initial SQL Server collector recipe",
                    now)
            ],
            ["algorithms"] =
            [
                new(
                    Guid.Parse("12121212-2222-2222-2222-222222222222"),
                    Guid.Parse("99999999-2222-2222-2222-222222222222"),
                    Guid.Parse("bbbbbbbb-2222-2222-2222-222222222222"),
                    1,
                    new()
                    {
                        ["expression"] = "{ data }"
                    },
                    new(),
                    true,
                    "system",
                    "Initial transform recipe",
                    now)
            ],
            ["transfers"] =
            [
                new(
                    Guid.Parse("12121212-3333-3333-3333-333333333333"),
                    Guid.Parse("99999999-3333-3333-3333-333333333333"),
                    Guid.Parse("cccccccc-3333-3333-3333-333333333333"),
                    1,
                    new()
                    {
                        ["path"] = "C:\\\\Hermes\\\\output"
                    },
                    new(),
                    true,
                    "system",
                    "Initial file output recipe",
                    now)
            ]
        };

        var pipelineId = Guid.Parse("44444444-4444-4444-4444-444444444444");
        var activationId = Guid.Parse("55555555-5555-5555-5555-555555555555");

        var pipeline = new PipelineSummaryDto(
            pipelineId,
            "Order Monitoring",
            "Collect, transform, and transfer vendor order batches",
            "API_POLL",
            new() { ["interval_seconds"] = 60 },
            "ACTIVE",
            now,
            now);

        _pipelines =
        [
            pipeline
        ];

        _pipelineStages = new()
        {
            [pipelineId] =
            [
                new(Guid.Parse("66666666-0000-0000-0000-000000000001"), pipelineId, 1, "COLLECT", "COLLECTOR", collectorId, "REST API Collector", true, "STOP", 0, 0),
                new(Guid.Parse("66666666-0000-0000-0000-000000000002"), pipelineId, 2, "ALGORITHM", "ALGORITHM", algorithmId, "JSON Transform", true, "RETRY", 3, 5),
                new(Guid.Parse("66666666-0000-0000-0000-000000000003"), pipelineId, 3, "TRANSFER", "TRANSFER", transferId, "File Output", true, "STOP", 0, 0)
            ]
        };

        _activations =
        [
            new(
                activationId,
                pipelineId,
                pipeline,
                "RUNNING",
                now,
                null,
                "2026-03-15T00:10:00Z",
                "2026-03-15T00:09:50Z",
                null,
                "worker-1",
                2)
        ];

        _jobs =
        [
            new(
                Guid.Parse("77777777-0000-0000-0000-000000000001"),
                activationId,
                pipelineId,
                pipeline.Name,
                "API_RESPONSE",
                "order_batch_001.json",
                new() { ["source"] = "vendor-a" },
                "order_batch_001",
                "2026-03-15T00:05:00Z",
                "COMPLETED",
                Guid.Parse("88888888-0000-0000-0000-000000000001"),
                1,
                "2026-03-15T00:05:03Z"),
            new(
                Guid.Parse("77777777-0000-0000-0000-000000000002"),
                activationId,
                pipelineId,
                pipeline.Name,
                "API_RESPONSE",
                "order_batch_002.json",
                new() { ["source"] = "vendor-a" },
                "order_batch_002",
                "2026-03-15T00:06:00Z",
                "FAILED",
                Guid.Parse("88888888-0000-0000-0000-000000000002"),
                1,
                null)
        ];
    }

    public IReadOnlyList<DefinitionSummaryDto> ListDefinitions(string kind) =>
        _definitions.TryGetValue(kind, out var definitions) ? definitions : [];

    public DefinitionSummaryDto? GetDefinition(string kind, Guid definitionId) =>
        ListDefinitions(kind).FirstOrDefault(x => x.Id == definitionId);

    public IReadOnlyList<DefinitionVersionDto> ListDefinitionVersions(string kind, Guid definitionId) =>
        _definitionVersions.TryGetValue(kind, out var versions)
            ? versions.Where(x => x.DefinitionId == definitionId).OrderByDescending(x => x.VersionNo).ToArray()
            : [];

    public DefinitionSummaryDto CreateDefinition(string kind, DefinitionCreateRequest request)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        var definition = new DefinitionSummaryDto(
            Guid.NewGuid(),
            request.Code,
            request.Name,
            request.Description,
            request.Category,
            request.IconUrl,
            "DRAFT",
            now);

        lock (_lock)
        {
            if (!_definitions.TryGetValue(kind, out var definitions))
            {
                throw new InvalidOperationException($"Unknown definition type: {kind}");
            }

            if (definitions.Any(x => x.Code.Equals(request.Code, StringComparison.OrdinalIgnoreCase)))
            {
                throw new InvalidOperationException($"Definition code already exists: {request.Code}");
            }

            definitions.Add(definition);

            if (_definitionVersions.TryGetValue(kind, out var versions))
            {
                versions.Add(new DefinitionVersionDto(
                    Guid.NewGuid(),
                    definition.Id,
                    1,
                    [],
                    [],
                    [],
                    [],
                    "PLUGIN",
                    null,
                    false,
                    now));
            }
        }

        return definition;
    }

    public IReadOnlyList<InstanceSummaryDto> ListInstances(string kind) =>
        _instances.TryGetValue(kind, out var instances) ? instances : [];

    public InstanceSummaryDto? GetInstance(string kind, Guid instanceId) =>
        ListInstances(kind).FirstOrDefault(x => x.Id == instanceId);

    public InstanceSummaryDto CreateInstance(string kind, InstanceCreateRequest request)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        var instance = new InstanceSummaryDto(
            Guid.NewGuid(),
            request.DefinitionId,
            request.Name,
            request.Description,
            "DRAFT",
            now);

        lock (_lock)
        {
            if (!_instances.TryGetValue(kind, out var instances))
            {
                throw new InvalidOperationException($"Unknown instance type: {kind}");
            }

            instances.Add(instance);
            if (_recipes.TryGetValue(kind, out var recipes))
            {
                recipes.Add(new RecipeVersionDto(
                    Guid.NewGuid(),
                    instance.Id,
                    Guid.Empty,
                    1,
                    new(),
                    new(),
                    true,
                    "system",
                    "Initial empty recipe",
                    now));
            }
        }

        return instance;
    }

    public IReadOnlyList<RecipeVersionDto> ListRecipes(string kind, Guid instanceId) =>
        _recipes.TryGetValue(kind, out var recipes)
            ? recipes.Where(x => x.InstanceId == instanceId).OrderByDescending(x => x.VersionNo).ToArray()
            : [];

    public RecipeVersionDto CreateRecipe(string kind, Guid instanceId, RecipeCreateRequest request)
    {
        lock (_lock)
        {
            if (!_recipes.TryGetValue(kind, out var recipes))
            {
                throw new InvalidOperationException($"Unknown instance type: {kind}");
            }

            var currentVersions = recipes.Where(x => x.InstanceId == instanceId).ToArray();
            if (currentVersions.Length == 0)
            {
                throw new KeyNotFoundException("Instance not found");
            }

            var nextVersion = currentVersions.Max(x => x.VersionNo) + 1;
            for (var i = 0; i < recipes.Count; i++)
            {
                if (recipes[i].InstanceId == instanceId && recipes[i].IsCurrent)
                {
                    recipes[i] = recipes[i] with { IsCurrent = false };
                }
            }

            var recipe = new RecipeVersionDto(
                Guid.NewGuid(),
                instanceId,
                currentVersions[0].DefVersionId,
                nextVersion,
                request.ConfigJson,
                new(),
                true,
                request.CreatedBy,
                request.ChangeNote,
                DateTimeOffset.UtcNow.ToString("O"));

            recipes.Add(recipe);
            return recipe;
        }
    }

    public IReadOnlyList<PipelineSummaryDto> ListPipelines() => _pipelines;

    public PipelineSummaryDto? GetPipeline(Guid pipelineId) =>
        _pipelines.FirstOrDefault(x => x.Id == pipelineId);

    public PipelineSummaryDto CreatePipeline(PipelineCreateRequest request)
    {
        var now = DateTimeOffset.UtcNow.ToString("O");
        var pipeline = new PipelineSummaryDto(
            Guid.NewGuid(),
            request.Name,
            request.Description,
            request.MonitoringType,
            request.MonitoringConfig,
            "DRAFT",
            now,
            now);

        lock (_lock)
        {
            _pipelines.Add(pipeline);
            _pipelineStages[pipeline.Id] = [];
        }

        return pipeline;
    }

    public IReadOnlyList<PipelineStageDto> ListPipelineStages(Guid pipelineId) =>
        _pipelineStages.TryGetValue(pipelineId, out var stages) ? stages : [];

    public PipelineStageDto CreatePipelineStage(Guid pipelineId, PipelineStageCreateRequest request)
    {
        lock (_lock)
        {
            if (!_pipelineStages.TryGetValue(pipelineId, out var stages))
            {
                throw new KeyNotFoundException("Pipeline not found");
            }

            var nextOrder = request.StageOrder ?? (stages.Count == 0 ? 1 : stages.Max(x => x.StageOrder) + 1);
            var stage = new PipelineStageDto(
                Guid.NewGuid(),
                pipelineId,
                nextOrder,
                request.StageType,
                request.RefType,
                request.RefId,
                null,
                true,
                request.OnError,
                request.RetryCount,
                request.RetryDelaySeconds);

            stages.Add(stage);
            return stage;
        }
    }

    public PipelineActivationDto ActivatePipeline(Guid pipelineId)
    {
        lock (_lock)
        {
            var pipelineIndex = _pipelines.FindIndex(x => x.Id == pipelineId);
            if (pipelineIndex < 0)
            {
                throw new KeyNotFoundException("Pipeline not found");
            }

            var pipeline = _pipelines[pipelineIndex] with
            {
                Status = "ACTIVE",
                UpdatedAt = DateTimeOffset.UtcNow.ToString("O")
            };
            _pipelines[pipelineIndex] = pipeline;

            var activation = new PipelineActivationDto(
                Guid.NewGuid(),
                pipelineId,
                pipeline,
                "RUNNING",
                DateTimeOffset.UtcNow.ToString("O"),
                null,
                DateTimeOffset.UtcNow.ToString("O"),
                null,
                null,
                "worker-1",
                0);

            _activations.Add(activation);
            return activation;
        }
    }

    public PipelineActivationDto DeactivatePipeline(Guid pipelineId)
    {
        lock (_lock)
        {
            var pipelineIndex = _pipelines.FindIndex(x => x.Id == pipelineId);
            if (pipelineIndex < 0)
            {
                throw new KeyNotFoundException("Pipeline not found");
            }

            var pipeline = _pipelines[pipelineIndex] with
            {
                Status = "PAUSED",
                UpdatedAt = DateTimeOffset.UtcNow.ToString("O")
            };
            _pipelines[pipelineIndex] = pipeline;

            var activationIndex = _activations.FindLastIndex(x =>
                x.PipelineInstanceId == pipelineId &&
                x.Status == "RUNNING");

            if (activationIndex < 0)
            {
                throw new InvalidOperationException("Pipeline is not running");
            }

            var stoppedAt = DateTimeOffset.UtcNow.ToString("O");
            var stoppedActivation = _activations[activationIndex] with
            {
                Status = "STOPPED",
                StoppedAt = stoppedAt,
                LastHeartbeatAt = stoppedAt
            };

            _activations[activationIndex] = stoppedActivation;
            return stoppedActivation;
        }
    }

    public PaginatedResponseDto<JobSummaryDto> ListJobs(int page, int pageSize)
    {
        var items = _jobs
            .OrderByDescending(x => x.DetectedAt)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .ToArray();

        return new PaginatedResponseDto<JobSummaryDto>(items, _jobs.Count, page, pageSize);
    }

    public JobSummaryDto? GetJob(Guid jobId) =>
        _jobs.FirstOrDefault(x => x.Id == jobId);

    public MonitorStatsDto GetMonitorStats()
    {
        var completed = _jobs.Count(x => x.Status == "COMPLETED");
        var failed = _jobs.Count(x => x.Status == "FAILED");
        var successRate = _jobs.Count == 0 ? 0.0 : Math.Round((double)completed / _jobs.Count * 100.0, 1);

        return new MonitorStatsDto(
            _jobs.Count,
            completed,
            failed,
            successRate,
            2500,
            _activations.Count(x => x.Status == "RUNNING"));
    }

    public IReadOnlyList<PipelineActivationDto> ListMonitorActivations() => _activations;

    public IReadOnlyList<JobSummaryDto> ListRecentJobs(int limit) =>
        _jobs.OrderByDescending(x => x.DetectedAt).Take(limit).ToArray();
}
