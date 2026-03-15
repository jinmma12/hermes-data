# Hermes .NET 8 Solution Design

> Production-ready Clean Architecture blueprint for the Hermes data processing platform.
> Target: .NET 8 LTS, C# 12, open-source (Apache 2.0).

---

## 1. Solution Structure

```
Hermes.sln
├── src/
│   ├── Hermes.Domain/
│   ├── Hermes.Application/
│   ├── Hermes.Infrastructure/
│   ├── Hermes.Api/
│   ├── Hermes.Worker/
│   ├── Hermes.Plugins.Sdk/
│   └── Hermes.Shared/
├── tests/
│   ├── Hermes.Domain.Tests/
│   ├── Hermes.Application.Tests/
│   ├── Hermes.Infrastructure.Tests/
│   ├── Hermes.Api.Tests/
│   ├── Hermes.Worker.Tests/
│   └── Hermes.IntegrationTests/
├── plugins/
│   ├── Hermes.Plugin.RestApiCollector/
│   ├── Hermes.Plugin.FileWatcherCollector/
│   ├── Hermes.Plugin.DbQueryCollector/
│   ├── Hermes.Plugin.KafkaCollector/
│   ├── Hermes.Plugin.Passthrough/
│   ├── Hermes.Plugin.JsonTransform/
│   ├── Hermes.Plugin.FileTransfer/
│   └── Hermes.Plugin.RestApiTransfer/
├── protos/
│   └── hermes/
│       ├── plugin_service.proto
│       └── plugin_messages.proto
├── docker/
│   ├── Dockerfile.api
│   ├── Dockerfile.worker
│   └── docker-compose.yml
└── docs/
```

---

## 2. Project Details

### 2.1 Hermes.Domain

**Purpose**: Core business entities, value objects, enums, interfaces. Zero external dependencies.

**Framework**: `net8.0` (class library)

**Dependencies**: None. This project references no other project and no NuGet packages beyond the SDK.

**Namespace Structure**:
```
Hermes.Domain
├── Entities/
│   ├── Definitions/
│   │   ├── CollectorDefinition.cs
│   │   ├── CollectorDefinitionVersion.cs
│   │   ├── AlgorithmDefinition.cs
│   │   ├── AlgorithmDefinitionVersion.cs
│   │   ├── TransferDefinition.cs
│   │   └── TransferDefinitionVersion.cs
│   ├── Instances/
│   │   ├── CollectorInstance.cs
│   │   ├── CollectorInstanceVersion.cs
│   │   ├── AlgorithmInstance.cs
│   │   ├── AlgorithmInstanceVersion.cs
│   │   ├── TransferInstance.cs
│   │   └── TransferInstanceVersion.cs
│   ├── Pipelines/
│   │   ├── PipelineInstance.cs
│   │   ├── PipelineStage.cs
│   │   └── PipelineActivation.cs
│   ├── Execution/
│   │   ├── Job.cs
│   │   ├── JobExecution.cs
│   │   ├── JobStepExecution.cs
│   │   ├── ExecutionSnapshot.cs
│   │   ├── ExecutionEventLog.cs
│   │   └── ReprocessRequest.cs
│   ├── Plugins/
│   │   └── PluginRegistryEntry.cs
│   └── System/
│       ├── DeadLetterEntry.cs
│       └── SchemaVersion.cs
├── ValueObjects/
│   ├── Recipe.cs
│   ├── DataDescriptor.cs
│   ├── CollectionStrategy.cs
│   ├── MonitoringConfig.cs
│   ├── SourceMetadata.cs
│   └── SecretBinding.cs
├── Enums/
│   ├── DefinitionStatus.cs
│   ├── ExecutionType.cs
│   ├── InstanceStatus.cs
│   ├── PipelineStatus.cs
│   ├── MonitoringType.cs
│   ├── StageType.cs
│   ├── RefType.cs
│   ├── OnErrorAction.cs
│   ├── ActivationStatus.cs
│   ├── SourceType.cs
│   ├── JobStatus.cs
│   ├── TriggerType.cs
│   ├── ExecutionStatus.cs
│   ├── StepExecutionStatus.cs
│   ├── ReprocessStatus.cs
│   ├── EventLevel.cs
│   └── PluginStatus.cs
├── Events/
│   ├── JobCreatedEvent.cs
│   ├── JobCompletedEvent.cs
│   ├── JobFailedEvent.cs
│   ├── RecipeChangedEvent.cs
│   ├── PipelineActivatedEvent.cs
│   ├── PipelineDeactivatedEvent.cs
│   └── StepExecutionCompletedEvent.cs
├── Interfaces/
│   ├── IRepository.cs
│   ├── IUnitOfWork.cs
│   └── IDomainEvent.cs
├── Exceptions/
│   ├── HermesDomainException.cs
│   ├── RecipeValidationException.cs
│   └── PipelineConfigurationException.cs
└── Common/
    ├── BaseEntity.cs
    ├── AuditableEntity.cs
    └── ValueObject.cs
```

**Key Classes**:

```csharp
// --- Base Types ---

public abstract class BaseEntity
{
    public Guid Id { get; protected set; } = Guid.NewGuid();
    private readonly List<IDomainEvent> _domainEvents = new();
    public IReadOnlyList<IDomainEvent> DomainEvents => _domainEvents.AsReadOnly();
    public void AddDomainEvent(IDomainEvent e) => _domainEvents.Add(e);
    public void ClearDomainEvents() => _domainEvents.Clear();
}

public abstract class AuditableEntity : BaseEntity
{
    public DateTimeOffset CreatedAt { get; set; }
    public DateTimeOffset UpdatedAt { get; set; }
}

public interface IDomainEvent
{
    DateTimeOffset OccurredAt { get; }
}

public interface IRepository<T> where T : BaseEntity
{
    Task<T?> GetByIdAsync(Guid id, CancellationToken ct = default);
    Task<IReadOnlyList<T>> ListAllAsync(CancellationToken ct = default);
    Task<T> AddAsync(T entity, CancellationToken ct = default);
    Task UpdateAsync(T entity, CancellationToken ct = default);
    Task DeleteAsync(T entity, CancellationToken ct = default);
}

public interface IUnitOfWork : IDisposable
{
    Task<int> SaveChangesAsync(CancellationToken ct = default);
}

// --- Definition Layer ---

public class CollectorDefinition : AuditableEntity
{
    public string Code { get; set; } = string.Empty;
    public string Name { get; set; } = string.Empty;
    public string? Description { get; set; }
    public string? Category { get; set; }
    public string? IconUrl { get; set; }
    public DefinitionStatus Status { get; set; } = DefinitionStatus.Draft;
    public ICollection<CollectorDefinitionVersion> Versions { get; set; } = new List<CollectorDefinitionVersion>();
}

public class CollectorDefinitionVersion : BaseEntity
{
    public Guid DefinitionId { get; set; }
    public int VersionNo { get; set; }
    public JsonDocument InputSchema { get; set; } = JsonDocument.Parse("{}");
    public JsonDocument UiSchema { get; set; } = JsonDocument.Parse("{}");
    public JsonDocument OutputSchema { get; set; } = JsonDocument.Parse("{}");
    public JsonDocument DefaultConfig { get; set; } = JsonDocument.Parse("{}");
    public ExecutionType ExecutionType { get; set; }
    public string? ExecutionRef { get; set; }
    public bool IsPublished { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public CollectorDefinition Definition { get; set; } = null!;
}

// AlgorithmDefinition, AlgorithmDefinitionVersion — identical pattern
// TransferDefinition, TransferDefinitionVersion — identical pattern

// --- Instance Layer ---

public class CollectorInstance : AuditableEntity
{
    public Guid DefinitionId { get; set; }
    public string Name { get; set; } = string.Empty;
    public string? Description { get; set; }
    public InstanceStatus Status { get; set; } = InstanceStatus.Draft;
    public CollectorDefinition Definition { get; set; } = null!;
    public ICollection<CollectorInstanceVersion> Versions { get; set; } = new List<CollectorInstanceVersion>();
    public CollectorInstanceVersion? CurrentVersion =>
        Versions.FirstOrDefault(v => v.IsCurrent);
}

public class CollectorInstanceVersion : BaseEntity
{
    public Guid InstanceId { get; set; }
    public Guid DefVersionId { get; set; }
    public int VersionNo { get; set; }
    public JsonDocument ConfigJson { get; set; } = JsonDocument.Parse("{}");
    public JsonDocument SecretBindingJson { get; set; } = JsonDocument.Parse("{}");
    public bool IsCurrent { get; set; }
    public string? CreatedBy { get; set; }
    public string? ChangeNote { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public CollectorInstance Instance { get; set; } = null!;
    public CollectorDefinitionVersion DefVersion { get; set; } = null!;
}

// AlgorithmInstance / AlgorithmInstanceVersion — identical pattern
// TransferInstance / TransferInstanceVersion — identical pattern

// --- Pipeline Layer ---

public class PipelineInstance : AuditableEntity
{
    public string Name { get; set; } = string.Empty;
    public string? Description { get; set; }
    public MonitoringType? MonitoringType { get; set; }
    public JsonDocument MonitoringConfig { get; set; } = JsonDocument.Parse("{}");
    public PipelineStatus Status { get; set; } = PipelineStatus.Draft;
    public ICollection<PipelineStage> Steps { get; set; } = new List<PipelineStage>();
    public ICollection<PipelineActivation> Activations { get; set; } = new List<PipelineActivation>();
}

public class PipelineStage : BaseEntity
{
    public Guid PipelineInstanceId { get; set; }
    public int StepOrder { get; set; }
    public StageType StageType { get; set; }
    public RefType RefType { get; set; }
    public Guid RefId { get; set; }
    public bool IsEnabled { get; set; } = true;
    public OnErrorAction OnError { get; set; } = OnErrorAction.Stop;
    public int RetryCount { get; set; }
    public int RetryDelaySeconds { get; set; }
    public PipelineInstance Pipeline { get; set; } = null!;
}

public class PipelineActivation : BaseEntity
{
    public Guid PipelineInstanceId { get; set; }
    public ActivationStatus Status { get; set; } = ActivationStatus.Starting;
    public DateTimeOffset StartedAt { get; set; }
    public DateTimeOffset? StoppedAt { get; set; }
    public DateTimeOffset? LastHeartbeatAt { get; set; }
    public DateTimeOffset? LastPolledAt { get; set; }
    public string? ErrorMessage { get; set; }
    public string? WorkerId { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public PipelineInstance Pipeline { get; set; } = null!;
    public ICollection<Job> Jobs { get; set; } = new List<Job>();
}

// --- Execution Layer ---

public class Job : AuditableEntity
{
    public Guid PipelineActivationId { get; set; }
    public Guid PipelineInstanceId { get; set; }
    public SourceType SourceType { get; set; }
    public string SourceKey { get; set; } = string.Empty;
    public JsonDocument SourceMetadata { get; set; } = JsonDocument.Parse("{}");
    public string? DedupKey { get; set; }
    public DateTimeOffset DetectedAt { get; set; }
    public JobStatus Status { get; set; } = JobStatus.Detected;
    public Guid? CurrentExecutionId { get; set; }
    public int ExecutionCount { get; set; }
    public DateTimeOffset? LastCompletedAt { get; set; }
    public PipelineActivation Activation { get; set; } = null!;
    public PipelineInstance Pipeline { get; set; } = null!;
    public JobExecution? CurrentExecution { get; set; }
    public ICollection<JobExecution> Executions { get; set; } = new List<JobExecution>();
}

public class JobExecution : BaseEntity
{
    public Guid JobId { get; set; }
    public int ExecutionNo { get; set; }
    public TriggerType TriggerType { get; set; } = TriggerType.Initial;
    public string? TriggerSource { get; set; }
    public ExecutionStatus Status { get; set; } = ExecutionStatus.Running;
    public DateTimeOffset StartedAt { get; set; }
    public DateTimeOffset? EndedAt { get; set; }
    public long? DurationMs { get; set; }
    public Guid? ReprocessRequestId { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public Job Job { get; set; } = null!;
    public ExecutionSnapshot? Snapshot { get; set; }
    public ICollection<JobStepExecution> StepExecutions { get; set; } = new List<JobStepExecution>();
}

public class JobStepExecution : BaseEntity
{
    public Guid ExecutionId { get; set; }
    public Guid PipelineStageId { get; set; }
    public StageType StageType { get; set; }
    public int StepOrder { get; set; }
    public StepExecutionStatus Status { get; set; } = StepExecutionStatus.Pending;
    public DateTimeOffset? StartedAt { get; set; }
    public DateTimeOffset? EndedAt { get; set; }
    public long? DurationMs { get; set; }
    public JsonDocument? InputSummary { get; set; }
    public JsonDocument? OutputSummary { get; set; }
    public string? ErrorCode { get; set; }
    public string? ErrorMessage { get; set; }
    public int RetryAttempt { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public JobExecution Execution { get; set; } = null!;
    public PipelineStage PipelineStage { get; set; } = null!;
}

public class ExecutionSnapshot : BaseEntity
{
    public Guid ExecutionId { get; set; }
    public JsonDocument PipelineConfig { get; set; } = JsonDocument.Parse("{}");
    public JsonDocument CollectorConfig { get; set; } = JsonDocument.Parse("{}");
    public JsonDocument AlgorithmConfig { get; set; } = JsonDocument.Parse("{}");
    public JsonDocument TransferConfig { get; set; } = JsonDocument.Parse("{}");
    public string? SnapshotHash { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public JobExecution Execution { get; set; } = null!;
}

public class ExecutionEventLog : BaseEntity
{
    public Guid ExecutionId { get; set; }
    public Guid? StepExecutionId { get; set; }
    public EventLevel EventType { get; set; } = EventLevel.Info;
    public string EventCode { get; set; } = string.Empty;
    public string? Message { get; set; }
    public JsonDocument? DetailJson { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
    public JobExecution Execution { get; set; } = null!;
    public JobStepExecution? StepExecution { get; set; }
}

public class ReprocessRequest : AuditableEntity
{
    public Guid JobId { get; set; }
    public string RequestedBy { get; set; } = string.Empty;
    public DateTimeOffset RequestedAt { get; set; }
    public string? Reason { get; set; }
    public int? StartFromStep { get; set; }
    public bool UseLatestRecipe { get; set; } = true;
    public ReprocessStatus Status { get; set; } = ReprocessStatus.Pending;
    public string? ApprovedBy { get; set; }
    public Guid? ExecutionId { get; set; }
    public Job Job { get; set; } = null!;
    public JobExecution? Execution { get; set; }
}

// --- New from benchmark gaps ---

public class DeadLetterEntry : BaseEntity
{
    public Guid? JobId { get; set; }
    public Guid? ExecutionId { get; set; }
    public Guid? PipelineInstanceId { get; set; }
    public string ErrorCode { get; set; } = string.Empty;
    public string ErrorMessage { get; set; } = string.Empty;
    public JsonDocument? PayloadJson { get; set; }
    public int RetryCount { get; set; }
    public DateTimeOffset? LastRetryAt { get; set; }
    public DateTimeOffset CreatedAt { get; set; }
}

public class SchemaVersion : BaseEntity
{
    public string SchemaName { get; set; } = string.Empty;
    public int Version { get; set; }
    public string Checksum { get; set; } = string.Empty;
    public DateTimeOffset AppliedAt { get; set; }
}

public class PluginRegistryEntry : AuditableEntity
{
    public string PluginCode { get; set; } = string.Empty;
    public string PluginName { get; set; } = string.Empty;
    public RefType PluginType { get; set; }
    public string Version { get; set; } = string.Empty;
    public string? Description { get; set; }
    public string? Author { get; set; }
    public string? HomepageUrl { get; set; }
    public string? RepositoryUrl { get; set; }
    public string? IconUrl { get; set; }
    public PluginStatus Status { get; set; } = PluginStatus.Installed;
    public string? InstallPath { get; set; }
    public JsonDocument ManifestJson { get; set; } = JsonDocument.Parse("{}");
    public DateTimeOffset InstalledAt { get; set; }
}
```

