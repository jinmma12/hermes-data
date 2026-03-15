namespace Hermes.Engine.Domain.Entities;

public class WorkItem : AuditableEntity
{
    public Guid PipelineActivationId { get; set; }
    public Guid PipelineInstanceId { get; set; }
    public SourceType SourceType { get; set; }
    public string SourceKey { get; set; } = string.Empty;
    public string SourceMetadata { get; set; } = "{}";
    public string? DedupKey { get; set; }
    public DateTimeOffset DetectedAt { get; set; } = DateTimeOffset.UtcNow;
    public JobStatus Status { get; set; } = JobStatus.Detected;
    public Guid? CurrentExecutionId { get; set; }
    public int ExecutionCount { get; set; }
    public DateTimeOffset? LastCompletedAt { get; set; }
    public PipelineActivation PipelineActivation { get; set; } = null!;
    public PipelineInstance PipelineInstance { get; set; } = null!;
    public List<WorkItemExecution> Executions { get; set; } = new();
    public List<ReprocessRequest> ReprocessRequests { get; set; } = new();
}

public class WorkItemExecution : BaseEntity
{
    public Guid WorkItemId { get; set; }
    public int ExecutionNo { get; set; }
    public TriggerType TriggerType { get; set; } = TriggerType.Initial;
    public string? TriggerSource { get; set; }
    public ExecutionStatus Status { get; set; } = ExecutionStatus.Running;
    public DateTimeOffset StartedAt { get; set; } = DateTimeOffset.UtcNow;
    public DateTimeOffset? EndedAt { get; set; }
    public long? DurationMs { get; set; }
    public Guid? ReprocessRequestId { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public WorkItem WorkItem { get; set; } = null!;
    public List<WorkItemStepExecution> StepExecutions { get; set; } = new();
    public ExecutionSnapshot? Snapshot { get; set; }
    public List<ExecutionEventLog> EventLogs { get; set; } = new();
}

public class WorkItemStepExecution : BaseEntity
{
    public Guid ExecutionId { get; set; }
    public Guid PipelineStepId { get; set; }
    public StageType StepType { get; set; }
    public int StepOrder { get; set; }
    public StepExecutionStatus Status { get; set; } = StepExecutionStatus.Pending;
    public DateTimeOffset? StartedAt { get; set; }
    public DateTimeOffset? EndedAt { get; set; }
    public long? DurationMs { get; set; }
    public string? InputSummary { get; set; }
    public string? OutputSummary { get; set; }
    public string? ErrorCode { get; set; }
    public string? ErrorMessage { get; set; }
    public int RetryAttempt { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public WorkItemExecution Execution { get; set; } = null!;
    public PipelineStep PipelineStep { get; set; } = null!;
    public List<ExecutionEventLog> EventLogs { get; set; } = new();
}

public class ExecutionSnapshot : BaseEntity
{
    public Guid ExecutionId { get; set; }
    public string PipelineConfig { get; set; } = "{}";
    public string CollectorConfig { get; set; } = "{}";
    public string AlgorithmConfig { get; set; } = "{}";
    public string TransferConfig { get; set; } = "{}";
    public string? SnapshotHash { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public WorkItemExecution Execution { get; set; } = null!;
}

public class ExecutionEventLog : BaseEntity
{
    public Guid ExecutionId { get; set; }
    public Guid? StepExecutionId { get; set; }
    public EventLevel EventType { get; set; } = EventLevel.Info;
    public string EventCode { get; set; } = string.Empty;
    public string? Message { get; set; }
    public string? DetailJson { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public WorkItemExecution Execution { get; set; } = null!;
    public WorkItemStepExecution? StepExecution { get; set; }
}

public class ReprocessRequest : AuditableEntity
{
    public Guid WorkItemId { get; set; }
    public string RequestedBy { get; set; } = string.Empty;
    public DateTimeOffset RequestedAt { get; set; } = DateTimeOffset.UtcNow;
    public string? Reason { get; set; }
    public int? StartFromStep { get; set; }
    public bool UseLatestRecipe { get; set; } = true;
    public ReprocessStatus Status { get; set; } = ReprocessStatus.Pending;
    public string? ApprovedBy { get; set; }
    public Guid? ExecutionId { get; set; }
    public WorkItem WorkItem { get; set; } = null!;
}

public class DeadLetterEntry : BaseEntity
{
    public Guid WorkItemId { get; set; }
    public Guid? ExecutionId { get; set; }
    public Guid PipelineInstanceId { get; set; }
    public string ErrorCode { get; set; } = string.Empty;
    public string ErrorMessage { get; set; } = string.Empty;
    public string? StackTrace { get; set; }
    public int FailureCount { get; set; }
    public string? LastStepType { get; set; }
    public int? LastStepOrder { get; set; }
    public string OriginalSourceKey { get; set; } = string.Empty;
    public string? InputDataJson { get; set; }
    public DeadLetterStatus Status { get; set; } = DeadLetterStatus.Quarantined;
    public string? ResolvedBy { get; set; }
    public DateTimeOffset? ResolvedAt { get; set; }
    public string? ResolutionNote { get; set; }
    public DateTimeOffset CreatedAt { get; set; } = DateTimeOffset.UtcNow;
    public WorkItem WorkItem { get; set; } = null!;
}
