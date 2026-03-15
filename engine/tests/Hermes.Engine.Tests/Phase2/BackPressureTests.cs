using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;
using Hermes.Engine.Services;

namespace Hermes.Engine.Tests.Phase2;

/// <summary>
/// Tests for back-pressure system.
/// References: NiFi FlowController back-pressure, MassTransit rate limiting.
///
/// Back-pressure behavior:
/// - Normal: queue < soft limit → no throttling
/// - Throttled: soft limit ≤ queue < hard limit → monitoring slows down (2x-10x)
/// - Paused: queue ≥ hard limit → monitoring stops entirely
/// </summary>
public class BackPressureTests
{
    private static (BackPressureManager Manager, HermesDbContext Db) CreateManager()
    {
        var (provider, db) = TestServiceHelper.CreateServices();
        var scopeFactory = provider.GetRequiredService<IServiceScopeFactory>();
        var manager = new BackPressureManager(scopeFactory, NullLogger<BackPressureManager>.Instance);
        return (manager, db);
    }

    [Fact]
    public async Task Normal_WhenQueueBelowSoftLimit()
    {
        var (manager, db) = CreateManager();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Add a few queued items (well below default soft limit of 100)
        for (int i = 0; i < 5; i++)
        {
            db.WorkItems.Add(new WorkItem
            {
                PipelineActivationId = activation.Id,
                PipelineInstanceId = pipeline.Id,
                SourceType = SourceType.File,
                SourceKey = $"/data/file_{i}.csv",
                Status = JobStatus.Queued
            });
        }
        await db.SaveChangesAsync();

        var state = await manager.GetStateAsync(pipeline.Id);

        Assert.Equal(BackPressureLevel.Normal, state.Level);
        Assert.Equal(5, state.QueuedCount);
        Assert.False(await manager.ShouldThrottleAsync(pipeline.Id));
        Assert.False(await manager.ShouldPauseAsync(pipeline.Id));
    }

    [Fact]
    public async Task Throttled_WhenQueueAtSoftLimit()
    {
        var (manager, db) = CreateManager();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Fill queue to soft limit (default 100)
        for (int i = 0; i < 100; i++)
        {
            db.WorkItems.Add(new WorkItem
            {
                PipelineActivationId = activation.Id,
                PipelineInstanceId = pipeline.Id,
                SourceType = SourceType.File,
                SourceKey = $"/data/throttle_{i}.csv",
                Status = JobStatus.Queued
            });
        }
        await db.SaveChangesAsync();

        var state = await manager.GetStateAsync(pipeline.Id);

        Assert.Equal(BackPressureLevel.Throttled, state.Level);
        Assert.True(await manager.ShouldThrottleAsync(pipeline.Id));
        Assert.False(await manager.ShouldPauseAsync(pipeline.Id));
    }

    [Fact]
    public async Task Paused_WhenQueueAtHardLimit()
    {
        var (manager, db) = CreateManager();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Fill queue to hard limit (default 500)
        for (int i = 0; i < 500; i++)
        {
            db.WorkItems.Add(new WorkItem
            {
                PipelineActivationId = activation.Id,
                PipelineInstanceId = pipeline.Id,
                SourceType = SourceType.File,
                SourceKey = $"/data/pause_{i}.csv",
                Status = JobStatus.Queued
            });
        }
        await db.SaveChangesAsync();

        var state = await manager.GetStateAsync(pipeline.Id);

        Assert.Equal(BackPressureLevel.Paused, state.Level);
        Assert.True(await manager.ShouldThrottleAsync(pipeline.Id));
        Assert.True(await manager.ShouldPauseAsync(pipeline.Id));
    }

    [Fact]
    public async Task ProcessingCountIncludedInTotal()
    {
        var (manager, db) = CreateManager();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // 60 queued + 50 processing = 110 total (above soft limit of 100)
        for (int i = 0; i < 60; i++)
        {
            db.WorkItems.Add(new WorkItem
            {
                PipelineActivationId = activation.Id,
                PipelineInstanceId = pipeline.Id,
                SourceType = SourceType.File,
                SourceKey = $"/data/q_{i}.csv",
                Status = JobStatus.Queued
            });
        }
        for (int i = 0; i < 50; i++)
        {
            db.WorkItems.Add(new WorkItem
            {
                PipelineActivationId = activation.Id,
                PipelineInstanceId = pipeline.Id,
                SourceType = SourceType.File,
                SourceKey = $"/data/p_{i}.csv",
                Status = JobStatus.Processing
            });
        }
        await db.SaveChangesAsync();

        var state = await manager.GetStateAsync(pipeline.Id);

        Assert.Equal(60, state.QueuedCount);
        Assert.Equal(50, state.ProcessingCount);
        Assert.Equal(BackPressureLevel.Throttled, state.Level);
    }

