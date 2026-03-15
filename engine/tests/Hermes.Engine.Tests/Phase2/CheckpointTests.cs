using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;
using Hermes.Engine.Services;

namespace Hermes.Engine.Tests.Phase2;

/// <summary>
/// Tests for checkpoint-based exactly-once processing.
/// References: Kafka consumer offsets, Flink checkpointing, NiFi FlowFile tracking.
///
/// Key scenarios:
/// - Save checkpoint after each step
/// - Resume from checkpoint after crash
/// - Clear checkpoints on completion
/// - Find recoverable executions
/// </summary>
public class CheckpointTests
{
    private static (CheckpointManager Manager, HermesDbContext Db) Create()
    {
        var (provider, db) = TestServiceHelper.CreateServices();
        var scopeFactory = provider.GetRequiredService<IServiceScopeFactory>();
        var manager = new CheckpointManager(scopeFactory, NullLogger<CheckpointManager>.Instance);
        return (manager, db);
    }

    [Fact]
    public async Task SaveCheckpoint_StoresInMemory()
    {
        var (manager, _) = Create();
        var execId = Guid.NewGuid();

        await manager.SaveCheckpointAsync(execId, 2, "{\"records\":50}");

        var checkpoint = await manager.GetCheckpointAsync(execId);
        Assert.NotNull(checkpoint);
        Assert.Equal(execId, checkpoint.ExecutionId);
        Assert.Equal(2, checkpoint.LastCompletedStep);
        Assert.Equal("{\"records\":50}", checkpoint.LastOutputJson);
    }

    [Fact]
    public async Task SaveCheckpoint_PersistsToDb()
    {
        var (manager, db) = Create();
        var execId = Guid.NewGuid();

        // Need a valid execution for the FK
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);
        var wi = new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/test.csv", Status = JobStatus.Processing };
        db.WorkItems.Add(wi);
        var exec = new WorkItemExecution { WorkItemId = wi.Id, ExecutionNo = 1, Status = ExecutionStatus.Running };
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        await manager.SaveCheckpointAsync(exec.Id, 1, "{\"data\":\"collected\"}");

        // Verify CHECKPOINT event log in DB
        var logs = db.ExecutionEventLogs.Where(e => e.ExecutionId == exec.Id && e.EventCode == "CHECKPOINT").ToList();
        Assert.Single(logs);
        Assert.Contains("step 1", logs[0].Message!);
    }

    [Fact]
    public async Task SaveMultipleCheckpoints_KeepsLatest()
    {
        var (manager, _) = Create();
        var execId = Guid.NewGuid();

        await manager.SaveCheckpointAsync(execId, 1, "step1_output");
        await manager.SaveCheckpointAsync(execId, 2, "step2_output");
        await manager.SaveCheckpointAsync(execId, 3, "step3_output");

        var checkpoint = await manager.GetCheckpointAsync(execId);
        Assert.Equal(3, checkpoint!.LastCompletedStep);
        Assert.Equal("step3_output", checkpoint.LastOutputJson);
    }

    [Fact]
    public async Task GetCheckpoint_NonExistent_ReturnsNull()
    {
        var (manager, _) = Create();
        var result = await manager.GetCheckpointAsync(Guid.NewGuid());
        Assert.Null(result);
    }

    [Fact]
    public async Task ClearCheckpoints_RemovesAll()
    {
        var (manager, db) = Create();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);
        var wi = new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/test.csv", Status = JobStatus.Processing };
        db.WorkItems.Add(wi);
        var exec = new WorkItemExecution { WorkItemId = wi.Id, ExecutionNo = 1, Status = ExecutionStatus.Completed };
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        await manager.SaveCheckpointAsync(exec.Id, 1, "out1");
        await manager.SaveCheckpointAsync(exec.Id, 2, "out2");

        await manager.ClearCheckpointsAsync(exec.Id);

        var checkpoint = await manager.GetCheckpointAsync(exec.Id);
        Assert.Null(checkpoint);

        // DB events should be cleaned up too
        var logs = db.ExecutionEventLogs.Where(e => e.ExecutionId == exec.Id && e.EventCode == "CHECKPOINT").ToList();
        Assert.Empty(logs);
    }

    [Fact]
    public async Task FindRecoverable_FindsStuckExecutions()
    {
        var (manager, db) = Create();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Execution 1: RUNNING with checkpoint (crash candidate)
        var wi1 = new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/crash.csv", Status = JobStatus.Processing };
        db.WorkItems.Add(wi1);
        var exec1 = new WorkItemExecution { WorkItemId = wi1.Id, ExecutionNo = 1, Status = ExecutionStatus.Running };
        db.WorkItemExecutions.Add(exec1);
        await db.SaveChangesAsync();

        await manager.SaveCheckpointAsync(exec1.Id, 2, "partial_output");

        // Execution 2: COMPLETED (not recoverable)
        var wi2 = new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/done.csv", Status = JobStatus.Completed };
        db.WorkItems.Add(wi2);
        var exec2 = new WorkItemExecution { WorkItemId = wi2.Id, ExecutionNo = 1, Status = ExecutionStatus.Completed };
        db.WorkItemExecutions.Add(exec2);
        await db.SaveChangesAsync();

        var recoverable = await manager.FindRecoverableExecutionsAsync();

        Assert.Single(recoverable);
        Assert.Equal(exec1.Id, recoverable[0].ExecutionId);
        Assert.Equal(2, recoverable[0].LastCompletedStep);
    }

    [Fact]
    public async Task Scenario_CrashAndRecover()
    {
        var (manager, db) = Create();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Simulate: Pipeline execution starts, completes steps 1-2, crashes before step 3
        var wi = new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/important.csv", Status = JobStatus.Processing };
        db.WorkItems.Add(wi);
        var exec = new WorkItemExecution { WorkItemId = wi.Id, ExecutionNo = 1, Status = ExecutionStatus.Running };
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        // Step 1 completes → checkpoint
        await manager.SaveCheckpointAsync(exec.Id, 1, "{\"collected\":100}");
        // Step 2 completes → checkpoint
        await manager.SaveCheckpointAsync(exec.Id, 2, "{\"processed\":95,\"anomalies\":5}");
        // Step 3 would run but... CRASH!

        // === Engine restarts ===
        var recoverable = await manager.FindRecoverableExecutionsAsync();
        Assert.Single(recoverable);
        Assert.Equal(wi.Id, recoverable[0].WorkItemId);
        Assert.Equal(2, recoverable[0].LastCompletedStep);

        // Resume from step 3 (step after last checkpoint)
        var resumeFromStep = recoverable[0].LastCompletedStep + 1;
        Assert.Equal(3, resumeFromStep);

        // Simulate successful completion
        await manager.ClearCheckpointsAsync(exec.Id);
        var cleared = await manager.GetCheckpointAsync(exec.Id);
        Assert.Null(cleared);
    }
}
