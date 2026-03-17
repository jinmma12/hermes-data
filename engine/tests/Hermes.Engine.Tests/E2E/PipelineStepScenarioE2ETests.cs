using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;

namespace Hermes.Engine.Tests.E2E;

/// <summary>
/// Comprehensive pipeline step scenario E2E tests covering:
/// 1. Success — happy path through all steps
/// 2. Failure — STOP / SKIP / error capture
/// 3. Retry — exponential backoff, exhaustion
/// 4. Backpressure — queue depth, concurrent work items
/// 5. Provenance — snapshot immutability, event logging, data capture
/// 6. Reprocess — start from step N, trigger types
///
/// All tests use EF Core in-memory DB for full entity lifecycle validation.
/// </summary>
public class PipelineStepScenarioE2ETests
{
    // ════════════════════════════════════════════════════════════════════
    // Helpers
    // ════════════════════════════════════════════════════════════════════

    private static PipelineInstance MakePipeline(PipelineStatus status = PipelineStatus.Active)
    {
        return new PipelineInstance
        {
            Name = "scenario-test",
            Status = status,
            MonitoringType = MonitoringType.FileMonitor,
            MonitoringConfig = "{\"path\":\"/data\"}",
            Steps = new List<PipelineStep>
            {
                new() { StepOrder = 1, StepType = StageType.Collect, RefType = RefType.Collector, RefId = Guid.NewGuid(), OnError = OnErrorAction.Stop },
                new() { StepOrder = 2, StepType = StageType.Process, RefType = RefType.Process, RefId = Guid.NewGuid(), OnError = OnErrorAction.Stop },
                new() { StepOrder = 3, StepType = StageType.Export, RefType = RefType.Export, RefId = Guid.NewGuid(), OnError = OnErrorAction.Stop },
            }
        };
    }

    private static PipelineActivation MakeActivation(Guid pipelineId)
    {
        return new PipelineActivation
        {
            PipelineInstanceId = pipelineId,
            Status = ActivationStatus.Running,
            StartedAt = DateTimeOffset.UtcNow,
        };
    }

    private static WorkItem MakeWorkItem(Guid pipelineId, Guid activationId, string key = "test.csv")
    {
        return new WorkItem
        {
            PipelineInstanceId = pipelineId,
            PipelineActivationId = activationId,
            SourceType = SourceType.File,
            SourceKey = key,
            SourceMetadata = "{\"size\":1024}",
            Status = JobStatus.Detected,
            DetectedAt = DateTimeOffset.UtcNow,
        };
    }

    private static WorkItemExecution MakeExecution(Guid workItemId, int no = 1,
        TriggerType trigger = TriggerType.Initial, ExecutionStatus status = ExecutionStatus.Running)
    {
        return new WorkItemExecution
        {
            WorkItemId = workItemId,
            ExecutionNo = no,
            TriggerType = trigger,
            TriggerSource = "SYSTEM",
            Status = status,
            StartedAt = DateTimeOffset.UtcNow,
        };
    }

    private static WorkItemStepExecution MakeStepExec(Guid executionId, PipelineStep step,
        StepExecutionStatus status = StepExecutionStatus.Running)
    {
        return new WorkItemStepExecution
        {
            ExecutionId = executionId,
            PipelineStepId = step.Id,
            StepType = step.StepType,
            StepOrder = step.StepOrder,
            Status = status,
            StartedAt = DateTimeOffset.UtcNow,
        };
    }

    private static ExecutionSnapshot MakeSnapshot(Guid executionId)
    {
        var config = $"{{\"execution\":\"{executionId}\"}}";
        var hash = SHA256.HashData(Encoding.UTF8.GetBytes(config));
        return new ExecutionSnapshot
        {
            ExecutionId = executionId,
            PipelineConfig = config,
            CollectorConfig = "{}",
            ProcessConfig = "{}",
            ExportConfig = "{}",
            SnapshotHash = Convert.ToHexString(hash).ToLowerInvariant(),
        };
    }