**Enums (all in `Hermes.Domain.Enums`)**:
```csharp
public enum DefinitionStatus { Draft, Active, Deprecated, Archived }
public enum ExecutionType { Plugin, Script, Http, Docker, NifiFlow }
public enum InstanceStatus { Draft, Active, Disabled, Archived }
public enum PipelineStatus { Draft, Active, Paused, Archived }
public enum MonitoringType { FileMonitor, ApiPoll, DbPoll, EventStream }
public enum StageType { Collect, Algorithm, Transfer }
public enum RefType { Collector, Algorithm, Transfer }
public enum OnErrorAction { Stop, Skip, Retry }
public enum ActivationStatus { Starting, Running, Stopping, Stopped, Error }
public enum SourceType { File, ApiResponse, DbChange, Event }
public enum JobStatus { Detected, Queued, Processing, Completed, Failed }
public enum TriggerType { Initial, Retry, Reprocess }
public enum ExecutionStatus { Running, Completed, Failed, Cancelled }
public enum StepExecutionStatus { Pending, Running, Completed, Failed, Skipped }
public enum ReprocessStatus { Pending, Approved, Executing, Done, Rejected }
public enum EventLevel { Debug, Info, Warn, Error }
public enum PluginStatus { Installed, Active, Disabled, Uninstalled }
```

**NuGet Packages**: None.

---

### 2.2 Hermes.Application

**Purpose**: Use cases, CQRS commands/queries, DTOs, service interfaces, validators, mapping profiles.

**References**: `Hermes.Domain`, `Hermes.Shared`

**Namespace Structure**:
```
Hermes.Application
├── Common/
│   ├── Behaviors/
│   │   ├── LoggingBehavior.cs
│   │   ├── ValidationBehavior.cs
│   │   └── PerformanceBehavior.cs
│   ├── Interfaces/
│   │   ├── IPipelineManager.cs
│   │   ├── IRecipeEngine.cs
│   │   ├── IMonitoringEngine.cs
│   │   ├── IProcessingOrchestrator.cs
│   │   ├── IExecutionDispatcher.cs
│   │   ├── ISnapshotResolver.cs
│   │   ├── IConditionEvaluator.cs
│   │   ├── ISchemaRegistry.cs
│   │   ├── IBackPressureManager.cs
│   │   ├── ICircuitBreakerManager.cs
│   │   ├── IPluginManager.cs
│   │   ├── ISecretProvider.cs
│   │   ├── IEventBus.cs
│   │   └── ICurrentUserService.cs
│   ├── Exceptions/
│   │   ├── NotFoundException.cs
│   │   ├── ValidationException.cs
│   │   ├── ConflictException.cs
│   │   └── ForbiddenException.cs
│   └── Mappings/
│       └── MappingProfile.cs
├── Definitions/
│   ├── Commands/
│   │   ├── CreateCollectorDefinition/
│   │   │   ├── CreateCollectorDefinitionCommand.cs
│   │   │   ├── CreateCollectorDefinitionHandler.cs
│   │   │   └── CreateCollectorDefinitionValidator.cs
│   │   ├── UpdateCollectorDefinition/
│   │   ├── PublishDefinitionVersion/
│   │   └── DeprecateDefinition/
│   ├── Queries/
│   │   ├── GetDefinitions/
│   │   │   ├── GetDefinitionsQuery.cs
│   │   │   ├── GetDefinitionsHandler.cs
│   │   │   └── DefinitionDto.cs
│   │   ├── GetDefinitionById/
│   │   └── GetDefinitionVersions/
│   └── (same pattern for Algorithm, Transfer)
├── Instances/
│   ├── Commands/
│   │   ├── CreateCollectorInstance/
│   │   ├── CreateRecipeVersion/
│   │   │   ├── CreateRecipeVersionCommand.cs
│   │   │   ├── CreateRecipeVersionHandler.cs
│   │   │   └── CreateRecipeVersionValidator.cs
│   │   └── SetCurrentRecipeVersion/
│   ├── Queries/
│   │   ├── GetInstances/
│   │   ├── GetRecipeHistory/
│   │   │   ├── GetRecipeHistoryQuery.cs
│   │   │   ├── GetRecipeHistoryHandler.cs
│   │   │   └── RecipeVersionDto.cs
│   │   └── GetRecipeDiff/
│   └── (same pattern for Algorithm, Transfer)
├── Pipelines/
│   ├── Commands/
│   │   ├── CreatePipeline/
│   │   ├── UpdatePipeline/
│   │   ├── AddPipelineStage/
│   │   ├── RemovePipelineStage/
│   │   ├── ReorderPipelineStages/
│   │   ├── ActivatePipeline/
│   │   │   ├── ActivatePipelineCommand.cs
│   │   │   └── ActivatePipelineHandler.cs
│   │   └── DeactivatePipeline/
│   ├── Queries/
│   │   ├── GetPipelines/
│   │   ├── GetPipelineById/
│   │   └── GetPipelineStatus/
│   └── EventHandlers/
│       └── PipelineActivatedEventHandler.cs
├── Jobs/
│   ├── Commands/
│   │   ├── CreateJob/
│   │   ├── ReprocessJob/
│   │   │   ├── ReprocessJobCommand.cs
│   │   │   └── ReprocessJobHandler.cs
│   │   ├── BulkReprocess/
│   │   │   ├── BulkReprocessCommand.cs
│   │   │   └── BulkReprocessHandler.cs
│   │   └── CancelExecution/
│   ├── Queries/
│   │   ├── GetJobs/
│   │   │   ├── GetJobsQuery.cs        // includes filtering, paging, sorting
│   │   │   ├── GetJobsHandler.cs
│   │   │   ├── JobDto.cs
│   │   │   └── JobFilterDto.cs
│   │   ├── GetJobDetail/
│   │   ├── GetExecutionTimeline/
│   │   └── GetExecutionEventLogs/
│   └── EventHandlers/
│       ├── JobCreatedEventHandler.cs
│       ├── JobCompletedEventHandler.cs
│       └── JobFailedEventHandler.cs
├── Plugins/
│   ├── Commands/
│   │   ├── InstallPlugin/
│   │   ├── UninstallPlugin/
│   │   └── EnableDisablePlugin/
│   └── Queries/
│       ├── GetInstalledPlugins/
│       └── GetPluginManifest/
└── System/
    ├── Commands/
    │   └── ProcessDeadLetterEntry/
    └── Queries/
        ├── GetSystemHealth/
        └── GetDeadLetterEntries/
```

