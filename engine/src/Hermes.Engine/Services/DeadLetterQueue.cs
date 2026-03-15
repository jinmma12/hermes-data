using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;

namespace Hermes.Engine.Services;

public interface IDeadLetterQueue
{
    Task<DeadLetterEntry> EnqueueAsync(
        Guid workItemId, Guid? executionId, Guid pipelineId,
        string errorCode, string errorMessage, string? stackTrace = null,
        string? lastStepType = null, int? lastStepOrder = null,
        string? inputDataJson = null, CancellationToken ct = default);
    Task<List<DeadLetterEntry>> GetEntriesAsync(
        Guid? pipelineId = null, DeadLetterStatus? status = null,
        int limit = 50, CancellationToken ct = default);
    Task<DeadLetterEntry?> ResolveAsync(Guid entryId, string resolvedBy, string note, CancellationToken ct = default);
    Task<DeadLetterEntry?> RetryAsync(Guid entryId, CancellationToken ct = default);
    Task<int> DiscardAsync(List<Guid> entryIds, string discardedBy, CancellationToken ct = default);
    Task<DlqStats> GetStatsAsync(CancellationToken ct = default);
}

public record DlqStats(int Total, int Quarantined, int Retrying, int Resolved, int Discarded);

public class DeadLetterQueue : IDeadLetterQueue
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<DeadLetterQueue> _logger;

    private const int MaxFailuresBeforePoisonPill = 5;

    public DeadLetterQueue(IServiceScopeFactory scopeFactory, ILogger<DeadLetterQueue> logger)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    public async Task<DeadLetterEntry> EnqueueAsync(
        Guid workItemId, Guid? executionId, Guid pipelineId,
        string errorCode, string errorMessage, string? stackTrace = null,
        string? lastStepType = null, int? lastStepOrder = null,
        string? inputDataJson = null, CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        // Check existing failure count
        var existingCount = await db.DeadLetterEntries
            .CountAsync(d => d.WorkItemId == workItemId, ct);

        var workItem = await db.WorkItems.FindAsync(new object[] { workItemId }, ct);
        var entry = new DeadLetterEntry
        {
            WorkItemId = workItemId,
            ExecutionId = executionId,
            PipelineInstanceId = pipelineId,
            ErrorCode = errorCode,
            ErrorMessage = errorMessage,
            StackTrace = stackTrace,
            FailureCount = existingCount + 1,
            LastStepType = lastStepType,
            LastStepOrder = lastStepOrder,
            OriginalSourceKey = workItem?.SourceKey ?? "unknown",
            InputDataJson = inputDataJson,
            Status = existingCount + 1 >= MaxFailuresBeforePoisonPill
                ? DeadLetterStatus.Quarantined // Poison pill - stop retrying
                : DeadLetterStatus.Quarantined
        };

        db.DeadLetterEntries.Add(entry);
        await db.SaveChangesAsync(ct);

        _logger.LogWarning("DLQ: Work item {WorkItemId} added to dead letter queue (failure #{Count}): {Error}",
            workItemId, entry.FailureCount, errorMessage);

        return entry;
    }

    public async Task<List<DeadLetterEntry>> GetEntriesAsync(
        Guid? pipelineId = null, DeadLetterStatus? status = null,
        int limit = 50, CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        var query = db.DeadLetterEntries.AsQueryable();
        if (pipelineId.HasValue)
            query = query.Where(d => d.PipelineInstanceId == pipelineId.Value);
        if (status.HasValue)
            query = query.Where(d => d.Status == status.Value);

        return await query
            .OrderByDescending(d => d.CreatedAt)
            .Take(limit)
            .ToListAsync(ct);
    }

    public async Task<DeadLetterEntry?> ResolveAsync(Guid entryId, string resolvedBy, string note, CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        var entry = await db.DeadLetterEntries.FindAsync(new object[] { entryId }, ct);
        if (entry == null) return null;

        entry.Status = DeadLetterStatus.Resolved;
        entry.ResolvedBy = resolvedBy;
        entry.ResolvedAt = DateTimeOffset.UtcNow;
        entry.ResolutionNote = note;
        await db.SaveChangesAsync(ct);

        _logger.LogInformation("DLQ: Entry {EntryId} resolved by {ResolvedBy}: {Note}", entryId, resolvedBy, note);
        return entry;
    }

    public async Task<DeadLetterEntry?> RetryAsync(Guid entryId, CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        var entry = await db.DeadLetterEntries.FindAsync(new object[] { entryId }, ct);
        if (entry == null) return null;

        entry.Status = DeadLetterStatus.Retrying;
        await db.SaveChangesAsync(ct);

        // Re-queue the work item
        var workItem = await db.WorkItems.FindAsync(new object[] { entry.WorkItemId }, ct);
        if (workItem != null)
        {
            workItem.Status = JobStatus.Queued;
            await db.SaveChangesAsync(ct);
        }

        _logger.LogInformation("DLQ: Entry {EntryId} marked for retry, work item {WorkItemId} re-queued",
            entryId, entry.WorkItemId);
        return entry;
    }

    public async Task<int> DiscardAsync(List<Guid> entryIds, string discardedBy, CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        var entries = await db.DeadLetterEntries
            .Where(d => entryIds.Contains(d.Id))
            .ToListAsync(ct);

        foreach (var entry in entries)
        {
            entry.Status = DeadLetterStatus.Discarded;
            entry.ResolvedBy = discardedBy;
            entry.ResolvedAt = DateTimeOffset.UtcNow;
        }
        await db.SaveChangesAsync(ct);

        _logger.LogInformation("DLQ: {Count} entries discarded by {DiscardedBy}", entries.Count, discardedBy);
        return entries.Count;
    }

    public async Task<DlqStats> GetStatsAsync(CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        var total = await db.DeadLetterEntries.CountAsync(ct);
        var quarantined = await db.DeadLetterEntries.CountAsync(d => d.Status == DeadLetterStatus.Quarantined, ct);
        var retrying = await db.DeadLetterEntries.CountAsync(d => d.Status == DeadLetterStatus.Retrying, ct);
        var resolved = await db.DeadLetterEntries.CountAsync(d => d.Status == DeadLetterStatus.Resolved, ct);
        var discarded = await db.DeadLetterEntries.CountAsync(d => d.Status == DeadLetterStatus.Discarded, ct);

        return new DlqStats(total, quarantined, retrying, resolved, discarded);
    }
}
