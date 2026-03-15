using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;
using Hermes.Engine.Observability;

namespace Hermes.Engine.Services;

public interface IBackPressureManager
{
    Task<BackPressureState> GetStateAsync(Guid pipelineId, CancellationToken ct = default);
    Task<bool> ShouldThrottleAsync(Guid pipelineId, CancellationToken ct = default);
    Task<bool> ShouldPauseAsync(Guid pipelineId, CancellationToken ct = default);
    int GetThrottledIntervalMs(int baseIntervalMs, BackPressureState state);
}

public record BackPressureState(
    Guid PipelineId,
    int QueuedCount,
    int ProcessingCount,
    int SoftLimit,
    int HardLimit,
    BackPressureLevel Level);

public enum BackPressureLevel { Normal, Throttled, Paused }

public class BackPressureManager : IBackPressureManager
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<BackPressureManager> _logger;

    // Configurable limits (can be overridden per pipeline via MonitoringConfig)
    private const int DefaultSoftLimit = 100;  // Start throttling
    private const int DefaultHardLimit = 500;  // Pause monitoring

    public BackPressureManager(IServiceScopeFactory scopeFactory, ILogger<BackPressureManager> logger)
    {
        _scopeFactory = scopeFactory;
        _logger = logger;
    }

    public async Task<BackPressureState> GetStateAsync(Guid pipelineId, CancellationToken ct = default)
    {
        using var scope = _scopeFactory.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();

        var queued = await db.WorkItems
            .CountAsync(w => w.PipelineInstanceId == pipelineId && w.Status == JobStatus.Queued, ct);
        var processing = await db.WorkItems
            .CountAsync(w => w.PipelineInstanceId == pipelineId && w.Status == JobStatus.Processing, ct);

        // Try to get pipeline-specific limits from MonitoringConfig
        var pipeline = await db.PipelineInstances.FindAsync(new object[] { pipelineId }, ct);
        var (softLimit, hardLimit) = ParseLimits(pipeline?.MonitoringConfig);

        var total = queued + processing;
        var level = total >= hardLimit ? BackPressureLevel.Paused
                  : total >= softLimit ? BackPressureLevel.Throttled
                  : BackPressureLevel.Normal;

        // Update metrics
        HermesMetrics.WorkItemsQueued.Set(queued);
        HermesMetrics.WorkItemsProcessing.Set(processing);

        if (level != BackPressureLevel.Normal)
        {
            _logger.LogWarning("Back-pressure {Level} for pipeline {PipelineId}: {Queued} queued, {Processing} processing (soft={Soft}, hard={Hard})",
                level, pipelineId, queued, processing, softLimit, hardLimit);
        }

        return new BackPressureState(pipelineId, queued, processing, softLimit, hardLimit, level);
    }

    public async Task<bool> ShouldThrottleAsync(Guid pipelineId, CancellationToken ct = default)
    {
        var state = await GetStateAsync(pipelineId, ct);
        return state.Level >= BackPressureLevel.Throttled;
    }

    public async Task<bool> ShouldPauseAsync(Guid pipelineId, CancellationToken ct = default)
    {
        var state = await GetStateAsync(pipelineId, ct);
        return state.Level == BackPressureLevel.Paused;
    }

    public int GetThrottledIntervalMs(int baseIntervalMs, BackPressureState state)
    {
        return state.Level switch
        {
            BackPressureLevel.Paused => int.MaxValue, // Effectively pause
            BackPressureLevel.Throttled =>
                // Linearly scale: at soft limit = 2x, approaching hard limit = 10x
                (int)(baseIntervalMs * (2.0 + 8.0 * (state.QueuedCount - state.SoftLimit) /
                    Math.Max(1, state.HardLimit - state.SoftLimit))),
            _ => baseIntervalMs
        };
    }

    private static (int softLimit, int hardLimit) ParseLimits(string? monitoringConfig)
    {
        if (string.IsNullOrEmpty(monitoringConfig)) return (DefaultSoftLimit, DefaultHardLimit);
        try
        {
            var doc = System.Text.Json.JsonDocument.Parse(monitoringConfig);
            var soft = doc.RootElement.TryGetProperty("back_pressure_soft_limit", out var s) ? s.GetInt32() : DefaultSoftLimit;
            var hard = doc.RootElement.TryGetProperty("back_pressure_hard_limit", out var h) ? h.GetInt32() : DefaultHardLimit;
            return (soft, hard);
        }
        catch { return (DefaultSoftLimit, DefaultHardLimit); }
    }
}