**Key Interfaces**:

```csharp
// CQRS base types (thin wrappers over MediatR)
public interface ICommand<TResponse> : IRequest<TResponse> { }
public interface ICommandHandler<TCommand, TResponse> : IRequestHandler<TCommand, TResponse>
    where TCommand : ICommand<TResponse> { }

public interface IQuery<TResponse> : IRequest<TResponse> { }
public interface IQueryHandler<TQuery, TResponse> : IRequestHandler<TQuery, TResponse>
    where TQuery : IQuery<TResponse> { }

// Service interfaces (implemented in Infrastructure)
public interface IPipelineManager
{
    Task<PipelineActivation> ActivateAsync(Guid pipelineId, CancellationToken ct);
    Task DeactivateAsync(Guid activationId, CancellationToken ct);
    Task<PipelineActivation?> GetActiveActivationAsync(Guid pipelineId, CancellationToken ct);
}

public interface IRecipeEngine
{
    Task<JsonDocument> ResolveRecipeAsync(Guid instanceId, RefType type, int? versionNo, CancellationToken ct);
    Task<JsonDocument> ComputeDiffAsync(Guid instanceId, RefType type, int fromVersion, int toVersion, CancellationToken ct);
    Task ValidateRecipeAsync(JsonDocument recipe, JsonDocument schema, CancellationToken ct);
}

public interface IMonitoringEngine
{
    Task StartMonitoringAsync(PipelineActivation activation, CancellationToken ct);
    Task StopMonitoringAsync(Guid activationId, CancellationToken ct);
}

public interface IProcessingOrchestrator
{
    Task ProcessJobAsync(Guid jobId, CancellationToken ct);
    Task ReprocessJobAsync(Guid reprocessRequestId, CancellationToken ct);
}

public interface IExecutionDispatcher
{
    Task<JsonDocument> ExecuteStepAsync(ExecutionType type, string executionRef,
        JsonDocument config, JsonDocument input, CancellationToken ct);
}

public interface ISnapshotResolver
{
    Task<ExecutionSnapshot> CaptureSnapshotAsync(Guid executionId, Guid pipelineInstanceId, CancellationToken ct);
}

public interface IConditionEvaluator
{
    bool Evaluate(JsonDocument eventPayload, JsonDocument conditionConfig);
}

public interface ISchemaRegistry
{
    Task<JsonDocument?> GetSchemaAsync(string schemaName, int? version, CancellationToken ct);
    Task RegisterSchemaAsync(string schemaName, JsonDocument schema, CancellationToken ct);
}

public interface IBackPressureManager
{
    Task<bool> ShouldThrottleAsync(Guid pipelineId, CancellationToken ct);
    Task RecordThroughputAsync(Guid pipelineId, int itemCount, CancellationToken ct);
}

public interface ICircuitBreakerManager
{
    Task<bool> IsOpenAsync(string resourceKey, CancellationToken ct);
    Task RecordSuccessAsync(string resourceKey, CancellationToken ct);
    Task RecordFailureAsync(string resourceKey, CancellationToken ct);
}

public interface ISecretProvider
{
    Task<string> GetSecretAsync(string key, CancellationToken ct);
}

public interface IEventBus
{
    Task PublishAsync<T>(T @event, CancellationToken ct) where T : IDomainEvent;
}

public interface ICurrentUserService
{
    string? UserId { get; }
    string? UserName { get; }
}
```

**Example Command/Handler**:
```csharp
public record ActivatePipelineCommand(Guid PipelineId) : ICommand<PipelineActivationDto>;

public class ActivatePipelineHandler : ICommandHandler<ActivatePipelineCommand, PipelineActivationDto>
{
    private readonly IRepository<PipelineInstance> _pipelineRepo;
    private readonly IPipelineManager _pipelineManager;
    private readonly IMapper _mapper;

    public ActivatePipelineHandler(
        IRepository<PipelineInstance> pipelineRepo,
        IPipelineManager pipelineManager,
        IMapper mapper)
    {
        _pipelineRepo = pipelineRepo;
        _pipelineManager = pipelineManager;
        _mapper = mapper;
    }

    public async Task<PipelineActivationDto> Handle(
        ActivatePipelineCommand request, CancellationToken ct)
    {
        var pipeline = await _pipelineRepo.GetByIdAsync(request.PipelineId, ct)
            ?? throw new NotFoundException(nameof(PipelineInstance), request.PipelineId);

        if (pipeline.Status != PipelineStatus.Active)
            throw new HermesDomainException("Pipeline must be in Active status to activate.");

        var activation = await _pipelineManager.ActivateAsync(pipeline.Id, ct);
        return _mapper.Map<PipelineActivationDto>(activation);
    }
}
```

**NuGet Packages**:
| Package | Version | Purpose |
|---|---|---|
| `MediatR` | 12.x | CQRS command/query dispatching |
| `FluentValidation` | 11.x | Request validation |
| `FluentValidation.DependencyInjectionExtensions` | 11.x | DI integration |
| `AutoMapper` | 13.x | Object-to-object mapping |
| `AutoMapper.Extensions.Microsoft.DependencyInjection` | 13.x | DI registration |

**DI Registration** (`DependencyInjection.cs`):
```csharp
public static class DependencyInjection
{
    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        services.AddMediatR(cfg =>
            cfg.RegisterServicesFromAssembly(typeof(DependencyInjection).Assembly));

        services.AddValidatorsFromAssembly(typeof(DependencyInjection).Assembly);
        services.AddAutoMapper(typeof(DependencyInjection).Assembly);

        services.AddTransient(typeof(IPipelineBehavior<,>), typeof(ValidationBehavior<,>));
        services.AddTransient(typeof(IPipelineBehavior<,>), typeof(LoggingBehavior<,>));
        services.AddTransient(typeof(IPipelineBehavior<,>), typeof(PerformanceBehavior<,>));

        return services;
    }
}
```

---

### 2.3 Hermes.Infrastructure

**Purpose**: All external concerns — database, messaging, HTTP clients, gRPC, metrics, health checks.

**References**: `Hermes.Domain`, `Hermes.Application`, `Hermes.Shared`

**Namespace Structure**:
```
Hermes.Infrastructure
├── Persistence/
│   ├── HermesDbContext.cs
│   ├── UnitOfWork.cs
│   ├── Configurations/
│   │   ├── CollectorDefinitionConfiguration.cs
│   │   ├── CollectorDefinitionVersionConfiguration.cs
│   │   ├── AlgorithmDefinitionConfiguration.cs
│   │   ├── ...                                        // one per entity
│   │   ├── JobConfiguration.cs
│   │   ├── DeadLetterEntryConfiguration.cs
│   │   └── PluginRegistryEntryConfiguration.cs
│   ├── Repositories/
│   │   ├── GenericRepository.cs
│   │   ├── CollectorDefinitionRepository.cs
│   │   ├── PipelineInstanceRepository.cs
│   │   ├── JobRepository.cs
│   │   └── ...
│   ├── Migrations/                                    // EF Core auto-generated
│   └── Interceptors/
│       ├── AuditableEntityInterceptor.cs
│       └── DomainEventDispatchInterceptor.cs
├── Messaging/
│   ├── Kafka/
│   │   ├── KafkaProducer.cs
│   │   ├── KafkaConsumer.cs
│   │   └── KafkaOptions.cs
│   └── InMemory/
│       └── InMemoryEventBus.cs
├── Plugins/
│   ├── PluginLoader.cs
│   ├── ProcessPluginExecutor.cs                       // stdin/stdout JSON protocol
│   ├── HttpPluginExecutor.cs
│   ├── DockerPluginExecutor.cs
│   ├── GrpcPluginExecutor.cs
│   └── NifiFlowExecutor.cs
├── Services/
│   ├── PipelineManager.cs
│   ├── RecipeEngine.cs
│   ├── ProcessingOrchestrator.cs
│   ├── ExecutionDispatcher.cs
│   ├── SnapshotResolver.cs
│   ├── ConditionEvaluator.cs
│   ├── SchemaRegistry.cs
│   ├── BackPressureManager.cs
│   └── CircuitBreakerManager.cs
├── ExternalServices/
│   ├── NiFi/
│   │   ├── NiFiClient.cs
│   │   ├── NiFiOptions.cs
│   │   └── NiFiModels.cs
│   └── Secrets/
│       ├── EnvironmentSecretProvider.cs
│       ├── AzureKeyVaultSecretProvider.cs
│       └── AwsSecretsManagerProvider.cs
├── HealthChecks/
│   ├── PostgreSqlHealthCheck.cs
│   ├── KafkaHealthCheck.cs
│   └── NiFiHealthCheck.cs
└── Metrics/
    ├── PrometheusMetrics.cs
    └── MetricsConstants.cs
```

**Key Implementation — DbContext**:
```csharp
public class HermesDbContext : DbContext, IUnitOfWork
{
    public HermesDbContext(DbContextOptions<HermesDbContext> options) : base(options) { }

    // Definition Layer
    public DbSet<CollectorDefinition> CollectorDefinitions => Set<CollectorDefinition>();
    public DbSet<CollectorDefinitionVersion> CollectorDefinitionVersions => Set<CollectorDefinitionVersion>();
    public DbSet<AlgorithmDefinition> AlgorithmDefinitions => Set<AlgorithmDefinition>();
    public DbSet<AlgorithmDefinitionVersion> AlgorithmDefinitionVersions => Set<AlgorithmDefinitionVersion>();
    public DbSet<TransferDefinition> TransferDefinitions => Set<TransferDefinition>();
    public DbSet<TransferDefinitionVersion> TransferDefinitionVersions => Set<TransferDefinitionVersion>();

    // Instance Layer
    public DbSet<CollectorInstance> CollectorInstances => Set<CollectorInstance>();
    public DbSet<CollectorInstanceVersion> CollectorInstanceVersions => Set<CollectorInstanceVersion>();
    public DbSet<AlgorithmInstance> AlgorithmInstances => Set<AlgorithmInstance>();
    public DbSet<AlgorithmInstanceVersion> AlgorithmInstanceVersions => Set<AlgorithmInstanceVersion>();
    public DbSet<TransferInstance> TransferInstances => Set<TransferInstance>();
    public DbSet<TransferInstanceVersion> TransferInstanceVersions => Set<TransferInstanceVersion>();

    // Pipeline Layer
    public DbSet<PipelineInstance> PipelineInstances => Set<PipelineInstance>();
    public DbSet<PipelineStage> PipelineStages => Set<PipelineStage>();
    public DbSet<PipelineActivation> PipelineActivations => Set<PipelineActivation>();

    // Execution Layer
    public DbSet<Job> Jobs => Set<Job>();
    public DbSet<JobExecution> JobExecutions => Set<JobExecution>();
    public DbSet<JobStepExecution> JobStepExecutions => Set<JobStepExecution>();
    public DbSet<ExecutionSnapshot> ExecutionSnapshots => Set<ExecutionSnapshot>();
    public DbSet<ExecutionEventLog> ExecutionEventLogs => Set<ExecutionEventLog>();
    public DbSet<ReprocessRequest> ReprocessRequests => Set<ReprocessRequest>();

    // System
    public DbSet<DeadLetterEntry> DeadLetterEntries => Set<DeadLetterEntry>();
    public DbSet<PluginRegistryEntry> PluginRegistry => Set<PluginRegistryEntry>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.ApplyConfigurationsFromAssembly(typeof(HermesDbContext).Assembly);
        modelBuilder.HasPostgresEnum<DefinitionStatus>("definition_status");
        modelBuilder.HasPostgresEnum<ExecutionType>("execution_type");
        modelBuilder.HasPostgresEnum<InstanceStatus>("instance_status");
        modelBuilder.HasPostgresEnum<PipelineStatus>("pipeline_status");
        modelBuilder.HasPostgresEnum<MonitoringType>("monitoring_type");
        modelBuilder.HasPostgresEnum<StageType>("stage_type");
        modelBuilder.HasPostgresEnum<RefType>("ref_type");
        modelBuilder.HasPostgresEnum<OnErrorAction>("on_error_action");
        modelBuilder.HasPostgresEnum<ActivationStatus>("activation_status");
        modelBuilder.HasPostgresEnum<SourceType>("source_type");
        modelBuilder.HasPostgresEnum<JobStatus>("job_status");
        modelBuilder.HasPostgresEnum<TriggerType>("trigger_type");
        modelBuilder.HasPostgresEnum<ExecutionStatus>("execution_status");
        modelBuilder.HasPostgresEnum<StepExecutionStatus>("step_execution_status");
        modelBuilder.HasPostgresEnum<ReprocessStatus>("reprocess_status");
        modelBuilder.HasPostgresEnum<EventLevel>("event_level");
        modelBuilder.HasPostgresEnum<PluginStatus>("plugin_status");
    }
}
```

