using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;

namespace Hermes.Engine.Services;

/// <summary>
/// Handles graceful shutdown: drain monitoring, finish in-flight jobs, recover orphans on startup.
/// </summary>
public class GracefulShutdownHandler : IHostedService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IMonitoringEngine _monitoringEngine;
    private readonly ILogger<GracefulShutdownHandler> _logger;

    public GracefulShutdownHandler(
        IServiceScopeFactory scopeFactory,
        IMonitoringEngine monitoringEngine,
        ILogger<GracefulShutdownHandler> logger)
    {
        _scopeFactory = scopeFactory;
        _monitoringEngine = monitoringEngine;
        _logger = logger;
    }

    public async Task StartAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("GracefulShutdownHandler: recovering orphaned items from previous crash...");
        await RecoverOrphansAsync(cancellationToken);
    }

    public async Task StopAsync(CancellationToken cancellationToken)
    {
        _logger.LogInformation("GracefulShutdownHandler: initiating graceful shutdown...");
        await DrainAsync(cancellationToken);
    }

    private async Task RecoverOrphansAsync(CancellationToken ct)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        // 1. Recover stuck PROCESSING items (from previous crash)
        var stuckItems = await db.WorkItems
            .Where(w => w.Status == JobStatus.Processing)
            .ToListAsync(ct);

        foreach (var item in stuckItems)
        {
            item.Status = JobStatus.Queued; // Re-queue for processing
            _logger.LogWarning("Recovered orphaned work item {Id} (was PROCESSING, re-queued)", item.Id);
        }

        // 2. Clean up stuck RUNNING executions
        var stuckExecutions = await db.WorkItemExecutions
            .Where(e => e.Status == ExecutionStatus.Running)
            .ToListAsync(ct);

        foreach (var exec in stuckExecutions)
        {
            exec.Status = ExecutionStatus.Failed;
            exec.EndedAt = DateTimeOffset.UtcNow;
            _logger.LogWarning("Marked orphaned execution {Id} as Failed", exec.Id);
        }

        // 3. Clean up stuck activations
        var stuckActivations = await db.PipelineActivations
            .Where(a => a.Status == ActivationStatus.Running || a.Status == ActivationStatus.Starting)
            .Where(a => a.WorkerId == Environment.MachineName)
            .ToListAsync(ct);

        foreach (var activation in stuckActivations)
        {
            activation.Status = ActivationStatus.Stopped;
            activation.StoppedAt = DateTimeOffset.UtcNow;
            activation.ErrorMessage = "Recovered after engine restart";
            _logger.LogWarning("Cleaned up stuck activation {Id}", activation.Id);
        }

        if (stuckItems.Count + stuckExecutions.Count + stuckActivations.Count > 0)
        {
            await db.SaveChangesAsync(ct);
            _logger.LogInformation("Recovery complete: {Items} items re-queued, {Execs} executions failed, {Acts} activations stopped",
                stuckItems.Count, stuckExecutions.Count, stuckActivations.Count);
        }
        else
        {
            _logger.LogInformation("No orphaned items found — clean startup");
        }
    }

    private async Task DrainAsync(CancellationToken ct)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        // Stop all monitoring
        var activeActivations = await db.PipelineActivations
            .Where(a => a.Status == ActivationStatus.Running || a.Status == ActivationStatus.Starting)
            .ToListAsync(ct);

        foreach (var activation in activeActivations)
        {
            await _monitoringEngine.StopMonitoringAsync(activation.Id, ct);
            activation.Status = ActivationStatus.Stopped;
            activation.StoppedAt = DateTimeOffset.UtcNow;
        }
        await db.SaveChangesAsync(ct);

        _logger.LogInformation("Drain complete: stopped {Count} active monitoring tasks", activeActivations.Count);

        // Wait for in-flight processing to complete (up to 30 seconds)
        var deadline = DateTimeOffset.UtcNow.AddSeconds(30);
        while (DateTimeOffset.UtcNow < deadline)
        {
            var processing = await db.WorkItems.CountAsync(w => w.Status == JobStatus.Processing, ct);
            if (processing == 0)
            {
                _logger.LogInformation("All in-flight items completed");
                break;
            }
            _logger.LogInformation("Waiting for {Count} in-flight items to complete...", processing);
            await Task.Delay(1000, ct);
        }
    }
}
