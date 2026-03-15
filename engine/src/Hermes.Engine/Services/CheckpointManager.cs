using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;

namespace Hermes.Engine.Services;

/// <summary>
/// Manages execution checkpoints for exactly-once processing.
/// After each successful step, a checkpoint is saved. On crash recovery,
/// execution resumes from the last checkpoint instead of re-running all steps.
///
/// Inspired by: Kafka consumer offsets, Flink checkpoints, NiFi FlowFile tracking.
/// </summary>
public interface ICheckpointManager
{
    /// <summary>Save a checkpoint after a step completes successfully.</summary>
    Task SaveCheckpointAsync(Guid executionId, int completedStepOrder, string? outputJson, CancellationToken ct = default);

    /// <summary>Get the last checkpoint for an execution (null if no checkpoint).</summary>
    Task<ExecutionCheckpoint?> GetCheckpointAsync(Guid executionId, CancellationToken ct = default);

    /// <summary>Clear all checkpoints for an execution (after full completion or cancellation).</summary>
    Task ClearCheckpointsAsync(Guid executionId, CancellationToken ct = default);

    /// <summary>Find executions that have checkpoints but didn't complete (crash recovery candidates).</summary>
    Task<List<RecoverableExecution>> FindRecoverableExecutionsAsync(CancellationToken ct = default);
}

public record ExecutionCheckpoint(
    Guid ExecutionId,
    int LastCompletedStep,
    string? LastOutputJson,
    DateTimeOffset CheckpointedAt);

public record RecoverableExecution(
    Guid ExecutionId,
    Guid WorkItemId,
    int LastCompletedStep,
    string? LastOutputJson);

public class CheckpointManager : ICheckpointManager
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<CheckpointManager> _logger;

    // In-memory checkpoint store (fast, survives within process lifetime)
    // For cross-process durability, checkpoints are also persisted to DB via ExecutionEventLog
    private readonly Dictionary<Guid, ExecutionCheckpoint> _checkpoints = new();

    public CheckpointManager(IServiceScopeFactory scopeFactory, ILogger<CheckpointManager> logger)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    public async Task SaveCheckpointAsync(Guid executionId, int completedStepOrder, string? outputJson, CancellationToken ct = default)
    {
        var checkpoint = new ExecutionCheckpoint(executionId, completedStepOrder, outputJson, DateTimeOffset.UtcNow);
        _checkpoints[executionId] = checkpoint;

        // Persist to DB for crash recovery
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();
        db.ExecutionEventLogs.Add(new ExecutionEventLog
        {
            ExecutionId = executionId,
            EventType = EventLevel.Info,
            EventCode = "CHECKPOINT",
            Message = $"Checkpoint saved at step {completedStepOrder}",
            DetailJson = JsonSerializer.Serialize(new
            {
                completed_step = completedStepOrder,
                has_output = outputJson != null,
                checkpointed_at = DateTimeOffset.UtcNow
            })
        });
        await db.SaveChangesAsync(ct);

        _logger.LogDebug("Checkpoint saved: execution {Id}, step {Step}", executionId, completedStepOrder);
    }

    public Task<ExecutionCheckpoint?> GetCheckpointAsync(Guid executionId, CancellationToken ct = default)
    {
        _checkpoints.TryGetValue(executionId, out var checkpoint);
        return Task.FromResult(checkpoint);
    }

    public async Task ClearCheckpointsAsync(Guid executionId, CancellationToken ct = default)
    {
        _checkpoints.Remove(executionId);

        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();
        var logs = await db.ExecutionEventLogs
            .Where(e => e.ExecutionId == executionId && e.EventCode == "CHECKPOINT")
            .ToListAsync(ct);
        db.ExecutionEventLogs.RemoveRange(logs);
        await db.SaveChangesAsync(ct);

        _logger.LogDebug("Checkpoints cleared for execution {Id}", executionId);
    }

    public async Task<List<RecoverableExecution>> FindRecoverableExecutionsAsync(CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        // Find RUNNING executions that have CHECKPOINT events (crashed mid-execution)
        var running = await db.WorkItemExecutions
            .Where(e => e.Status == ExecutionStatus.Running)
            .ToListAsync(ct);

        var recoverable = new List<RecoverableExecution>();
        foreach (var exec in running)
        {
            var lastCheckpoint = await db.ExecutionEventLogs
                .Where(e => e.ExecutionId == exec.Id && e.EventCode == "CHECKPOINT")
                .OrderByDescending(e => e.CreatedAt)
                .FirstOrDefaultAsync(ct);

            if (lastCheckpoint?.DetailJson != null)
            {
                var detail = JsonDocument.Parse(lastCheckpoint.DetailJson);
                var step = detail.RootElement.GetProperty("completed_step").GetInt32();

                recoverable.Add(new RecoverableExecution(
                    exec.Id, exec.WorkItemId, step, null));
            }
        }

        if (recoverable.Count > 0)
            _logger.LogInformation("Found {Count} recoverable executions with checkpoints", recoverable.Count);

        return recoverable;
    }
}