**Example EF Configuration**:
```csharp
public class JobConfiguration : IEntityTypeConfiguration<Job>
{
    public void Configure(EntityTypeBuilder<Job> builder)
    {
        builder.ToTable("jobs");
        builder.HasKey(e => e.Id);
        builder.Property(e => e.Id).HasColumnName("id");
        builder.Property(e => e.PipelineActivationId).HasColumnName("pipeline_activation_id");
        builder.Property(e => e.PipelineInstanceId).HasColumnName("pipeline_instance_id");
        builder.Property(e => e.SourceType).HasColumnName("source_type");
        builder.Property(e => e.SourceKey).HasColumnName("source_key").HasMaxLength(1024);
        builder.Property(e => e.SourceMetadata).HasColumnName("source_metadata").HasColumnType("jsonb");
        builder.Property(e => e.DedupKey).HasColumnName("dedup_key").HasMaxLength(512);
        builder.Property(e => e.DetectedAt).HasColumnName("detected_at");
        builder.Property(e => e.Status).HasColumnName("status");
        builder.Property(e => e.CurrentExecutionId).HasColumnName("current_execution_id");
        builder.Property(e => e.ExecutionCount).HasColumnName("execution_count");
        builder.Property(e => e.LastCompletedAt).HasColumnName("last_completed_at");
        builder.Property(e => e.CreatedAt).HasColumnName("created_at");
        builder.Property(e => e.UpdatedAt).HasColumnName("updated_at");

        builder.HasIndex(e => e.PipelineInstanceId);
        builder.HasIndex(e => e.PipelineActivationId);
        builder.HasIndex(e => e.Status);
        builder.HasIndex(e => e.DetectedAt);
        builder.HasIndex(e => new { e.PipelineInstanceId, e.DedupKey })
               .HasFilter("dedup_key IS NOT NULL");

        builder.HasOne(e => e.Activation)
               .WithMany(a => a.Jobs)
               .HasForeignKey(e => e.PipelineActivationId)
               .OnDelete(DeleteBehavior.Restrict);

        builder.HasOne(e => e.CurrentExecution)
               .WithOne()
               .HasForeignKey<Job>(e => e.CurrentExecutionId)
               .OnDelete(DeleteBehavior.SetNull);
    }
}
```

**NuGet Packages**:
| Package | Version | Purpose |
|---|---|---|
| `Npgsql.EntityFrameworkCore.PostgreSQL` | 8.x | PostgreSQL EF Core provider |
| `Microsoft.EntityFrameworkCore` | 8.x | ORM |
| `Microsoft.EntityFrameworkCore.Design` | 8.x | Migrations tooling |
| `Confluent.Kafka` | 2.x | Kafka producer/consumer |
| `Grpc.Net.Client` | 2.x | gRPC client |
| `Google.Protobuf` | 3.x | Protobuf serialization |
| `Grpc.Tools` | 2.x | Proto compilation |
| `Microsoft.Extensions.Http.Polly` | 8.x | Resilience policies |
| `Polly` | 8.x | Circuit breaker, retry, timeout |
| `prometheus-net` | 8.x | Prometheus metrics |
| `prometheus-net.AspNetCore` | 8.x | Metrics middleware |
| `AspNetCore.HealthChecks.NpgSql` | 8.x | PostgreSQL health check |
| `AspNetCore.HealthChecks.Kafka` | 8.x | Kafka health check |
| `Microsoft.Extensions.Caching.StackExchangeRedis` | 8.x | Redis caching (optional) |

**DI Registration**:
```csharp
public static class DependencyInjection
{
    public static IServiceCollection AddInfrastructure(
        this IServiceCollection services, IConfiguration configuration)
    {
        // EF Core + PostgreSQL
        services.AddDbContext<HermesDbContext>(options =>
            options.UseNpgsql(
                configuration.GetConnectionString("HermesDb"),
                npgsqlOptions =>
                {
                    npgsqlOptions.MigrationsAssembly(typeof(HermesDbContext).Assembly.FullName);
                    npgsqlOptions.EnableRetryOnFailure(3);
                    npgsqlOptions.MapEnum<DefinitionStatus>("definition_status");
                    // ... map all enums
                })
            .AddInterceptors(
                services.BuildServiceProvider().GetRequiredService<AuditableEntityInterceptor>(),
                services.BuildServiceProvider().GetRequiredService<DomainEventDispatchInterceptor>()));

        services.AddScoped<IUnitOfWork>(sp => sp.GetRequiredService<HermesDbContext>());
        services.AddScoped(typeof(IRepository<>), typeof(GenericRepository<>));

        // Kafka
        services.Configure<KafkaOptions>(configuration.GetSection("Kafka"));
        services.AddSingleton<KafkaProducer>();
        services.AddSingleton<KafkaConsumer>();

        // Services
        services.AddScoped<IPipelineManager, PipelineManager>();
        services.AddScoped<IRecipeEngine, RecipeEngine>();
        services.AddScoped<IProcessingOrchestrator, ProcessingOrchestrator>();
        services.AddScoped<IExecutionDispatcher, ExecutionDispatcher>();
        services.AddScoped<ISnapshotResolver, SnapshotResolver>();
        services.AddScoped<IConditionEvaluator, ConditionEvaluator>();
        services.AddScoped<ISchemaRegistry, SchemaRegistry>();
        services.AddScoped<IBackPressureManager, BackPressureManager>();
        services.AddScoped<ICircuitBreakerManager, CircuitBreakerManager>();
        services.AddScoped<IEventBus, InMemoryEventBus>();
        services.AddScoped<ISecretProvider, EnvironmentSecretProvider>();

        // NiFi HTTP client with Polly
        services.Configure<NiFiOptions>(configuration.GetSection("NiFi"));
        services.AddHttpClient<NiFiClient>()
            .AddTransientHttpErrorPolicy(p =>
                p.WaitAndRetryAsync(3, attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt))))
            .AddTransientHttpErrorPolicy(p =>
                p.CircuitBreakerAsync(5, TimeSpan.FromSeconds(30)));

        // Health checks
        services.AddHealthChecks()
            .AddNpgSql(configuration.GetConnectionString("HermesDb")!, name: "postgresql")
            .AddKafka(cfg =>
            {
                cfg.BootstrapServers = configuration["Kafka:BootstrapServers"];
            }, name: "kafka");

        return services;
    }
}
```

---

### 2.4 Hermes.Api

**Purpose**: ASP.NET Core Web API, SignalR hubs, middleware, Swagger, CORS.

**References**: `Hermes.Application`, `Hermes.Infrastructure`, `Hermes.Shared`

**Namespace Structure**:
```
Hermes.Api
├── Controllers/
│   ├── CollectorDefinitionsController.cs
│   ├── AlgorithmDefinitionsController.cs
│   ├── TransferDefinitionsController.cs
│   ├── CollectorInstancesController.cs
│   ├── AlgorithmInstancesController.cs
│   ├── TransferInstancesController.cs
│   ├── PipelinesController.cs
│   ├── JobsController.cs
│   ├── PluginsController.cs
│   └── SystemController.cs
├── Hubs/
│   ├── PipelineHub.cs
│   └── JobHub.cs
├── Middleware/
│   ├── GlobalExceptionHandlerMiddleware.cs
│   ├── RequestLoggingMiddleware.cs
│   └── CorrelationIdMiddleware.cs
├── Filters/
│   └── ApiExceptionFilterAttribute.cs
├── Models/
│   ├── ApiResponse.cs
│   ├── PagedResponse.cs
│   └── ErrorResponse.cs
├── Configuration/
│   ├── SwaggerConfiguration.cs
│   ├── CorsConfiguration.cs
│   ├── AuthenticationConfiguration.cs
│   └── RateLimitingConfiguration.cs
├── Services/
│   └── CurrentUserService.cs
├── Program.cs
└── appsettings.json
```

