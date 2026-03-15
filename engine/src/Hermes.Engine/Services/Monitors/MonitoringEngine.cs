using System.Collections.Concurrent;
using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;
using Hermes.Engine.Services;

namespace Hermes.Engine.Services.Monitors;

public class MonitoringEngine : IMonitoringEngine
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly IConditionEvaluator _conditionEvaluator;
    private readonly IBackPressureManager _backPressureManager;
    private readonly IHttpClientFactory _httpClientFactory;
    private readonly ILogger<MonitoringEngine> _logger;
    private readonly ConcurrentDictionary<Guid, CancellationTokenSource> _monitors = new();

    public MonitoringEngine(
        IServiceScopeFactory scopeFactory,
        IConditionEvaluator conditionEvaluator,
        IBackPressureManager backPressureManager,
        IHttpClientFactory httpClientFactory,
        ILogger<MonitoringEngine> logger)
    {
        _scopeFactory = scopeFactory;
        _conditionEvaluator = conditionEvaluator;
        _backPressureManager = backPressureManager;
        _httpClientFactory = httpClientFactory;
        _logger = logger;
    }

    public bool IsMonitoring(Guid activationId) => _monitors.ContainsKey(activationId);

    public Task StartMonitoringAsync(PipelineActivation activation, CancellationToken ct = default)
    {
        if (_monitors.ContainsKey(activation.Id))
        {
            _logger.LogWarning("Already monitoring activation {Id}", activation.Id);
            return Task.CompletedTask;
        }

        var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        _monitors[activation.Id] = cts;

        var pipeline = activation.PipelineInstance;
        var monitor = CreateMonitor(pipeline);
        var intervalMs = ParseIntervalMs(pipeline.MonitoringConfig);

        _ = Task.Run(() => MonitoringLoopAsync(activation.Id, pipeline.Id, monitor, intervalMs, cts.Token), cts.Token);

        _logger.LogInformation("Started monitoring for activation {Id}, pipeline {Pipeline}, interval {Interval}ms",
            activation.Id, pipeline.Name, intervalMs);
        return Task.CompletedTask;
    }

    public Task StopMonitoringAsync(Guid activationId, CancellationToken ct = default)
    {
        if (_monitors.TryRemove(activationId, out var cts))
        {
            cts.Cancel();
            cts.Dispose();
            _logger.LogInformation("Stopped monitoring for activation {Id}", activationId);
        }
        return Task.CompletedTask;
    }

    private async Task MonitoringLoopAsync(Guid activationId, Guid pipelineId, BaseMonitor monitor, int intervalMs, CancellationToken ct)
    {
        while (!ct.IsCancellationRequested)
        {
            try
            {
                // Back-pressure check
                var bpState = await _backPressureManager.GetStateAsync(pipelineId, ct);
                if (bpState.Level == BackPressureLevel.Paused)
                {
                    _logger.LogWarning("Back-pressure PAUSED for pipeline {Id}, queue={Queued}", pipelineId, bpState.QueuedCount);
                    await Task.Delay(10000, ct); // Wait 10s before re-checking
                    continue;
                }

                var events = await monitor.PollAsync(ct);
                if (events.Count > 0)
                {
                    using var scope = _scopeFactory.CreateScope();
                    var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();
                    var pipeline = await db.PipelineInstances.FindAsync(new object[] { pipelineId }, ct);

                    foreach (var evt in events)
                    {
                        if (!_conditionEvaluator.Evaluate(evt, pipeline!))
                            continue;

                        var dedupKey = _conditionEvaluator.GenerateDedupKey(evt);
                        var exists = await db.WorkItems
                            .AnyAsync(w => w.PipelineInstanceId == pipelineId && w.DedupKey == dedupKey, ct);
                        if (exists) continue;

                        var workItem = new WorkItem
                        {
                            PipelineActivationId = activationId,
                            PipelineInstanceId = pipelineId,
                            SourceType = Enum.TryParse<SourceType>(evt.EventType, ignoreCase: true, out var st) ? st : SourceType.Event,
                            SourceKey = evt.Key,
                            SourceMetadata = JsonSerializer.Serialize(evt.Metadata),
                            DedupKey = dedupKey,
                            DetectedAt = evt.DetectedAt,
                            Status = JobStatus.Queued
                        };
                        db.WorkItems.Add(workItem);
                        _logger.LogInformation("Created work item for event: {Key}", evt.Key);
                    }

                    // Update heartbeat
                    var activation = await db.PipelineActivations.FindAsync(new object[] { activationId }, ct);
                    if (activation != null)
                    {
                        activation.LastHeartbeatAt = DateTimeOffset.UtcNow;
                        activation.LastPolledAt = DateTimeOffset.UtcNow;
                        if (activation.Status == ActivationStatus.Starting)
                            activation.Status = ActivationStatus.Running;
                    }

                    await db.SaveChangesAsync(ct);
                }

                var effectiveInterval = _backPressureManager.GetThrottledIntervalMs(intervalMs, bpState);
                await Task.Delay(effectiveInterval, ct);
            }
            catch (OperationCanceledException) { break; }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error in monitoring loop for activation {Id}", activationId);
                await Task.Delay(5000, ct); // backoff on error
            }
        }

        // Cleanup
        try
        {
            using var scope = _scopeFactory.CreateScope();
            var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();
            var activation = await db.PipelineActivations.FindAsync(new object[] { activationId });
            if (activation != null)
            {
                activation.Status = ActivationStatus.Stopped;
                activation.StoppedAt = DateTimeOffset.UtcNow;
                await db.SaveChangesAsync();
            }
        }
        catch { }
    }

    private BaseMonitor CreateMonitor(PipelineInstance pipeline)
    {
        var config = !string.IsNullOrEmpty(pipeline.MonitoringConfig)
            ? JsonDocument.Parse(pipeline.MonitoringConfig).RootElement
            : default;

        return pipeline.MonitoringType switch
        {
            MonitoringType.FileMonitor => new FileMonitor(
                watchPath: config.TryGetProperty("watch_path", out var wp) ? wp.GetString()! : "/data/input",
                filePattern: config.TryGetProperty("file_pattern", out var fp) ? fp.GetString()! : "*"),
            MonitoringType.ApiPoll => new ApiPollMonitor(
                _httpClientFactory.CreateClient(),
                url: config.TryGetProperty("url", out var u) ? u.GetString()! : "http://localhost",
                headers: config.TryGetProperty("headers", out var h)
                    ? JsonSerializer.Deserialize<Dictionary<string, string>>(h.GetRawText())
                    : null),
            MonitoringType.EventStream => new KafkaMonitor(
                bootstrapServers: config.TryGetProperty("bootstrap_servers", out var bs) ? bs.GetString()! : "localhost:9092",
                topic: config.TryGetProperty("topic", out var t) ? t.GetString()! : "hermes-events",
                groupId: config.TryGetProperty("group_id", out var g) ? g.GetString()! : "hermes-engine"),
            _ => throw new NotSupportedException($"Monitoring type not supported: {pipeline.MonitoringType}")
        };
    }

    private static int ParseIntervalMs(string? configJson)
    {
        if (string.IsNullOrEmpty(configJson)) return 5000;
        try
        {
            var doc = JsonDocument.Parse(configJson);
            if (doc.RootElement.TryGetProperty("interval", out var interval))
            {
                var val = interval.GetString();
                if (val != null)
                {
                    if (val.EndsWith("ms")) return int.Parse(val[..^2]);
                    if (val.EndsWith("s")) return int.Parse(val[..^1]) * 1000;
                    if (val.EndsWith("m")) return int.Parse(val[..^1]) * 60_000;
                    if (val.EndsWith("h")) return int.Parse(val[..^1]) * 3_600_000;
                    if (int.TryParse(val, out var ms)) return ms;
                }
            }
            if (doc.RootElement.TryGetProperty("interval_ms", out var ims))
                return ims.GetInt32();
        }
        catch { }
        return 5000;
    }
}
