using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging.Abstractions;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;
using Hermes.Engine.Services;

namespace Hermes.Engine.Tests.Phase2;

/// <summary>
/// Tests for Dead Letter Queue system.
/// References: NiFi penalty/failure routing, RabbitMQ DLX, MassTransit error pipeline.
///
/// DLQ behavior:
/// - Failed items are quarantined with full error context
/// - Operators can retry, resolve (with notes), or discard entries
/// - Poison pills detected after N failures → permanent quarantine
/// - Stats tracked per pipeline for dashboard
/// </summary>
public class DeadLetterQueueTests
{
    private static (DeadLetterQueue Dlq, HermesDbContext Db) CreateDlq()
    {
        var (provider, db) = TestServiceHelper.CreateServices();
        var scopeFactory = provider.GetRequiredService<IServiceScopeFactory>();
        var dlq = new DeadLetterQueue(scopeFactory, NullLogger<DeadLetterQueue>.Instance);
        return (dlq, db);
    }

    [Fact]
    public async Task Enqueue_CreatesEntryWithFullContext()
    {
        var (dlq, db) = CreateDlq();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);
        var workItem = await CreateWorkItemAsync(db, pipeline, activation);

        var entry = await dlq.EnqueueAsync(
            workItem.Id, Guid.NewGuid(), pipeline.Id,
            errorCode: "CONNECTION_TIMEOUT",
            errorMessage: "Failed to connect to S3 bucket after 30s",
            stackTrace: "at Hermes.Engine.Services.ExecutionDispatcher...",
            lastStepType: "TRANSFER",
            lastStepOrder: 3,
            inputDataJson: "{\"records\":150}");