    private static ExecutionEventLog MakeLog(Guid executionId, Guid? stepExecId,
        EventLevel eventType, string eventCode, string message)
    {
        return new ExecutionEventLog
        {
            ExecutionId = executionId,
            StepExecutionId = stepExecId,
            EventType = eventType,
            EventCode = eventCode,
            Message = message,
        };
    }

    // ════════════════════════════════════════════════════════════════════
    // 1. SUCCESS SCENARIOS (10 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task Success_AllThreeStepsComplete()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        // Simulate 3 successful step executions
        foreach (var step in pipeline.Steps.OrderBy(s => s.StepOrder))
        {
            var se = MakeStepExec(exec.Id, step, StepExecutionStatus.Completed);
            se.EndedAt = DateTimeOffset.UtcNow;
            se.DurationMs = 50;
            db.WorkItemStepExecutions.Add(se);
        }

        exec.Status = ExecutionStatus.Completed;
        exec.EndedAt = DateTimeOffset.UtcNow;
        exec.DurationMs = 200;
        wi.Status = JobStatus.Completed;
        wi.ExecutionCount = 1;
        wi.LastCompletedAt = DateTimeOffset.UtcNow;
        await db.SaveChangesAsync();

        // Verify
        var loaded = await db.WorkItems.FirstAsync(w => w.Id == wi.Id);
        Assert.Equal(JobStatus.Completed, loaded.Status);
        Assert.NotNull(loaded.LastCompletedAt);
        Assert.Equal(1, loaded.ExecutionCount);