**Example Controller**:
```csharp
[ApiController]
[Route("api/v1/pipelines")]
[Produces("application/json")]
public class PipelinesController : ControllerBase
{
    private readonly ISender _mediator;

    public PipelinesController(ISender mediator) => _mediator = mediator;

    /// <summary>List all pipelines with optional filtering.</summary>
    [HttpGet]
    [ProducesResponseType(typeof(PagedResponse<PipelineDto>), 200)]
    public async Task<IActionResult> GetPipelines(
        [FromQuery] GetPipelinesQuery query, CancellationToken ct)
        => Ok(await _mediator.Send(query, ct));

    /// <summary>Get a pipeline by ID with steps and activation status.</summary>
    [HttpGet("{id:guid}")]
    [ProducesResponseType(typeof(PipelineDetailDto), 200)]
    [ProducesResponseType(404)]
    public async Task<IActionResult> GetPipeline(Guid id, CancellationToken ct)
        => Ok(await _mediator.Send(new GetPipelineByIdQuery(id), ct));

    /// <summary>Create a new pipeline.</summary>
    [HttpPost]
    [ProducesResponseType(typeof(PipelineDto), 201)]
    [ProducesResponseType(typeof(ErrorResponse), 400)]
    public async Task<IActionResult> CreatePipeline(
        [FromBody] CreatePipelineCommand command, CancellationToken ct)
    {
        var result = await _mediator.Send(command, ct);
        return CreatedAtAction(nameof(GetPipeline), new { id = result.Id }, result);
    }

    /// <summary>Activate a pipeline (start monitoring).</summary>
    [HttpPost("{id:guid}/activate")]
    [ProducesResponseType(typeof(PipelineActivationDto), 200)]
    [ProducesResponseType(404)]
    [ProducesResponseType(409)]
    public async Task<IActionResult> ActivatePipeline(Guid id, CancellationToken ct)
        => Ok(await _mediator.Send(new ActivatePipelineCommand(id), ct));

    /// <summary>Deactivate a pipeline (stop monitoring).</summary>
    [HttpPost("{id:guid}/deactivate")]
    [ProducesResponseType(204)]
    public async Task<IActionResult> DeactivatePipeline(Guid id, CancellationToken ct)
    {
        await _mediator.Send(new DeactivatePipelineCommand(id), ct);
        return NoContent();
    }
}

[ApiController]
[Route("api/v1/jobs")]
public class JobsController : ControllerBase
{
    private readonly ISender _mediator;
    public JobsController(ISender mediator) => _mediator = mediator;

    [HttpGet]
    public async Task<IActionResult> GetJobs(
        [FromQuery] GetJobsQuery query, CancellationToken ct)
        => Ok(await _mediator.Send(query, ct));

    [HttpGet("{id:guid}")]
    public async Task<IActionResult> GetJob(Guid id, CancellationToken ct)
        => Ok(await _mediator.Send(new GetJobDetailQuery(id), ct));

    [HttpPost("{id:guid}/reprocess")]
    public async Task<IActionResult> ReprocessJob(
        Guid id, [FromBody] ReprocessJobCommand command, CancellationToken ct)
    {
        command = command with { JobId = id };
        return Ok(await _mediator.Send(command, ct));
    }

    [HttpPost("bulk-reprocess")]
    public async Task<IActionResult> BulkReprocess(
        [FromBody] BulkReprocessCommand command, CancellationToken ct)
        => Ok(await _mediator.Send(command, ct));

    [HttpGet("{id:guid}/executions/{executionNo:int}/events")]
    public async Task<IActionResult> GetExecutionEvents(
        Guid id, int executionNo, CancellationToken ct)
        => Ok(await _mediator.Send(new GetExecutionEventLogsQuery(id, executionNo), ct));
}
```

**SignalR Hub**:
```csharp
public class PipelineHub : Hub
{
    public async Task JoinPipelineGroup(Guid pipelineId)
        => await Groups.AddToGroupAsync(Context.ConnectionId, $"pipeline-{pipelineId}");

    public async Task LeavePipelineGroup(Guid pipelineId)
        => await Groups.RemoveFromGroupAsync(Context.ConnectionId, $"pipeline-{pipelineId}");
}

// Broadcast from anywhere via IHubContext<PipelineHub>:
// await _hubContext.Clients.Group($"pipeline-{pipelineId}")
//     .SendAsync("JobStatusChanged", jobDto);
```

**Program.cs (condensed)**:
```csharp
var builder = WebApplication.CreateBuilder(args);

// Layer registration
builder.Services.AddApplication();
builder.Services.AddInfrastructure(builder.Configuration);

// API
builder.Services.AddControllers().AddJsonOptions(o =>
{
    o.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter());
    o.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
});
builder.Services.AddSignalR();
builder.Services.AddEndpointsApiExplorer();
builder.Services.AddSwaggerGen(SwaggerConfiguration.Configure);
builder.Services.AddCors(CorsConfiguration.Configure);
builder.Services.AddRateLimiter(RateLimitingConfiguration.Configure);
builder.Services.AddScoped<ICurrentUserService, CurrentUserService>();

// Optional auth
if (builder.Configuration.GetSection("Authentication").Exists())
    AuthenticationConfiguration.Configure(builder.Services, builder.Configuration);

builder.Services.AddProblemDetails();

var app = builder.Build();

// Middleware pipeline
app.UseCorrelationId();
app.UseRequestLogging();
app.UseExceptionHandler();

if (app.Environment.IsDevelopment())
{
    app.UseSwagger();
    app.UseSwaggerUI();
}

app.UseCors("Default");
app.UseRateLimiter();
app.UseAuthentication();
app.UseAuthorization();

app.MapControllers();
app.MapHub<PipelineHub>("/hubs/pipeline");
app.MapHub<JobHub>("/hubs/jobs");
app.MapHealthChecks("/health", new HealthCheckOptions
{
    ResponseWriter = UIResponseWriter.WriteHealthCheckUIResponse
});
app.MapPrometheusScrapingEndpoint("/metrics");

app.Run();
```

**NuGet Packages**:
| Package | Version | Purpose |
|---|---|---|
| `Microsoft.AspNetCore.OpenApi` | 8.x | OpenAPI metadata |
| `Swashbuckle.AspNetCore` | 6.x | Swagger UI |
| `Microsoft.AspNetCore.SignalR` | (built-in) | Real-time WebSocket |
| `Microsoft.AspNetCore.RateLimiting` | (built-in) | Rate limiting |
| `AspNetCore.HealthChecks.UI.Client` | 8.x | Health check UI response |
| `Serilog.AspNetCore` | 8.x | Structured logging |
| `Serilog.Sinks.Console` | 6.x | Console sink |
| `Serilog.Sinks.Seq` | 7.x | Seq sink (optional) |
| `Microsoft.AspNetCore.Authentication.JwtBearer` | 8.x | JWT auth (optional) |

---

### 2.5 Hermes.Worker

**Purpose**: Long-running background services for monitoring, processing, health, and dead letter handling.

**References**: `Hermes.Application`, `Hermes.Infrastructure`, `Hermes.Shared`

**Namespace Structure**:
```
Hermes.Worker
├── Workers/
│   ├── MonitoringWorker.cs
│   ├── ProcessingWorker.cs
│   ├── HealthCheckWorker.cs
│   ├── BackPressureMonitor.cs
│   └── DeadLetterProcessor.cs
├── Configuration/
│   └── WorkerOptions.cs
├── Program.cs
└── appsettings.json
```

**Key Workers**:
```csharp
public class MonitoringWorker : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<MonitoringWorker> _logger;
    private readonly IOptions<WorkerOptions> _options;

    public MonitoringWorker(
        IServiceScopeFactory scopeFactory,
        ILogger<MonitoringWorker> logger,
        IOptions<WorkerOptions> options)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
        _options = options;
    }

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("MonitoringWorker starting");
        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = _scopeFactory.CreateScope();
                var engine = scope.ServiceProvider.GetRequiredService<IMonitoringEngine>();
                var repo = scope.ServiceProvider.GetRequiredService<IRepository<PipelineActivation>>();

                var activeActivations = await repo.ListAllAsync(stoppingToken);
                foreach (var activation in activeActivations
                    .Where(a => a.Status == ActivationStatus.Running))
                {
                    await engine.StartMonitoringAsync(activation, stoppingToken);
                }
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "MonitoringWorker error");
            }

            await Task.Delay(_options.Value.MonitoringIntervalMs, stoppingToken);
        }
    }
}

public class ProcessingWorker : BackgroundService
{
    // Polls for QUEUED work items and dispatches processing
    // Uses IProcessingOrchestrator.ProcessJobAsync
    // Respects IBackPressureManager.ShouldThrottleAsync
    // Handles concurrency via SemaphoreSlim (configurable max parallelism)
}

public class HealthCheckWorker : BackgroundService
{
    // Periodically updates pipeline_activations.last_heartbeat_at
    // Detects stale activations (no heartbeat > threshold) → marks ERROR
}

public class BackPressureMonitor : BackgroundService
{
    // Monitors queue depth per pipeline
    // Adjusts throttling thresholds dynamically
}

public class DeadLetterProcessor : BackgroundService
{
    // Periodically retries dead letter entries up to max retries
    // Logs permanently failed entries
}
```

**Worker Program.cs**:
```csharp
var builder = Host.CreateApplicationBuilder(args);

builder.Services.AddApplication();
builder.Services.AddInfrastructure(builder.Configuration);
builder.Services.Configure<WorkerOptions>(builder.Configuration.GetSection("Worker"));

builder.Services.AddHostedService<MonitoringWorker>();
builder.Services.AddHostedService<ProcessingWorker>();
builder.Services.AddHostedService<HealthCheckWorker>();
builder.Services.AddHostedService<BackPressureMonitor>();
builder.Services.AddHostedService<DeadLetterProcessor>();

builder.Services.AddSerilog(cfg => cfg.ReadFrom.Configuration(builder.Configuration));

var host = builder.Build();
host.Run();
```

**WorkerOptions**:
```csharp
public class WorkerOptions
{
    public int MonitoringIntervalMs { get; set; } = 5000;
    public int ProcessingIntervalMs { get; set; } = 1000;
    public int HealthCheckIntervalMs { get; set; } = 30000;
    public int MaxParallelProcessing { get; set; } = 4;
    public int HeartbeatStaleThresholdSeconds { get; set; } = 120;
    public int DeadLetterRetryIntervalMs { get; set; } = 60000;
    public int DeadLetterMaxRetries { get; set; } = 5;
}
```

**NuGet Packages**:
| Package | Version | Purpose |
|---|---|---|
| `Microsoft.Extensions.Hosting` | 8.x | Generic host |
| `Serilog.Extensions.Hosting` | 8.x | Serilog integration |
| (inherits Infrastructure packages via project reference) | | |

---

### 2.6 Hermes.Plugins.Sdk

**Purpose**: NuGet package that plugin authors reference to build Hermes plugins. Defines the plugin contract and helpers.

**References**: None (standalone package, no reference to other Hermes projects).

**Published as**: `Hermes.Plugins.Sdk` on NuGet.org

**Namespace Structure**:
```
Hermes.Plugins.Sdk
├── Abstractions/
│   ├── IHermesPlugin.cs
│   ├── ICollector.cs
│   ├── IAlgorithm.cs
│   ├── ITransfer.cs
│   └── IPluginLifecycle.cs
├── Base/
│   ├── PluginBase.cs
│   ├── CollectorBase.cs
│   ├── AlgorithmBase.cs
│   └── TransferBase.cs
├── Models/
│   ├── PluginContext.cs
│   ├── PluginInput.cs
│   ├── PluginOutput.cs
│   ├── PluginMessage.cs
│   ├── PluginManifest.cs
│   └── DataRef.cs
├── Protocol/
│   ├── MessageType.cs          // CONFIGURE, EXECUTE, LOG, OUTPUT, ERROR, STATUS, DONE
│   ├── ProtocolReader.cs       // reads JSON messages from stdin
│   ├── ProtocolWriter.cs       // writes JSON messages to stdout
│   └── ProtocolHost.cs         // main loop: read → dispatch → write
├── Configuration/
│   ├── PluginConfigurationBinder.cs
│   └── PluginHostBuilder.cs
├── Grpc/
│   ├── PluginGrpcService.cs    // gRPC service base for sidecar mode
│   └── PluginGrpcHost.cs
└── Logging/
    └── PluginLogger.cs         // logs via protocol OUTPUT messages
```