        Assert.NotNull(entry);
        Assert.Equal(workItem.Id, entry.WorkItemId);
        Assert.Equal("CONNECTION_TIMEOUT", entry.ErrorCode);
        Assert.Equal(DeadLetterStatus.Quarantined, entry.Status);
        Assert.Equal(1, entry.FailureCount);
        Assert.Equal("TRANSFER", entry.LastStepType);
        Assert.Equal(3, entry.LastStepOrder);
        Assert.Equal(workItem.SourceKey, entry.OriginalSourceKey);
    }

    [Fact]
    public async Task Enqueue_IncrementsFailureCount()
    {
        var (dlq, db) = CreateDlq();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);
        var workItem = await CreateWorkItemAsync(db, pipeline, activation);

        var entry1 = await dlq.EnqueueAsync(workItem.Id, null, pipeline.Id, "ERR1", "First failure");
        Assert.Equal(1, entry1.FailureCount);

        var entry2 = await dlq.EnqueueAsync(workItem.Id, null, pipeline.Id, "ERR2", "Second failure");
        Assert.Equal(2, entry2.FailureCount);

        var entry3 = await dlq.EnqueueAsync(workItem.Id, null, pipeline.Id, "ERR3", "Third failure");
        Assert.Equal(3, entry3.FailureCount);
    }

    [Fact]
    public async Task GetEntries_FilterByPipeline()
    {
        var (dlq, db) = CreateDlq();
        var (pipeline1, activation1) = await TestDbHelper.SeedPipelineAsync(db);

        var wi1 = await CreateWorkItemAsync(db, pipeline1, activation1);
        var wi2 = await CreateWorkItemAsync(db, pipeline1, activation1, "/data/other.csv");

        await dlq.EnqueueAsync(wi1.Id, null, pipeline1.Id, "ERR", "err1");
        await dlq.EnqueueAsync(wi2.Id, null, pipeline1.Id, "ERR", "err2");

        var entries = await dlq.GetEntriesAsync(pipelineId: pipeline1.Id);
        Assert.Equal(2, entries.Count);
    }

    [Fact]
    public async Task GetEntries_FilterByStatus()
    {
        var (dlq, db) = CreateDlq();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        var wi1 = await CreateWorkItemAsync(db, pipeline, activation);
        var wi2 = await CreateWorkItemAsync(db, pipeline, activation, "/data/other.csv");

        await dlq.EnqueueAsync(wi1.Id, null, pipeline.Id, "ERR", "err1");
        var entry2 = await dlq.EnqueueAsync(wi2.Id, null, pipeline.Id, "ERR", "err2");

        // Resolve one
        await dlq.ResolveAsync(entry2.Id, "admin", "Fixed config");

        var quarantined = await dlq.GetEntriesAsync(status: DeadLetterStatus.Quarantined);
        Assert.Single(quarantined);

        var resolved = await dlq.GetEntriesAsync(status: DeadLetterStatus.Resolved);
        Assert.Single(resolved);
    }

    [Fact]
    public async Task Resolve_SetsResolvedFields()
    {
        var (dlq, db) = CreateDlq();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);
        var workItem = await CreateWorkItemAsync(db, pipeline, activation);

        var entry = await dlq.EnqueueAsync(workItem.Id, null, pipeline.Id, "ERR", "error");

        var resolved = await dlq.ResolveAsync(entry.Id, "operator:kim", "Fixed upstream API config");

        Assert.NotNull(resolved);
        Assert.Equal(DeadLetterStatus.Resolved, resolved.Status);
        Assert.Equal("operator:kim", resolved.ResolvedBy);
        Assert.Equal("Fixed upstream API config", resolved.ResolutionNote);
        Assert.NotNull(resolved.ResolvedAt);
    }

    [Fact]
    public async Task Retry_RequeuesWorkItem()
    {
        var (dlq, db) = CreateDlq();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);
        var workItem = await CreateWorkItemAsync(db, pipeline, activation);
        workItem.Status = JobStatus.Failed;
        await db.SaveChangesAsync();

        var entry = await dlq.EnqueueAsync(workItem.Id, null, pipeline.Id, "ERR", "transient error");

        var retried = await dlq.RetryAsync(entry.Id);

        Assert.NotNull(retried);
        Assert.Equal(DeadLetterStatus.Retrying, retried.Status);

        // Work item should be re-queued (reload to see changes from DLQ's scope)
        await db.Entry(workItem).ReloadAsync();
        Assert.Equal(JobStatus.Queued, workItem.Status);
    }

    [Fact]
    public async Task Discard_BulkDiscardEntries()
    {
        var (dlq, db) = CreateDlq();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        var entries = new List<DeadLetterEntry>();
        for (int i = 0; i < 5; i++)
        {
            var wi = await CreateWorkItemAsync(db, pipeline, activation, $"/data/discard_{i}.csv");
            entries.Add(await dlq.EnqueueAsync(wi.Id, null, pipeline.Id, "ERR", $"error {i}"));
        }

        var discarded = await dlq.DiscardAsync(entries.Select(e => e.Id).ToList(), "admin");

        Assert.Equal(5, discarded);
        var stats = await dlq.GetStatsAsync();
        Assert.Equal(5, stats.Discarded);
        Assert.Equal(0, stats.Quarantined);
    }

    [Fact]
    public async Task Stats_AggregatesCorrectly()
    {
        var (dlq, db) = CreateDlq();
        var (pipeline, activation) = await TestDbHelper.SeedPipelineAsync(db);

        // Create entries in different states
        var wi1 = await CreateWorkItemAsync(db, pipeline, activation, "/data/s1.csv");
        var wi2 = await CreateWorkItemAsync(db, pipeline, activation, "/data/s2.csv");
        var wi3 = await CreateWorkItemAsync(db, pipeline, activation, "/data/s3.csv");
        var wi4 = await CreateWorkItemAsync(db, pipeline, activation, "/data/s4.csv");

        var e1 = await dlq.EnqueueAsync(wi1.Id, null, pipeline.Id, "ERR", "err1"); // Quarantined
        var e2 = await dlq.EnqueueAsync(wi2.Id, null, pipeline.Id, "ERR", "err2");
        await dlq.ResolveAsync(e2.Id, "admin", "fixed"); // Resolved
        var e3 = await dlq.EnqueueAsync(wi3.Id, null, pipeline.Id, "ERR", "err3");
        await dlq.RetryAsync(e3.Id); // Retrying
        var e4 = await dlq.EnqueueAsync(wi4.Id, null, pipeline.Id, "ERR", "err4");
        await dlq.DiscardAsync(new List<Guid> { e4.Id }, "admin"); // Discarded

        var stats = await dlq.GetStatsAsync();

        Assert.Equal(4, stats.Total);
        Assert.Equal(1, stats.Quarantined);
        Assert.Equal(1, stats.Resolved);
        Assert.Equal(1, stats.Retrying);
        Assert.Equal(1, stats.Discarded);
    }

    [Fact]
    public async Task Resolve_NonExistentEntry_ReturnsNull()
    {
        var (dlq, _) = CreateDlq();
        var result = await dlq.ResolveAsync(Guid.NewGuid(), "admin", "note");
        Assert.Null(result);
    }

    private static async Task<WorkItem> CreateWorkItemAsync(
        HermesDbContext db, PipelineInstance pipeline, PipelineActivation activation,
        string sourceKey = "/data/test.csv")
    {
        var wi = new WorkItem
        {
            PipelineActivationId = activation.Id,
            PipelineInstanceId = pipeline.Id,
            SourceType = SourceType.File,
            SourceKey = sourceKey,
            Status = JobStatus.Queued
        };
        db.WorkItems.Add(wi);
        await db.SaveChangesAsync();
        return wi;
    }
}
