using Microsoft.Extensions.Logging.Abstractions;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Services;

namespace Hermes.Engine.Tests;

/// <summary>
/// Integration tests for ProcessingOrchestrator using in-memory DB.
/// Mirrors backend/tests/test_processing_orchestrator.py scenarios.
/// </summary>
public class ProcessingOrchestratorTests
{
    private static (ProcessingOrchestrator Orchestrator, Infrastructure.Data.HermesDbContext Db) CreateOrchestrator()
    {
        var db = TestDbHelper.CreateInMemoryDb();
        var snapshotResolver = new SnapshotResolver(db);
        var dispatcher = new FakeDispatcher(success: true);
        var logger = NullLogger<ProcessingOrchestrator>.Instance;
        var orchestrator = new ProcessingOrchestrator(db, dispatcher, snapshotResolver, logger);
        return (orchestrator, db);
    }

    [Fact]
    public async Task ProcessWorkItem_Success_CompletesExecution()
    {
        var (orchestrator, db) = CreateOrchestrator();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        var workItem = new WorkItem
        {
            PipelineActivationId = activation.Id,
            PipelineInstanceId = pipeline.Id,
            SourceType = SourceType.File,
            SourceKey = "/data/test.csv",
            Status = JobStatus.Queued
        };
        db.WorkItems.Add(workItem);
        await db.SaveChangesAsync();

        var execution = await orchestrator.ProcessWorkItemAsync(workItem.Id);

        Assert.Equal(ExecutionStatus.Completed, execution.Status);
        Assert.Equal(1, execution.ExecutionNo);
        Assert.NotNull(execution.DurationMs);
        Assert.True(execution.DurationMs > 0);

        // Work item should be completed
        var updated = await db.WorkItems.FindAsync(workItem.Id);
        Assert.Equal(JobStatus.Completed, updated!.Status);
        Assert.Equal(1, updated.ExecutionCount);
    }

    [Fact]
    public async Task ProcessWorkItem_DispatcherFails_StopOnError()
    {
        var db = TestDbHelper.CreateInMemoryDb();
        var snapshotResolver = new SnapshotResolver(db);
        var dispatcher = new FakeDispatcher(success: false); // All steps fail
        var orchestrator = new ProcessingOrchestrator(db, dispatcher, snapshotResolver,
            NullLogger<ProcessingOrchestrator>.Instance);
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        var workItem = new WorkItem
        {
            PipelineActivationId = activation.Id,
            PipelineInstanceId = pipeline.Id,
            SourceType = SourceType.File,
            SourceKey = "/data/fail.csv",
            Status = JobStatus.Queued
        };
        db.WorkItems.Add(workItem);
        await db.SaveChangesAsync();

        var execution = await orchestrator.ProcessWorkItemAsync(workItem.Id);

        Assert.Equal(ExecutionStatus.Failed, execution.Status);
        var updated = await db.WorkItems.FindAsync(workItem.Id);
        Assert.Equal(JobStatus.Failed, updated!.Status);
    }

    [Fact]
    public async Task ProcessWorkItem_SkipOnError_ContinuesAfterFailure()
    {
        var db = TestDbHelper.CreateInMemoryDb();
        var snapshotResolver = new SnapshotResolver(db);
        // Fail on step 1 (Collect), but step has OnError=Stop
        // Step 2 (Algorithm) has OnError=Skip in seed data
        var dispatcher = new FakeDispatcher(success: false);
        var orchestrator = new ProcessingOrchestrator(db, dispatcher, snapshotResolver,
            NullLogger<ProcessingOrchestrator>.Instance);
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Change step 1 to Skip so processing continues
        var step1 = pipeline.Steps.First(s => s.StepOrder == 1);
        step1.OnError = OnErrorAction.Skip;
        await db.SaveChangesAsync();

        var workItem = new WorkItem
        {
            PipelineActivationId = activation.Id,
            PipelineInstanceId = pipeline.Id,
            SourceType = SourceType.File,
            SourceKey = "/data/partial.csv",
            Status = JobStatus.Queued
        };
        db.WorkItems.Add(workItem);
        await db.SaveChangesAsync();

        var execution = await orchestrator.ProcessWorkItemAsync(workItem.Id);

        // Step 1 skipped, step 2 skipped, step 3 fails with Stop → Failed
        Assert.Equal(ExecutionStatus.Failed, execution.Status);
    }

