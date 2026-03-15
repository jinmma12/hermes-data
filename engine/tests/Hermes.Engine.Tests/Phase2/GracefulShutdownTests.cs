using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;
using Hermes.Engine.Services;

namespace Hermes.Engine.Tests.Phase2;

/// <summary>
/// Tests for graceful shutdown and crash recovery.
/// References: NiFi FlowController shutdown, Kafka consumer group rebalance,
/// MassTransit bus stop with pending messages.
/// </summary>
public class GracefulShutdownTests
{
    private static (GracefulShutdownHandler Handler, HermesDbContext Db) Create()
    {
        var (provider, db) = TestServiceHelper.CreateServices();
        var scopeFactory = provider.GetRequiredService<IServiceScopeFactory>();
        var handler = new GracefulShutdownHandler(scopeFactory, new NoOpMonitoringEngine(),
            NullLogger<GracefulShutdownHandler>.Instance);
        return (handler, db);
    }

    [Fact]
    public async Task Recovery_OrphanedProcessingItems_ReQueued()
    {
        var (handler, db) = Create();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        for (int i = 0; i < 3; i++)
            db.WorkItems.Add(new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = $"/data/orphan_{i}.csv", Status = JobStatus.Processing });
        await db.SaveChangesAsync();

        await handler.StartAsync(CancellationToken.None);

        // Reload tracked entities to see changes from handler's scope
        foreach (var e in db.ChangeTracker.Entries().ToList()) await e.ReloadAsync();
        var items = db.WorkItems.Where(w => w.PipelineInstanceId == pipeline.Id).ToList();
        Assert.Equal(3, items.Count);
        Assert.All(items, wi => Assert.Equal(JobStatus.Queued, wi.Status));
    }

    [Fact]
    public async Task Recovery_StuckExecutions_MarkedFailed()
    {
        var (handler, db) = Create();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        var workItem = new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/data/stuck.csv", Status = JobStatus.Processing };
        db.WorkItems.Add(workItem);
        await db.SaveChangesAsync();

        var execution = new WorkItemExecution { WorkItemId = workItem.Id, ExecutionNo = 1, Status = ExecutionStatus.Running, StartedAt = DateTimeOffset.UtcNow.AddMinutes(-30) };
        db.WorkItemExecutions.Add(execution);
        await db.SaveChangesAsync();

        await handler.StartAsync(CancellationToken.None);

        foreach (var e in db.ChangeTracker.Entries().ToList()) await e.ReloadAsync();
        Assert.Equal(ExecutionStatus.Failed, execution.Status);
        Assert.NotNull(execution.EndedAt);
    }

    [Fact]
    public async Task Recovery_StuckActivations_Stopped()
    {
        var (handler, db) = Create();
        var (pipeline, _) = await TestDbHelper.SeedPipelineAsync(db);

        var stuckActivation = new PipelineActivation { PipelineInstanceId = pipeline.Id, Status = ActivationStatus.Running, WorkerId = Environment.MachineName, StartedAt = DateTimeOffset.UtcNow.AddHours(-1) };
        db.PipelineActivations.Add(stuckActivation);
        await db.SaveChangesAsync();

        await handler.StartAsync(CancellationToken.None);

        foreach (var e in db.ChangeTracker.Entries().ToList()) await e.ReloadAsync();
        Assert.Equal(ActivationStatus.Stopped, stuckActivation.Status);
        Assert.NotNull(stuckActivation.StoppedAt);
        Assert.Contains("restart", stuckActivation.ErrorMessage!);
    }

    [Fact]
    public async Task Recovery_CleanStartup_NoOrphans()
    {
        var (handler, db) = Create();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        db.WorkItems.Add(new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/data/done.csv", Status = JobStatus.Completed });
        db.WorkItems.Add(new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/data/waiting.csv", Status = JobStatus.Queued });
        await db.SaveChangesAsync();

        await handler.StartAsync(CancellationToken.None);

        Assert.Equal(1, db.WorkItems.Count(w => w.Status == JobStatus.Completed));
        Assert.Equal(1, db.WorkItems.Count(w => w.Status == JobStatus.Queued));
    }

    [Fact]
    public async Task Recovery_MixedOrphans_AllRecovered()
    {
        var (handler, db) = Create();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        db.WorkItems.Add(new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/data/ok.csv", Status = JobStatus.Completed });
        db.WorkItems.Add(new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/data/orphan1.csv", Status = JobStatus.Processing });
        db.WorkItems.Add(new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/data/orphan2.csv", Status = JobStatus.Processing });
        db.WorkItems.Add(new WorkItem { PipelineActivationId = activation.Id, PipelineInstanceId = pipeline.Id, SourceType = SourceType.File, SourceKey = "/data/queued.csv", Status = JobStatus.Queued });
        await db.SaveChangesAsync();

        await handler.StartAsync(CancellationToken.None);

        Assert.Equal(1, db.WorkItems.Count(w => w.Status == JobStatus.Completed));
        Assert.Equal(3, db.WorkItems.Count(w => w.Status == JobStatus.Queued));
    }

    private class NoOpMonitoringEngine : IMonitoringEngine
    {
        public Task StartMonitoringAsync(PipelineActivation activation, CancellationToken ct = default) => Task.CompletedTask;
        public Task StopMonitoringAsync(Guid activationId, CancellationToken ct = default) => Task.CompletedTask;
        public bool IsMonitoring(Guid activationId) => false;
    }
}