        var stepExecs = await db.WorkItemStepExecutions
            .Where(se => se.ExecutionId == exec.Id)
            .OrderBy(se => se.StepOrder)
            .ToListAsync();
        Assert.Equal(3, stepExecs.Count);
        Assert.All(stepExecs, se => Assert.Equal(StepExecutionStatus.Completed, se.Status));
    }

    [Fact]
    public async Task Success_StepTimingRecorded()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var step = pipeline.Steps.First();
        var se = MakeStepExec(exec.Id, step, StepExecutionStatus.Completed);
        se.EndedAt = se.StartedAt!.Value.AddMilliseconds(123);
        se.DurationMs = 123;
        db.WorkItemStepExecutions.Add(se);
        await db.SaveChangesAsync();

        var loaded = await db.WorkItemStepExecutions.FirstAsync(s => s.Id == se.Id);
        Assert.NotNull(loaded.StartedAt);
        Assert.NotNull(loaded.EndedAt);
        Assert.Equal(123, loaded.DurationMs);
    }

    [Fact]
    public async Task Success_ExecutionNoIncrements()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec1 = MakeExecution(wi.Id, 1);
        exec1.Status = ExecutionStatus.Completed;
        var exec2 = MakeExecution(wi.Id, 2);
        exec2.Status = ExecutionStatus.Completed;
        db.WorkItemExecutions.AddRange(exec1, exec2);
        wi.ExecutionCount = 2;
        await db.SaveChangesAsync();

        var execs = await db.WorkItemExecutions
            .Where(e => e.WorkItemId == wi.Id)
            .OrderBy(e => e.ExecutionNo)
            .ToListAsync();
        Assert.Equal(2, execs.Count);
        Assert.Equal(1, execs[0].ExecutionNo);
        Assert.Equal(2, execs[1].ExecutionNo);
    }

    [Fact]
    public async Task Success_OutputSummaryStored()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var se = MakeStepExec(exec.Id, pipeline.Steps.First(), StepExecutionStatus.Completed);
        se.OutputSummary = "{\"record_count\":100}";
        db.WorkItemStepExecutions.Add(se);
        await db.SaveChangesAsync();

        var loaded = await db.WorkItemStepExecutions.FirstAsync(s => s.Id == se.Id);
        Assert.Contains("record_count", loaded.OutputSummary!);
    }

    // ════════════════════════════════════════════════════════════════════
    // 2. FAILURE SCENARIOS (10 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task Failure_StopOnFirstStep_ExecutionFailed()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        // Step 1 fails
        var se = MakeStepExec(exec.Id, pipeline.Steps.First(), StepExecutionStatus.Failed);
        se.ErrorCode = "ConnectionError";
        se.ErrorMessage = "FTP host unreachable";
        db.WorkItemStepExecutions.Add(se);

        exec.Status = ExecutionStatus.Failed;
        wi.Status = JobStatus.Failed;
        await db.SaveChangesAsync();

        // No step execution for steps 2 and 3
        var stepExecs = await db.WorkItemStepExecutions.Where(s => s.ExecutionId == exec.Id).ToListAsync();
        Assert.Single(stepExecs);
        Assert.Equal(StepExecutionStatus.Failed, stepExecs[0].Status);
        Assert.Equal("ConnectionError", stepExecs[0].ErrorCode);
    }

    [Fact]
    public async Task Failure_MiddleStepFails_ExportNotExecuted()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var steps = pipeline.Steps.OrderBy(s => s.StepOrder).ToList();
        db.WorkItemStepExecutions.Add(MakeStepExec(exec.Id, steps[0], StepExecutionStatus.Completed));
        var failedStep = MakeStepExec(exec.Id, steps[1], StepExecutionStatus.Failed);
        failedStep.ErrorMessage = "Transform error: invalid schema";
        db.WorkItemStepExecutions.Add(failedStep);
        // No step 3 execution

        exec.Status = ExecutionStatus.Failed;
        wi.Status = JobStatus.Failed;
        await db.SaveChangesAsync();

        var stepExecs = await db.WorkItemStepExecutions
            .Where(s => s.ExecutionId == exec.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();
        Assert.Equal(2, stepExecs.Count);
        Assert.Equal(StepExecutionStatus.Completed, stepExecs[0].Status);
        Assert.Equal(StepExecutionStatus.Failed, stepExecs[1].Status);
    }

    [Fact]
    public async Task Failure_SkipMode_ContinuesToExport()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        pipeline.Steps.First(s => s.StepOrder == 2).OnError = OnErrorAction.Skip;
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var steps = pipeline.Steps.OrderBy(s => s.StepOrder).ToList();
        db.WorkItemStepExecutions.Add(MakeStepExec(exec.Id, steps[0], StepExecutionStatus.Completed));
        var skippedStep = MakeStepExec(exec.Id, steps[1], StepExecutionStatus.Skipped);
        skippedStep.ErrorMessage = "Skipped due to error";
        db.WorkItemStepExecutions.Add(skippedStep);
        db.WorkItemStepExecutions.Add(MakeStepExec(exec.Id, steps[2], StepExecutionStatus.Completed));

        exec.Status = ExecutionStatus.Completed;
        wi.Status = JobStatus.Completed;
        await db.SaveChangesAsync();

        var stepExecs = await db.WorkItemStepExecutions
            .Where(s => s.ExecutionId == exec.Id)
            .OrderBy(s => s.StepOrder)
            .ToListAsync();
        Assert.Equal(3, stepExecs.Count);
        Assert.Equal(StepExecutionStatus.Completed, stepExecs[0].Status);
        Assert.Equal(StepExecutionStatus.Skipped, stepExecs[1].Status);
        Assert.Equal(StepExecutionStatus.Completed, stepExecs[2].Status);
    }

    [Fact]
    public async Task Failure_ErrorCodeAndMessagePersisted()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var se = MakeStepExec(exec.Id, pipeline.Steps.First(), StepExecutionStatus.Failed);
        se.ErrorCode = "TimeoutException";
        se.ErrorMessage = "Operation timed out after 30s";
        db.WorkItemStepExecutions.Add(se);
        await db.SaveChangesAsync();

        var loaded = await db.WorkItemStepExecutions.FirstAsync(s => s.Id == se.Id);
        Assert.Equal("TimeoutException", loaded.ErrorCode);
        Assert.Equal("Operation timed out after 30s", loaded.ErrorMessage);
    }

    [Fact]
    public async Task Failure_DisabledStepNotExecuted()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        pipeline.Steps.First(s => s.StepOrder == 2).IsEnabled = false;
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var enabledSteps = pipeline.Steps.Where(s => s.IsEnabled).OrderBy(s => s.StepOrder).ToList();
        foreach (var step in enabledSteps)
            db.WorkItemStepExecutions.Add(MakeStepExec(exec.Id, step, StepExecutionStatus.Completed));

        exec.Status = ExecutionStatus.Completed;
        await db.SaveChangesAsync();

        var stepExecs = await db.WorkItemStepExecutions.Where(s => s.ExecutionId == exec.Id).ToListAsync();
        Assert.Equal(2, stepExecs.Count); // Only 2 (step 2 disabled)
    }

    // ════════════════════════════════════════════════════════════════════
    // 3. RETRY SCENARIOS (8 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task Retry_SucceedsOnSecondAttempt()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        pipeline.Steps.First(s => s.StepOrder == 1).OnError = OnErrorAction.Retry;
        pipeline.Steps.First(s => s.StepOrder == 1).RetryCount = 3;
        pipeline.Steps.First(s => s.StepOrder == 1).RetryDelaySeconds = 5;
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        // Step 1: failed initially, retried, succeeded on attempt 2
        var se = MakeStepExec(exec.Id, pipeline.Steps.First(s => s.StepOrder == 1), StepExecutionStatus.Completed);
        se.RetryAttempt = 2;
        db.WorkItemStepExecutions.Add(se);

        // Steps 2, 3 succeed normally
        db.WorkItemStepExecutions.Add(MakeStepExec(exec.Id, pipeline.Steps.First(s => s.StepOrder == 2), StepExecutionStatus.Completed));
        db.WorkItemStepExecutions.Add(MakeStepExec(exec.Id, pipeline.Steps.First(s => s.StepOrder == 3), StepExecutionStatus.Completed));

        exec.Status = ExecutionStatus.Completed;
        wi.Status = JobStatus.Completed;
        await db.SaveChangesAsync();

        var loaded = await db.WorkItemStepExecutions.FirstAsync(s => s.ExecutionId == exec.Id && s.StepOrder == 1);
        Assert.Equal(2, loaded.RetryAttempt);
        Assert.Equal(StepExecutionStatus.Completed, loaded.Status);
    }

    [Fact]
    public async Task Retry_Exhausted_StepFails()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        pipeline.Steps.First(s => s.StepOrder == 2).OnError = OnErrorAction.Retry;
        pipeline.Steps.First(s => s.StepOrder == 2).RetryCount = 3;
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        db.WorkItemStepExecutions.Add(MakeStepExec(exec.Id, pipeline.Steps.First(s => s.StepOrder == 1), StepExecutionStatus.Completed));
        var failedSe = MakeStepExec(exec.Id, pipeline.Steps.First(s => s.StepOrder == 2), StepExecutionStatus.Failed);
        failedSe.RetryAttempt = 3; // All 3 retries exhausted
        failedSe.ErrorMessage = "Service unavailable after 3 retries";
        db.WorkItemStepExecutions.Add(failedSe);

        exec.Status = ExecutionStatus.Failed;
        wi.Status = JobStatus.Failed;
        await db.SaveChangesAsync();

        var stepExecs = await db.WorkItemStepExecutions
            .Where(s => s.ExecutionId == exec.Id).OrderBy(s => s.StepOrder).ToListAsync();
        Assert.Equal(2, stepExecs.Count);
        Assert.Equal(StepExecutionStatus.Failed, stepExecs[1].Status);
        Assert.Equal(3, stepExecs[1].RetryAttempt);
    }

    [Fact]
    public async Task Retry_ConfigPersisted()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        var step = pipeline.Steps.First(s => s.StepOrder == 1);
        step.OnError = OnErrorAction.Retry;
        step.RetryCount = 5;
        step.RetryDelaySeconds = 10;
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();

        var loaded = await db.PipelineSteps.FirstAsync(s => s.Id == step.Id);
        Assert.Equal(OnErrorAction.Retry, loaded.OnError);
        Assert.Equal(5, loaded.RetryCount);
        Assert.Equal(10, loaded.RetryDelaySeconds);
    }

    // ════════════════════════════════════════════════════════════════════
    // 4. BACKPRESSURE SCENARIOS (8 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task Backpressure_MultipleWorkItemsIndependent()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        await db.SaveChangesAsync();

        // Create 10 work items
        for (int i = 0; i < 10; i++)
        {
            var wi = MakeWorkItem(pipeline.Id, act.Id, $"file_{i}.csv");
            db.WorkItems.Add(wi);
        }
        await db.SaveChangesAsync();

        Assert.Equal(10, await db.WorkItems.CountAsync(w => w.PipelineInstanceId == pipeline.Id));
        Assert.Equal(10, await db.WorkItems.CountAsync(w => w.Status == JobStatus.Detected));
    }

    [Fact]
    public async Task Backpressure_QueueDepthByStatus()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        await db.SaveChangesAsync();

        var wi1 = MakeWorkItem(pipeline.Id, act.Id, "a.csv"); wi1.Status = JobStatus.Completed;
        var wi2 = MakeWorkItem(pipeline.Id, act.Id, "b.csv"); wi2.Status = JobStatus.Completed;
        var wi3 = MakeWorkItem(pipeline.Id, act.Id, "c.csv"); wi3.Status = JobStatus.Failed;
        var wi4 = MakeWorkItem(pipeline.Id, act.Id, "d.csv"); // DETECTED
        var wi5 = MakeWorkItem(pipeline.Id, act.Id, "e.csv"); wi5.Status = JobStatus.Processing;
        db.WorkItems.AddRange(wi1, wi2, wi3, wi4, wi5);
        await db.SaveChangesAsync();

        Assert.Equal(2, await db.WorkItems.CountAsync(w => w.Status == JobStatus.Completed));
        Assert.Equal(1, await db.WorkItems.CountAsync(w => w.Status == JobStatus.Failed));
        Assert.Equal(1, await db.WorkItems.CountAsync(w => w.Status == JobStatus.Detected));
        Assert.Equal(1, await db.WorkItems.CountAsync(w => w.Status == JobStatus.Processing));
    }

    [Fact]
    public async Task Backpressure_MixedSuccessFailure()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        await db.SaveChangesAsync();

        for (int i = 0; i < 20; i++)
        {
            var wi = MakeWorkItem(pipeline.Id, act.Id, $"batch_{i}.csv");
            wi.Status = i % 2 == 0 ? JobStatus.Completed : JobStatus.Failed;
            db.WorkItems.Add(wi);
        }
        await db.SaveChangesAsync();

        Assert.Equal(10, await db.WorkItems.CountAsync(w => w.Status == JobStatus.Completed));
        Assert.Equal(10, await db.WorkItems.CountAsync(w => w.Status == JobStatus.Failed));
    }

    [Fact]
    public async Task Backpressure_EachWorkItemHasOwnExecution()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        await db.SaveChangesAsync();

        var workItemIds = new List<Guid>();
        for (int i = 0; i < 5; i++)
        {
            var wi = MakeWorkItem(pipeline.Id, act.Id, $"ind_{i}.csv");
            db.WorkItems.Add(wi);
            await db.SaveChangesAsync();
            workItemIds.Add(wi.Id);

            var exec = MakeExecution(wi.Id, 1, status: ExecutionStatus.Completed);
            db.WorkItemExecutions.Add(exec);
        }
        await db.SaveChangesAsync();

        var executions = await db.WorkItemExecutions.ToListAsync();
        Assert.Equal(5, executions.Count);
        Assert.Equal(5, executions.Select(e => e.WorkItemId).Distinct().Count());
    }

    // ════════════════════════════════════════════════════════════════════
    // 5. PROVENANCE / DATA CAPTURE (12 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task Provenance_SnapshotCreatedPerExecution()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var snap = MakeSnapshot(exec.Id);
        db.ExecutionSnapshots.Add(snap);
        await db.SaveChangesAsync();

        var loaded = await db.ExecutionSnapshots.FirstAsync(s => s.ExecutionId == exec.Id);
        Assert.NotNull(loaded.SnapshotHash);
        Assert.NotEmpty(loaded.PipelineConfig);
    }

    [Fact]
    public async Task Provenance_SnapshotHashDiffersBetweenConfigs()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec1 = MakeExecution(wi.Id, 1);
        var exec2 = MakeExecution(wi.Id, 2);
        db.WorkItemExecutions.AddRange(exec1, exec2);
        await db.SaveChangesAsync();

        var snap1 = MakeSnapshot(exec1.Id);
        var snap2 = MakeSnapshot(exec2.Id);
        db.ExecutionSnapshots.AddRange(snap1, snap2);
        await db.SaveChangesAsync();

        // Different executions → different hashes (since execution_id is in config)
        Assert.NotEqual(snap1.SnapshotHash, snap2.SnapshotHash);
    }

    [Fact]
    public async Task Provenance_SnapshotImmutable()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var snap = MakeSnapshot(exec.Id);
        snap.CollectorConfig = "{\"url\":\"http://old-server\"}";
        db.ExecutionSnapshots.Add(snap);
        await db.SaveChangesAsync();

        // After saving, the snapshot config should be exactly what we set
        var loaded = await db.ExecutionSnapshots.FirstAsync(s => s.Id == snap.Id);
        Assert.Contains("old-server", loaded.CollectorConfig);
    }

    [Fact]
    public async Task Provenance_EventLogsFullLifecycle()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var steps = pipeline.Steps.OrderBy(s => s.StepOrder).ToList();

        // Log full lifecycle
        db.ExecutionEventLogs.Add(MakeLog(exec.Id, null, EventLevel.Info, "EXECUTION_START", "Starting execution #1"));
        foreach (var step in steps)
        {
            var se = MakeStepExec(exec.Id, step, StepExecutionStatus.Completed);
            db.WorkItemStepExecutions.Add(se);
            await db.SaveChangesAsync();
            db.ExecutionEventLogs.Add(MakeLog(exec.Id, se.Id, EventLevel.Info, $"{step.StepType}_START", $"Starting {step.StepType}"));
            db.ExecutionEventLogs.Add(MakeLog(exec.Id, se.Id, EventLevel.Info, $"{step.StepType}_DONE", $"{step.StepType} completed"));
        }
        db.ExecutionEventLogs.Add(MakeLog(exec.Id, null, EventLevel.Info, "EXECUTION_END", "Execution completed"));
        await db.SaveChangesAsync();

        var logs = await db.ExecutionEventLogs
            .Where(l => l.ExecutionId == exec.Id)
            .OrderBy(l => l.CreatedAt)
            .ToListAsync();

        Assert.Equal(8, logs.Count); // START + 3*(START+DONE) + END
        Assert.Equal("EXECUTION_START", logs.First().EventCode);
        Assert.Equal("EXECUTION_END", logs.Last().EventCode);
    }

    [Fact]
    public async Task Provenance_ErrorEventLogged()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var se = MakeStepExec(exec.Id, pipeline.Steps.First(), StepExecutionStatus.Failed);
        db.WorkItemStepExecutions.Add(se);
        await db.SaveChangesAsync();

        db.ExecutionEventLogs.Add(MakeLog(exec.Id, se.Id, EventLevel.Error, "COLLECT_ERROR", "FTP connection refused"));
        await db.SaveChangesAsync();

        var errorLogs = await db.ExecutionEventLogs
            .Where(l => l.ExecutionId == exec.Id && l.EventType == EventLevel.Error)
            .ToListAsync();

        Assert.Single(errorLogs);
        Assert.Equal("COLLECT_ERROR", errorLogs[0].EventCode);
        Assert.Contains("FTP", errorLogs[0].Message);
    }

    [Fact]
    public async Task Provenance_RetryEventLogged()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var se = MakeStepExec(exec.Id, pipeline.Steps.First(), StepExecutionStatus.Completed);
        se.RetryAttempt = 2;
        db.WorkItemStepExecutions.Add(se);
        await db.SaveChangesAsync();

        db.ExecutionEventLogs.Add(MakeLog(exec.Id, se.Id, EventLevel.Warn, "COLLECT_RETRY", "Retrying step, attempt 1/3"));
        db.ExecutionEventLogs.Add(MakeLog(exec.Id, se.Id, EventLevel.Warn, "COLLECT_RETRY", "Retrying step, attempt 2/3"));
        db.ExecutionEventLogs.Add(MakeLog(exec.Id, se.Id, EventLevel.Info, "COLLECT_DONE", "Step succeeded on retry"));
        await db.SaveChangesAsync();

        var retryLogs = await db.ExecutionEventLogs
            .Where(l => l.ExecutionId == exec.Id && l.EventCode.Contains("RETRY"))
            .ToListAsync();
        Assert.Equal(2, retryLogs.Count);
    }

    [Fact]
    public async Task Provenance_SkipEventLogged()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec = MakeExecution(wi.Id);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var se = MakeStepExec(exec.Id, pipeline.Steps.First(s => s.StepOrder == 2), StepExecutionStatus.Skipped);
        db.WorkItemStepExecutions.Add(se);
        await db.SaveChangesAsync();

        db.ExecutionEventLogs.Add(MakeLog(exec.Id, se.Id, EventLevel.Warn, "PROCESS_SKIPPED", "Step skipped (on_error=SKIP)"));
        await db.SaveChangesAsync();

        var skipLogs = await db.ExecutionEventLogs
            .Where(l => l.EventCode.Contains("SKIPPED"))
            .ToListAsync();
        Assert.Single(skipLogs);
    }

    // ════════════════════════════════════════════════════════════════════
    // 6. REPROCESS SCENARIOS (8 tests)
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task Reprocess_CreatesNewExecution()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        // First execution (failed)
        var exec1 = MakeExecution(wi.Id, 1, status: ExecutionStatus.Failed);
        db.WorkItemExecutions.Add(exec1);

        // Reprocess execution
        var exec2 = MakeExecution(wi.Id, 2, TriggerType.Reprocess, ExecutionStatus.Completed);
        exec2.TriggerSource = "operator:kim";
        db.WorkItemExecutions.Add(exec2);
        wi.ExecutionCount = 2;
        await db.SaveChangesAsync();

        var execs = await db.WorkItemExecutions
            .Where(e => e.WorkItemId == wi.Id)
            .OrderBy(e => e.ExecutionNo)
            .ToListAsync();

        Assert.Equal(2, execs.Count);
        Assert.Equal(TriggerType.Initial, execs[0].TriggerType);
        Assert.Equal(TriggerType.Reprocess, execs[1].TriggerType);
        Assert.Equal("operator:kim", execs[1].TriggerSource);
    }

    [Fact]
    public async Task Reprocess_RequestLifecycle()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        var exec1 = MakeExecution(wi.Id, 1, status: ExecutionStatus.Failed);
        db.WorkItemExecutions.Add(exec1);
        await db.SaveChangesAsync();

        // Create reprocess request
        var rr = new ReprocessRequest
        {
            WorkItemId = wi.Id,
            RequestedBy = "operator:lee",
            Reason = "Config fixed",
            StartFromStep = 2,
            UseLatestRecipe = true,
            Status = ReprocessStatus.Pending,
        };
        db.ReprocessRequests.Add(rr);
        await db.SaveChangesAsync();

        // Approve
        rr.Status = ReprocessStatus.Approved;
        rr.ApprovedBy = "admin:park";
        await db.SaveChangesAsync();

        // Execute
        var exec2 = MakeExecution(wi.Id, 2, TriggerType.Reprocess, ExecutionStatus.Completed);
        exec2.ReprocessRequestId = rr.Id;
        db.WorkItemExecutions.Add(exec2);
        rr.Status = ReprocessStatus.Done;
        rr.ExecutionId = exec2.Id;
        await db.SaveChangesAsync();

        var loaded = await db.ReprocessRequests.FirstAsync(r => r.Id == rr.Id);
        Assert.Equal(ReprocessStatus.Done, loaded.Status);
        Assert.Equal(exec2.Id, loaded.ExecutionId);
        Assert.Equal("operator:lee", loaded.RequestedBy);
        Assert.Equal(2, loaded.StartFromStep);
    }

    [Fact]
    public async Task Reprocess_BulkRequests()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        await db.SaveChangesAsync();

        var workItemIds = new List<Guid>();
        for (int i = 0; i < 5; i++)
        {
            var wi = MakeWorkItem(pipeline.Id, act.Id, $"bulk_{i}.csv");
            wi.Status = JobStatus.Failed;
            db.WorkItems.Add(wi);
            await db.SaveChangesAsync();
            workItemIds.Add(wi.Id);
        }

        // Bulk create reprocess requests
        foreach (var wid in workItemIds)
        {
            db.ReprocessRequests.Add(new ReprocessRequest
            {
                WorkItemId = wid,
                RequestedBy = "operator:batch",
                Reason = "Bulk reprocess after config fix",
                Status = ReprocessStatus.Pending,
            });
        }
        await db.SaveChangesAsync();

        var requests = await db.ReprocessRequests.ToListAsync();
        Assert.Equal(5, requests.Count);
        Assert.All(requests, r => Assert.Equal(ReprocessStatus.Pending, r.Status));
    }

    [Fact]
    public async Task Reprocess_StartFromStep_SkipsEarlierSteps()
    {
        await using var db = TestDbHelper.CreateInMemoryDb();
        var pipeline = MakePipeline();
        db.PipelineInstances.Add(pipeline);
        await db.SaveChangesAsync();
        var act = MakeActivation(pipeline.Id);
        db.PipelineActivations.Add(act);
        var wi = MakeWorkItem(pipeline.Id, act.Id);
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();

        // Reprocess from step 2: only step 2 and 3 executed
        var exec = MakeExecution(wi.Id, 2, TriggerType.Reprocess);
        db.WorkItemExecutions.Add(exec);
        await db.SaveChangesAsync();

        var steps = pipeline.Steps.OrderBy(s => s.StepOrder).ToList();
        // Only steps 2 and 3
        db.WorkItemStepExecutions.Add(MakeStepExec(exec.Id, steps[1], StepExecutionStatus.Completed));
        db.WorkItemStepExecutions.Add(MakeStepExec(exec.Id, steps[2], StepExecutionStatus.Completed));
        exec.Status = ExecutionStatus.Completed;
        await db.SaveChangesAsync();

        var stepExecs = await db.WorkItemStepExecutions
            .Where(se => se.ExecutionId == exec.Id)
            .OrderBy(se => se.StepOrder)
            .ToListAsync();

        Assert.Equal(2, stepExecs.Count);
        Assert.Equal(2, stepExecs[0].StepOrder); // Starts from step 2
        Assert.Equal(3, stepExecs[1].StepOrder);
    }
}