    [Fact]
    public async Task ProcessWorkItem_CapturesSnapshot()
    {
        var (orchestrator, db) = CreateOrchestrator();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        var workItem = new WorkItem
        {
            PipelineActivationId = activation.Id,
            PipelineInstanceId = pipeline.Id,
            SourceType = SourceType.File,
            SourceKey = "/data/snapshot.csv",
            Status = JobStatus.Queued
        };
        db.WorkItems.Add(workItem);
        await db.SaveChangesAsync();

        var execution = await orchestrator.ProcessWorkItemAsync(workItem.Id);

        var snapshot = db.ExecutionSnapshots.FirstOrDefault(s => s.ExecutionId == execution.Id);
        Assert.NotNull(snapshot);
        Assert.NotNull(snapshot.SnapshotHash);
        Assert.NotEqual("{}", snapshot.CollectorConfig);
    }

    [Fact]
    public async Task ProcessWorkItem_LogsEvents()
    {
        var (orchestrator, db) = CreateOrchestrator();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        var workItem = new WorkItem
        {
            PipelineActivationId = activation.Id,
            PipelineInstanceId = pipeline.Id,
            SourceType = SourceType.File,
            SourceKey = "/data/events.csv",
            Status = JobStatus.Queued
        };
        db.WorkItems.Add(workItem);
        await db.SaveChangesAsync();

        var execution = await orchestrator.ProcessWorkItemAsync(workItem.Id);

        var logs = db.ExecutionEventLogs.Where(l => l.ExecutionId == execution.Id).ToList();
        Assert.True(logs.Count >= 2); // At least EXECUTION_START and EXECUTION_DONE
        Assert.Contains(logs, l => l.EventCode == "EXECUTION_START");
        Assert.Contains(logs, l => l.EventCode == "EXECUTION_DONE");
    }

    [Fact]
    public async Task BulkReprocess_CreatesRequests()
    {
        var (orchestrator, db) = CreateOrchestrator();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        var items = Enumerable.Range(0, 3).Select(i => new WorkItem
        {
            PipelineActivationId = activation.Id,
            PipelineInstanceId = pipeline.Id,
            SourceType = SourceType.File,
            SourceKey = $"/data/bulk_{i}.csv",
            Status = JobStatus.Failed
        }).ToList();
        db.WorkItems.AddRange(items);
        await db.SaveChangesAsync();

        var requests = await orchestrator.BulkReprocessAsync(
            items.Select(i => i.Id).ToList(),
            "Config updated",
            "operator:test");

        Assert.Equal(3, requests.Count);
        Assert.All(requests, r =>
        {
            Assert.Equal(ReprocessStatus.Pending, r.Status);
            Assert.Equal("operator:test", r.RequestedBy);
        });
    }

    [Fact]
    public async Task Reprocess_FromSpecificStep()
    {
        var (orchestrator, db) = CreateOrchestrator();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        var workItem = new WorkItem
        {
            PipelineActivationId = activation.Id,
            PipelineInstanceId = pipeline.Id,
            SourceType = SourceType.File,
            SourceKey = "/data/reprocess.csv",
            Status = JobStatus.Failed,
            ExecutionCount = 1
        };
        db.WorkItems.Add(workItem);
        await db.SaveChangesAsync();

        var execution = await orchestrator.ProcessWorkItemAsync(
            workItem.Id,
            triggerType: TriggerType.Reprocess,
            triggerSource: "operator:kim",
            startFromStep: 2);

        Assert.Equal(TriggerType.Reprocess, execution.TriggerType);
        Assert.Equal("operator:kim", execution.TriggerSource);
        Assert.Equal(2, execution.ExecutionNo);
    }

    /// <summary>Fake dispatcher that always succeeds or always fails.</summary>
    private class FakeDispatcher : IExecutionDispatcher
    {
        private readonly bool _success;
        public FakeDispatcher(bool success) => _success = success;

        public Task<ExecutionResult> DispatchAsync(
            ExecutionType executionType, string? executionRef, string configJson,
            string? inputDataJson = null, Dictionary<string, string>? context = null,
            CancellationToken ct = default)
        {
            if (_success)
            {
                return Task.FromResult(new ExecutionResult(
                    true, "{\"result\":\"ok\"}", "{\"status\":\"success\"}", 100,
                    new List<LogEntry> { new(DateTimeOffset.UtcNow, "INFO", "Step completed") }));
            }
            return Task.FromResult(new ExecutionResult(
                false, null, null, 50,
                new List<LogEntry> { new(DateTimeOffset.UtcNow, "ERROR", "Step failed") }));
        }
    }
}