**Key Interfaces**:
```csharp
public interface IHermesPlugin : IDisposable
{
    string Name { get; }
    string Version { get; }
    Task ConfigureAsync(JsonDocument config, PluginContext context, CancellationToken ct);
}

public interface ICollector : IHermesPlugin
{
    Task<PluginOutput> CollectAsync(PluginInput input, CancellationToken ct);
}

public interface IAlgorithm : IHermesPlugin
{
    Task<PluginOutput> ProcessAsync(PluginInput input, CancellationToken ct);
}

public interface ITransfer : IHermesPlugin
{
    Task<PluginOutput> TransferAsync(PluginInput input, CancellationToken ct);
}

public abstract class PluginBase<TConfig> : IHermesPlugin where TConfig : class, new()
{
    protected TConfig Config { get; private set; } = new();
    protected PluginContext Context { get; private set; } = null!;
    protected ILogger Logger { get; private set; } = null!;

    public abstract string Name { get; }
    public abstract string Version { get; }

    public virtual Task ConfigureAsync(JsonDocument config, PluginContext context, CancellationToken ct)
    {
        Config = config.Deserialize<TConfig>() ?? new TConfig();
        Context = context;
        return Task.CompletedTask;
    }

    public virtual void Dispose() { }
}

public abstract class CollectorBase<TConfig> : PluginBase<TConfig>, ICollector
    where TConfig : class, new()
{
    public abstract Task<PluginOutput> CollectAsync(PluginInput input, CancellationToken ct);
}

// AlgorithmBase<TConfig>, TransferBase<TConfig> — same pattern

public class PluginHostBuilder
{
    // Bootstraps a plugin process: reads stdin, dispatches to plugin, writes stdout
    public static async Task RunAsync<TPlugin>(string[] args) where TPlugin : IHermesPlugin, new()
    {
        var plugin = new TPlugin();
        var reader = new ProtocolReader(Console.OpenStandardInput());
        var writer = new ProtocolWriter(Console.OpenStandardOutput());
        var host = new ProtocolHost(plugin, reader, writer);
        await host.RunAsync(CancellationToken.None);
    }
}
```

**Plugin Author Example** (e.g., `Hermes.Plugin.RestApiCollector`):
```csharp
public class RestApiCollectorConfig
{
    public string Url { get; set; } = string.Empty;
    public string Method { get; set; } = "GET";
    public Dictionary<string, string>? Headers { get; set; }
    public string? AuthType { get; set; }
    public int TimeoutSeconds { get; set; } = 30;
    public string? ResponseDataPath { get; set; }
}

public class RestApiCollector : CollectorBase<RestApiCollectorConfig>
{
    public override string Name => "rest-api-collector";
    public override string Version => "1.0.0";

    public override async Task<PluginOutput> CollectAsync(PluginInput input, CancellationToken ct)
    {
        using var client = new HttpClient { Timeout = TimeSpan.FromSeconds(Config.TimeoutSeconds) };
        // ... apply headers, auth, make request ...
        var response = await client.SendAsync(request, ct);
        var body = await response.Content.ReadAsStringAsync(ct);
        var data = JsonDocument.Parse(body);

        return new PluginOutput
        {
            Data = data,
            Metadata = new Dictionary<string, object>
            {
                ["status_code"] = (int)response.StatusCode,
                ["fetched_at"] = DateTimeOffset.UtcNow.ToString("O")
            }
        };
    }
}

// Entry point: Program.cs
await PluginHostBuilder.RunAsync<RestApiCollector>(args);
```

**NuGet Packages**:
| Package | Version | Purpose |
|---|---|---|
| `System.Text.Json` | 8.x | JSON serialization (SDK included) |
| `Microsoft.Extensions.Logging.Abstractions` | 8.x | Logging abstractions |
| `Grpc.AspNetCore` | 2.x | gRPC hosting (optional, for sidecar mode) |

---

### 2.7 Hermes.Shared

**Purpose**: Common utilities, constants, extension methods shared across all projects.

**References**: None.

**Contents**:
```
Hermes.Shared
├── Constants/
│   ├── HermesConstants.cs         // app-wide constants
│   └── EventCodes.cs             // COLLECT_START, ALGORITHM_DONE, etc.
├── Extensions/
│   ├── StringExtensions.cs
│   ├── JsonExtensions.cs         // JsonDocument helpers, diff, merge
│   ├── DateTimeExtensions.cs
│   └── EnumerableExtensions.cs
├── Helpers/
│   ├── HashHelper.cs             // SHA256 for snapshot hashing
│   ├── JsonDiffHelper.cs         // compute diff between two JsonDocuments
│   ├── CronParser.cs             // lightweight cron expression parser
│   └── GlobMatcher.cs            // file glob pattern matching
└── Models/
    ├── PagedResult.cs
    ├── SortDirection.cs
    └── Result.cs                 // Result<T> monad for error handling
```

**NuGet Packages**: None (only SDK references).

---

### 2.8 Test Projects

**Hermes.Domain.Tests**:
```
- Entity creation and validation
- Value object equality
- Domain event raising
- NuGet: xunit 2.x, FluentAssertions 6.x, Moq 4.x
```

**Hermes.Application.Tests**:
```
- Command/query handler unit tests
- Validator tests
- Behavior pipeline tests (validation, logging)
- NuGet: xunit, FluentAssertions, Moq, AutoFixture 4.x
```

**Hermes.Infrastructure.Tests**:
```
- Repository tests against in-memory provider
- EF Core configuration tests (column mapping, indexes)
- Service implementation tests
- NuGet: xunit, FluentAssertions, Microsoft.EntityFrameworkCore.InMemory 8.x
```

**Hermes.Api.Tests**:
```
- Controller tests via WebApplicationFactory
- Middleware tests
- SignalR hub tests
- NuGet: xunit, FluentAssertions, Microsoft.AspNetCore.Mvc.Testing 8.x
```

**Hermes.Worker.Tests**:
```
- BackgroundService lifecycle tests
- Worker logic unit tests
- NuGet: xunit, FluentAssertions, Moq
```

**Hermes.IntegrationTests**:
```
- Full end-to-end tests with real dependencies
- NuGet: Testcontainers 3.x, Testcontainers.PostgreSql, Testcontainers.Kafka
- Test: Create definition → create instance → create pipeline → activate → work item flows
```

---

## 3. Key Design Patterns

### 3.1 Clean Architecture

```
                    ┌─────────────────────────┐
                    │     Hermes.Domain        │  ← No dependencies
                    │  Entities, Interfaces    │
                    └────────────▲─────────────┘
                                 │
                    ┌────────────┴─────────────┐
                    │   Hermes.Application      │  ← Depends on Domain only
                    │  Use Cases, CQRS, DTOs    │
                    └────────────▲─────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              │                  │                   │
   ┌──────────┴───────┐ ┌───────┴────────┐ ┌────────┴────────┐
   │ Hermes.Api       │ │ Hermes.Worker  │ │ Hermes.Infra    │
   │ Controllers,     │ │ Background     │ │ EF Core, Kafka, │
   │ SignalR, Swagger  │ │ Services       │ │ gRPC, NiFi      │
   └──────────────────┘ └────────────────┘ └─────────────────┘
```

Dependencies always point inward. Domain has zero external references. Infrastructure implements interfaces defined in Application.

### 3.2 CQRS with MediatR

All API operations go through MediatR. Commands mutate state; queries read state. This enables:
- Validation pipeline (FluentValidation runs before handler)
- Logging pipeline (automatic request/response logging)
- Performance pipeline (slow query detection)
- Easy unit testing (mock IRepository, test handler in isolation)

### 3.3 Repository + Unit of Work

```csharp
// Generic repository for simple CRUD
public class GenericRepository<T> : IRepository<T> where T : BaseEntity
{
    protected readonly HermesDbContext _context;
    protected readonly DbSet<T> _dbSet;

    public GenericRepository(HermesDbContext context)
    {
        _context = context;
        _dbSet = context.Set<T>();
    }

    public async Task<T?> GetByIdAsync(Guid id, CancellationToken ct)
        => await _dbSet.FindAsync(new object[] { id }, ct);

    public async Task<IReadOnlyList<T>> ListAllAsync(CancellationToken ct)
        => await _dbSet.ToListAsync(ct);

    public async Task<T> AddAsync(T entity, CancellationToken ct)
    {
        await _dbSet.AddAsync(entity, ct);
        await _context.SaveChangesAsync(ct);
        return entity;
    }

    public async Task UpdateAsync(T entity, CancellationToken ct)
    {
        _context.Entry(entity).State = EntityState.Modified;
        await _context.SaveChangesAsync(ct);
    }

    public async Task DeleteAsync(T entity, CancellationToken ct)
    {
        _dbSet.Remove(entity);
        await _context.SaveChangesAsync(ct);
    }
}

// Specialized repositories add query methods
public class JobRepository : GenericRepository<Job>, IJobRepository
{
    public async Task<PagedResult<Job>> GetFilteredAsync(
        JobFilter filter, int page, int pageSize, CancellationToken ct)
    {
        var query = _dbSet.AsQueryable();
        if (filter.PipelineId.HasValue)
            query = query.Where(w => w.PipelineInstanceId == filter.PipelineId.Value);
        if (filter.Status.HasValue)
            query = query.Where(w => w.Status == filter.Status.Value);
        // ... more filters
        var total = await query.CountAsync(ct);
        var items = await query
            .OrderByDescending(w => w.DetectedAt)
            .Skip((page - 1) * pageSize)
            .Take(pageSize)
            .Include(w => w.CurrentExecution)
            .ToListAsync(ct);
        return new PagedResult<Job>(items, total, page, pageSize);
    }
}
```

### 3.4 Domain Events

Domain events are raised in entities, dispatched after `SaveChangesAsync` via `DomainEventDispatchInterceptor`:

```csharp
public class DomainEventDispatchInterceptor : SaveChangesInterceptor
{
    private readonly IMediator _mediator;

    public DomainEventDispatchInterceptor(IMediator mediator) => _mediator = mediator;

    public override async ValueTask<int> SavedChangesAsync(
        SaveChangesCompletedEventData eventData, int result, CancellationToken ct)
    {
        var context = eventData.Context;
        if (context is null) return result;

        var entities = context.ChangeTracker.Entries<BaseEntity>()
            .Where(e => e.Entity.DomainEvents.Any())
            .Select(e => e.Entity)
            .ToList();

        var events = entities.SelectMany(e => e.DomainEvents).ToList();
        entities.ForEach(e => e.ClearDomainEvents());

        foreach (var domainEvent in events)
            await _mediator.Publish(domainEvent, ct);

        return result;
    }
}
```

### 3.5 Options Pattern

All configuration sections are strongly typed:

```csharp
services.Configure<KafkaOptions>(configuration.GetSection("Kafka"));
services.Configure<NiFiOptions>(configuration.GetSection("NiFi"));
services.Configure<WorkerOptions>(configuration.GetSection("Worker"));
```

### 3.6 Circuit Breaker (Polly)

Applied to all external calls (NiFi, HTTP plugins, Kafka):

```csharp
// Defined in Infrastructure DI
services.AddHttpClient<NiFiClient>()
    .AddPolicyHandler(Policy.WrapAsync(
        Policy<HttpResponseMessage>
            .Handle<HttpRequestException>()
            .CircuitBreakerAsync(5, TimeSpan.FromSeconds(30)),
        Policy<HttpResponseMessage>
            .Handle<HttpRequestException>()
            .WaitAndRetryAsync(3, attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt))),
        Policy.TimeoutAsync<HttpResponseMessage>(TimeSpan.FromSeconds(30))
    ));
```