    [Fact]
    public void ThrottledInterval_ScalesLinearly()
    {
        var manager = new BackPressureManager(
            new ServiceCollection().BuildServiceProvider().GetRequiredService<IServiceScopeFactory>(),
            NullLogger<BackPressureManager>.Instance);

        var baseInterval = 5000; // 5 seconds

        // At soft limit: ~2x slowdown
        var atSoftLimit = new BackPressureState(Guid.Empty, 100, 0, 100, 500, BackPressureLevel.Throttled);
        var throttled = manager.GetThrottledIntervalMs(baseInterval, atSoftLimit);
        Assert.True(throttled >= baseInterval * 2);

        // At halfway: ~6x slowdown
        var halfway = new BackPressureState(Guid.Empty, 300, 0, 100, 500, BackPressureLevel.Throttled);
        var midThrottled = manager.GetThrottledIntervalMs(baseInterval, halfway);
        Assert.True(midThrottled > throttled);

        // Normal: no change
        var normal = new BackPressureState(Guid.Empty, 10, 0, 100, 500, BackPressureLevel.Normal);
        Assert.Equal(baseInterval, manager.GetThrottledIntervalMs(baseInterval, normal));

        // Paused: max
        var paused = new BackPressureState(Guid.Empty, 600, 0, 100, 500, BackPressureLevel.Paused);
        Assert.Equal(int.MaxValue, manager.GetThrottledIntervalMs(baseInterval, paused));
    }

    [Fact]
    public async Task CustomLimits_FromMonitoringConfig()
    {
        var (manager, db) = CreateManager();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Set custom limits via MonitoringConfig
        pipeline.MonitoringConfig = "{\"watch_path\":\"/data\",\"back_pressure_soft_limit\":10,\"back_pressure_hard_limit\":50}";
        await db.SaveChangesAsync();

        // Add 15 items (above custom soft limit of 10)
        for (int i = 0; i < 15; i++)
        {
            db.WorkItems.Add(new WorkItem
            {
                PipelineActivationId = activation.Id,
                PipelineInstanceId = pipeline.Id,
                SourceType = SourceType.File,
                SourceKey = $"/data/custom_{i}.csv",
                Status = JobStatus.Queued
            });
        }
        await db.SaveChangesAsync();

        var state = await manager.GetStateAsync(pipeline.Id);

        Assert.Equal(10, state.SoftLimit);
        Assert.Equal(50, state.HardLimit);
        Assert.Equal(BackPressureLevel.Throttled, state.Level);
    }

    [Fact]
    public async Task RecoveryFromThrottled_WhenQueueDrains()
    {
        var (manager, db) = CreateManager();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Add 150 items (above soft limit)
        var items = new List<WorkItem>();
        for (int i = 0; i < 150; i++)
        {
            var wi = new WorkItem
            {
                PipelineActivationId = activation.Id,
                PipelineInstanceId = pipeline.Id,
                SourceType = SourceType.File,
                SourceKey = $"/data/drain_{i}.csv",
                Status = JobStatus.Queued
            };
            db.WorkItems.Add(wi);
            items.Add(wi);
        }
        await db.SaveChangesAsync();

        // Verify throttled
        var state1 = await manager.GetStateAsync(pipeline.Id);
        Assert.Equal(BackPressureLevel.Throttled, state1.Level);

        // Process 100 items (complete them)
        foreach (var item in items.Take(100))
        {
            item.Status = JobStatus.Completed;
        }
        await db.SaveChangesAsync();

        // Now queue = 50 → should be Normal
        var state2 = await manager.GetStateAsync(pipeline.Id);
        Assert.Equal(BackPressureLevel.Normal, state2.Level);
        Assert.Equal(50, state2.QueuedCount);
    }

    [Fact]
    public async Task EmptyPipeline_Normal()
    {
        var (manager, db) = CreateManager();
        var (pipeline, _) = await TestDbHelper.SeedPipelineAsync(db);

        var state = await manager.GetStateAsync(pipeline.Id);

        Assert.Equal(BackPressureLevel.Normal, state.Level);
        Assert.Equal(0, state.QueuedCount);
        Assert.Equal(0, state.ProcessingCount);
    }
}