### 3.7 Specification Pattern (for query filtering)

```csharp
public abstract class Specification<T>
{
    public abstract Expression<Func<T, bool>> ToExpression();
    public bool IsSatisfiedBy(T entity) => ToExpression().Compile()(entity);
}

public class ActivePipelinesSpec : Specification<PipelineInstance>
{
    public override Expression<Func<PipelineInstance, bool>> ToExpression()
        => p => p.Status == PipelineStatus.Active;
}
```

---

## 4. NuGet Package Summary

### src/Hermes.Domain
No packages.

### src/Hermes.Application
| Package | Version |
|---|---|
| MediatR | 12.4+ |
| FluentValidation | 11.10+ |
| FluentValidation.DependencyInjectionExtensions | 11.10+ |
| AutoMapper | 13.0+ |
| AutoMapper.Extensions.Microsoft.DependencyInjection | 13.0+ |

### src/Hermes.Infrastructure
| Package | Version |
|---|---|
| Npgsql.EntityFrameworkCore.PostgreSQL | 8.0+ |
| Microsoft.EntityFrameworkCore | 8.0+ |
| Microsoft.EntityFrameworkCore.Design | 8.0+ |
| Confluent.Kafka | 2.6+ |
| Grpc.Net.Client | 2.66+ |
| Google.Protobuf | 3.28+ |
| Grpc.Tools | 2.66+ |
| Microsoft.Extensions.Http.Polly | 8.0+ |
| Polly | 8.4+ |
| prometheus-net | 8.2+ |
| prometheus-net.AspNetCore | 8.2+ |
| AspNetCore.HealthChecks.NpgSql | 8.0+ |
| AspNetCore.HealthChecks.Kafka | 8.0+ |
| Microsoft.Extensions.Caching.StackExchangeRedis | 8.0+ |

### src/Hermes.Api
| Package | Version |
|---|---|
| Swashbuckle.AspNetCore | 6.8+ |
| AspNetCore.HealthChecks.UI.Client | 8.0+ |
| Serilog.AspNetCore | 8.0+ |
| Serilog.Sinks.Console | 6.0+ |
| Serilog.Sinks.Seq | 7.0+ |
| Microsoft.AspNetCore.Authentication.JwtBearer | 8.0+ |

### src/Hermes.Worker
| Package | Version |
|---|---|
| Serilog.Extensions.Hosting | 8.0+ |

### src/Hermes.Plugins.Sdk
| Package | Version |
|---|---|
| Microsoft.Extensions.Logging.Abstractions | 8.0+ |
| Grpc.AspNetCore | 2.66+ |

### src/Hermes.Shared
No packages.

### Test Projects
| Package | Used By |
|---|---|
| xunit 2.9+ | All test projects |
| xunit.runner.visualstudio 2.8+ | All test projects |
| FluentAssertions 6.12+ | All test projects |
| Moq 4.20+ | Unit test projects |
| AutoFixture 4.18+ | Application.Tests |
| Microsoft.EntityFrameworkCore.InMemory 8.0+ | Infrastructure.Tests |
| Microsoft.AspNetCore.Mvc.Testing 8.0+ | Api.Tests |
| Testcontainers 3.10+ | IntegrationTests |
| Testcontainers.PostgreSql 3.10+ | IntegrationTests |
| Testcontainers.Kafka 3.10+ | IntegrationTests |

---

## 5. Configuration

### 5.1 appsettings.json (API)

```json
{
  "ConnectionStrings": {
    "HermesDb": "Host=localhost;Port=5432;Database=hermes;Username=hermes;Password=hermes"
  },
  "Kafka": {
    "BootstrapServers": "localhost:9092",
    "GroupId": "hermes-core",
    "AutoOffsetReset": "Earliest",
    "EnableAutoCommit": false
  },
  "NiFi": {
    "BaseUrl": "http://localhost:8080/nifi-api",
    "Username": "",
    "Password": "",
    "TimeoutSeconds": 30
  },
  "Worker": {
    "MonitoringIntervalMs": 5000,
    "ProcessingIntervalMs": 1000,
    "HealthCheckIntervalMs": 30000,
    "MaxParallelProcessing": 4,
    "HeartbeatStaleThresholdSeconds": 120,
    "DeadLetterRetryIntervalMs": 60000,
    "DeadLetterMaxRetries": 5
  },
  "Cors": {
    "AllowedOrigins": ["http://localhost:3000"]
  },
  "Authentication": {
    "Enabled": false,
    "Authority": "https://your-idp.com",
    "Audience": "hermes-api"
  },
  "Serilog": {
    "MinimumLevel": {
      "Default": "Information",
      "Override": {
        "Microsoft.AspNetCore": "Warning",
        "Microsoft.EntityFrameworkCore": "Warning"
      }
    },
    "WriteTo": [
      { "Name": "Console" },
      { "Name": "Seq", "Args": { "serverUrl": "http://localhost:5341" } }
    ]
  },
  "RateLimiting": {
    "PermitLimit": 100,
    "WindowSeconds": 60,
    "QueueLimit": 10
  }
}
```

### 5.2 Environment-Specific Overrides

```
appsettings.json                  ← base
appsettings.Development.json      ← local dev overrides
appsettings.Staging.json          ← staging
appsettings.Production.json       ← production (minimal, secrets via env/vault)
```

### 5.3 Docker Environment Variables

```yaml
# docker-compose.yml environment section
environment:
  - ASPNETCORE_ENVIRONMENT=Production
  - ConnectionStrings__HermesDb=Host=postgres;Port=5432;Database=hermes;Username=hermes;Password=${DB_PASSWORD}
  - Kafka__BootstrapServers=kafka:9092
  - NiFi__BaseUrl=http://nifi:8080/nifi-api
  - Worker__MaxParallelProcessing=8
  - Authentication__Enabled=true
  - Authentication__Authority=https://idp.example.com
```

### 5.4 Secrets Management

**Development**: .NET User Secrets
```bash
dotnet user-secrets set "ConnectionStrings:HermesDb" "Host=localhost;..."
```

**Production options**:
- **Environment variables** (simplest, Docker/K8s native)
- **Azure Key Vault**: `Azure.Extensions.AspNetCore.Configuration.Secrets` package
- **AWS Secrets Manager**: `AWSSDK.SecretsManager` + custom configuration provider
- **HashiCorp Vault**: `VaultSharp` package

```csharp
// Azure Key Vault integration in Program.cs
builder.Configuration.AddAzureKeyVault(
    new Uri($"https://{builder.Configuration["KeyVault:Name"]}.vault.azure.net/"),
    new DefaultAzureCredential());
```

---

## 6. Build & Deployment

### 6.1 Docker Multi-Stage Build

**Dockerfile.api**:
```dockerfile
# Build stage
FROM mcr.microsoft.com/dotnet/sdk:8.0-alpine AS build
WORKDIR /src

# Copy csproj files and restore (layer caching)
COPY src/Hermes.Domain/Hermes.Domain.csproj src/Hermes.Domain/
COPY src/Hermes.Application/Hermes.Application.csproj src/Hermes.Application/
COPY src/Hermes.Infrastructure/Hermes.Infrastructure.csproj src/Hermes.Infrastructure/
COPY src/Hermes.Shared/Hermes.Shared.csproj src/Hermes.Shared/
COPY src/Hermes.Api/Hermes.Api.csproj src/Hermes.Api/
RUN dotnet restore src/Hermes.Api/Hermes.Api.csproj

# Copy source and publish
COPY src/ src/
RUN dotnet publish src/Hermes.Api/Hermes.Api.csproj \
    -c Release \
    -o /app/publish \
    --no-restore \
    /p:PublishTrimmed=false

# Runtime stage
FROM mcr.microsoft.com/dotnet/aspnet:8.0-alpine AS runtime
WORKDIR /app

RUN addgroup -S hermes && adduser -S hermes -G hermes
USER hermes

COPY --from=build /app/publish .

ENV ASPNETCORE_URLS=http://+:8080
EXPOSE 8080

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://localhost:8080/health || exit 1

ENTRYPOINT ["dotnet", "Hermes.Api.dll"]
```

**Dockerfile.worker**:
```dockerfile
FROM mcr.microsoft.com/dotnet/sdk:8.0-alpine AS build
WORKDIR /src

COPY src/Hermes.Domain/Hermes.Domain.csproj src/Hermes.Domain/
COPY src/Hermes.Application/Hermes.Application.csproj src/Hermes.Application/
COPY src/Hermes.Infrastructure/Hermes.Infrastructure.csproj src/Hermes.Infrastructure/
COPY src/Hermes.Shared/Hermes.Shared.csproj src/Hermes.Shared/
COPY src/Hermes.Worker/Hermes.Worker.csproj src/Hermes.Worker/
RUN dotnet restore src/Hermes.Worker/Hermes.Worker.csproj

COPY src/ src/
RUN dotnet publish src/Hermes.Worker/Hermes.Worker.csproj \
    -c Release \
    -o /app/publish \
    --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:8.0-alpine AS runtime
WORKDIR /app
RUN addgroup -S hermes && adduser -S hermes -G hermes
USER hermes
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "Hermes.Worker.dll"]
```

**docker-compose.yml**:
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_DB: hermes
      POSTGRES_USER: hermes
      POSTGRES_PASSWORD: hermes
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U hermes"]
      interval: 10s
      timeout: 5s
      retries: 5

  kafka:
    image: confluentinc/cp-kafka:7.7.0
    environment:
      KAFKA_NODE_ID: 1
      KAFKA_LISTENER_SECURITY_PROTOCOL_MAP: CONTROLLER:PLAINTEXT,PLAINTEXT:PLAINTEXT
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://kafka:9092
      KAFKA_PROCESS_ROLES: broker,controller
      KAFKA_CONTROLLER_QUORUM_VOTERS: 1@kafka:9093
      KAFKA_LISTENERS: PLAINTEXT://kafka:9092,CONTROLLER://kafka:9093
      KAFKA_CONTROLLER_LISTENER_NAMES: CONTROLLER
      CLUSTER_ID: hermes-cluster-001
    ports:
      - "9092:9092"

  hermes-api:
    build:
      context: .
      dockerfile: docker/Dockerfile.api
    ports:
      - "8080:8080"
    environment:
      - ASPNETCORE_ENVIRONMENT=Production
      - ConnectionStrings__HermesDb=Host=postgres;Port=5432;Database=hermes;Username=hermes;Password=hermes
      - Kafka__BootstrapServers=kafka:9092
    depends_on:
      postgres:
        condition: service_healthy
      kafka:
        condition: service_started

  hermes-worker:
    build:
      context: .
      dockerfile: docker/Dockerfile.worker
    environment:
      - ConnectionStrings__HermesDb=Host=postgres;Port=5432;Database=hermes;Username=hermes;Password=hermes
      - Kafka__BootstrapServers=kafka:9092
      - Worker__MaxParallelProcessing=4
    depends_on:
      postgres:
        condition: service_healthy
      kafka:
        condition: service_started

volumes:
  pgdata:
```

### 6.2 CI/CD with GitHub Actions

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  build-and-test:
    runs-on: ubuntu-latest

    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_DB: hermes_test
          POSTGRES_USER: test
          POSTGRES_PASSWORD: test
        ports: ["5432:5432"]
        options: >-
          --health-cmd pg_isready --health-interval 10s
          --health-timeout 5s --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Setup .NET 8
        uses: actions/setup-dotnet@v4
        with:
          dotnet-version: '8.0.x'

      - name: Restore dependencies
        run: dotnet restore

      - name: Build
        run: dotnet build --no-restore --configuration Release

      - name: Run unit tests
        run: |
          dotnet test tests/Hermes.Domain.Tests/ --no-build -c Release --logger trx
          dotnet test tests/Hermes.Application.Tests/ --no-build -c Release --logger trx
          dotnet test tests/Hermes.Infrastructure.Tests/ --no-build -c Release --logger trx
          dotnet test tests/Hermes.Api.Tests/ --no-build -c Release --logger trx
          dotnet test tests/Hermes.Worker.Tests/ --no-build -c Release --logger trx

      - name: Run integration tests
        env:
          ConnectionStrings__HermesDb: "Host=localhost;Port=5432;Database=hermes_test;Username=test;Password=test"
        run: dotnet test tests/Hermes.IntegrationTests/ --no-build -c Release --logger trx

      - name: Publish test results
        uses: dorny/test-reporter@v1
        if: always()
        with:
          name: Test Results
          path: '**/*.trx'
          reporter: dotnet-trx

  docker:
    needs: build-and-test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'

    steps:
      - uses: actions/checkout@v4

      - name: Login to GHCR
        uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}

      - name: Build and push API image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/Dockerfile.api
          push: true
          tags: ghcr.io/${{ github.repository }}/hermes-api:latest

      - name: Build and push Worker image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: docker/Dockerfile.worker
          push: true
          tags: ghcr.io/${{ github.repository }}/hermes-worker:latest
```

### 6.3 Kubernetes Health Endpoints

| Endpoint | Purpose | Used By |
|---|---|---|
| `GET /health` | Full health check (DB, Kafka, NiFi) | K8s readinessProbe |
| `GET /health/live` | Liveness (app is running) | K8s livenessProbe |
| `GET /health/startup` | Startup check (DB migrations done) | K8s startupProbe |
| `GET /metrics` | Prometheus scrape endpoint | Prometheus |

```csharp
// Health check endpoint mapping
app.MapHealthChecks("/health", new HealthCheckOptions
{
    ResponseWriter = UIResponseWriter.WriteHealthCheckUIResponse
});

app.MapHealthChecks("/health/live", new HealthCheckOptions
{
    Predicate = _ => false  // no checks, just "am I alive?"
});

app.MapHealthChecks("/health/startup", new HealthCheckOptions
{
    Tags = { "startup" }
});
```

### 6.4 Helm Chart Considerations

```
helm/hermes/
├── Chart.yaml
├── values.yaml
├── templates/
│   ├── api-deployment.yaml
│   ├── api-service.yaml
│   ├── api-hpa.yaml                  # HorizontalPodAutoscaler
│   ├── worker-deployment.yaml
│   ├── worker-hpa.yaml
│   ├── configmap.yaml
│   ├── secret.yaml
│   ├── ingress.yaml
│   ├── serviceaccount.yaml
│   └── pdb.yaml                      # PodDisruptionBudget
└── charts/
    ├── postgresql/                    # bitnami/postgresql subchart
    └── kafka/                         # bitnami/kafka subchart
```

Key Helm values:
```yaml
api:
  replicas: 2
  resources:
    requests: { cpu: 250m, memory: 256Mi }
    limits: { cpu: 1000m, memory: 512Mi }
  autoscaling:
    enabled: true
    minReplicas: 2
    maxReplicas: 10
    targetCPUUtilizationPercentage: 70

worker:
  replicas: 2
  resources:
    requests: { cpu: 500m, memory: 512Mi }
    limits: { cpu: 2000m, memory: 1Gi }
  config:
    maxParallelProcessing: 8

postgresql:
  enabled: true
  auth:
    database: hermes
    username: hermes
    existingSecret: hermes-db-secret
```

---

## 7. gRPC Proto Definitions

**protos/hermes/plugin_service.proto**:
```protobuf
syntax = "proto3";

package hermes.plugin;

option csharp_namespace = "Hermes.Protos";

service PluginService {
  rpc Configure (ConfigureRequest) returns (ConfigureResponse);
  rpc Execute (ExecuteRequest) returns (stream ExecuteResponse);
  rpc HealthCheck (HealthCheckRequest) returns (HealthCheckResponse);
}

message ConfigureRequest {
  string config_json = 1;
  string context_json = 2;
}

message ConfigureResponse {
  bool success = 1;
  string error_message = 2;
}

message ExecuteRequest {
  string input_json = 1;
}

message ExecuteResponse {
  MessageType type = 1;
  string payload_json = 2;
  float progress = 3;
}

enum MessageType {
  LOG = 0;
  OUTPUT = 1;
  ERROR = 2;
  STATUS = 3;
  DONE = 4;
}

message HealthCheckRequest {}
message HealthCheckResponse {
  bool healthy = 1;
  string message = 2;
}
```

---

## 8. API Route Summary

| Method | Route | Description |
|---|---|---|
| **Definitions** | | |
| GET | `/api/v1/collector-definitions` | List collector definitions |
| POST | `/api/v1/collector-definitions` | Create collector definition |
| GET | `/api/v1/collector-definitions/{id}` | Get definition detail |
| POST | `/api/v1/collector-definitions/{id}/versions` | Add definition version |
| | (same pattern for algorithm-definitions, transfer-definitions) | |
| **Instances** | | |
| GET | `/api/v1/collector-instances` | List collector instances |
| POST | `/api/v1/collector-instances` | Create instance |
| GET | `/api/v1/collector-instances/{id}` | Get instance detail |
| GET | `/api/v1/collector-instances/{id}/versions` | Recipe version history |
| POST | `/api/v1/collector-instances/{id}/versions` | Create new recipe version |
| GET | `/api/v1/collector-instances/{id}/diff?from=1&to=2` | Recipe diff |
| | (same pattern for algorithm-instances, transfer-instances) | |
| **Pipelines** | | |
| GET | `/api/v1/pipelines` | List pipelines |
| POST | `/api/v1/pipelines` | Create pipeline |
| GET | `/api/v1/pipelines/{id}` | Get pipeline with steps |
| PUT | `/api/v1/pipelines/{id}` | Update pipeline |
| POST | `/api/v1/pipelines/{id}/steps` | Add step |
| DELETE | `/api/v1/pipelines/{id}/steps/{stepId}` | Remove step |
| POST | `/api/v1/pipelines/{id}/activate` | Activate pipeline |
| POST | `/api/v1/pipelines/{id}/deactivate` | Deactivate pipeline |
| GET | `/api/v1/pipelines/{id}/status` | Activation status |
| **Work Items** | | |
| GET | `/api/v1/jobs` | List work items (filterable) |
| GET | `/api/v1/jobs/{id}` | Work item detail |
| POST | `/api/v1/jobs/{id}/reprocess` | Request reprocess |
| POST | `/api/v1/jobs/bulk-reprocess` | Bulk reprocess |
| GET | `/api/v1/jobs/{id}/executions` | Execution history |
| GET | `/api/v1/jobs/{id}/executions/{no}/events` | Event log |
| GET | `/api/v1/jobs/{id}/executions/{no}/snapshot` | Config snapshot |
| **Plugins** | | |
| GET | `/api/v1/plugins` | List installed plugins |
| POST | `/api/v1/plugins/install` | Install plugin |
| DELETE | `/api/v1/plugins/{id}` | Uninstall plugin |
| **System** | | |
| GET | `/health` | Health check |
| GET | `/metrics` | Prometheus metrics |
| GET | `/api/v1/system/dead-letters` | Dead letter entries |
| POST | `/api/v1/system/dead-letters/{id}/retry` | Retry dead letter |
| **SignalR** | | |
| WS | `/hubs/pipeline` | Pipeline real-time events |
| WS | `/hubs/jobs` | Work item status updates |

---

## 9. Prometheus Metrics

```csharp
public static class MetricsConstants
{
    // Counters
    public static readonly Counter JobsCreated = Metrics.CreateCounter(
        "hermes_jobs_created_total", "Total work items created",
        new CounterConfiguration { LabelNames = new[] { "pipeline_id" } });

    public static readonly Counter JobsCompleted = Metrics.CreateCounter(
        "hermes_jobs_completed_total", "Total work items completed",
        new CounterConfiguration { LabelNames = new[] { "pipeline_id", "status" } });

    public static readonly Counter StepExecutions = Metrics.CreateCounter(
        "hermes_step_executions_total", "Total step executions",
        new CounterConfiguration { LabelNames = new[] { "stage_type", "status" } });

    // Gauges
    public static readonly Gauge ActivePipelines = Metrics.CreateGauge(
        "hermes_active_pipelines", "Number of active pipeline activations");

    public static readonly Gauge QueuedJobs = Metrics.CreateGauge(
        "hermes_queued_jobs", "Number of queued work items",
        new GaugeConfiguration { LabelNames = new[] { "pipeline_id" } });

    // Histograms
    public static readonly Histogram StepDuration = Metrics.CreateHistogram(
        "hermes_step_duration_seconds", "Step execution duration",
        new HistogramConfiguration
        {
            LabelNames = new[] { "stage_type" },
            Buckets = new[] { 0.1, 0.5, 1, 2, 5, 10, 30, 60, 120, 300 }
        });

    public static readonly Histogram JobDuration = Metrics.CreateHistogram(
        "hermes_job_duration_seconds", "Total work item processing duration",
        new HistogramConfiguration
        {
            Buckets = new[] { 1, 5, 10, 30, 60, 120, 300, 600 }
        });
}
```

---

## 10. Quick-Start for Developers

```bash
# 1. Clone and restore
git clone https://github.com/hermes-platform/hermes.git
cd hermes
dotnet restore

# 2. Start dependencies
docker compose -f docker/docker-compose.yml up -d postgres kafka

# 3. Apply migrations
cd src/Hermes.Api
dotnet ef database update

# 4. Run API (terminal 1)
dotnet run --project src/Hermes.Api

# 5. Run Worker (terminal 2)
dotnet run --project src/Hermes.Worker

# 6. Run tests
dotnet test

# API available at http://localhost:5000
# Swagger at http://localhost:5000/swagger
# Health at http://localhost:5000/health
```

---

## 11. Migration from Existing Python Backend

The existing Hermes implementation uses Python/FastAPI/SQLAlchemy. This .NET design is a **parallel implementation** that:

1. **Uses the same PostgreSQL schema** — EF Core entity configurations map to the exact same tables, columns, enums, and constraints defined in `schema.sql`.
2. **Uses the same REST API routes** — controllers mirror the existing FastAPI endpoints.
3. **Supports the same plugin protocol** — stdin/stdout JSON messages, plus gRPC as an additional option.
4. **Shares the same frontend** — the React webapp works unchanged against the .NET API.

This enables a gradual migration where either backend can serve the same database and frontend.
