using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace Hermes.Engine.Services.Nifi;

/// <summary>
/// Bridge between NiFi Process Groups and Hermes Pipelines.
/// Synchronizes NiFi flows with Hermes pipeline definitions.
/// </summary>
public interface INiFiBridge
{
    /// <summary>Import a NiFi process group as a Hermes pipeline.</summary>
    Task<NiFiSyncResult> SyncProcessGroupAsync(string processGroupId, CancellationToken ct = default);

    /// <summary>Push Hermes recipe changes to NiFi parameter context.</summary>
    Task PushRecipeToNiFiAsync(string paramContextId, Dictionary<string, string> recipeParams, CancellationToken ct = default);

    /// <summary>Map NiFi provenance events to Hermes execution event logs.</summary>
    Task<List<NiFiProvenanceMapping>> MapProvenanceEventsAsync(string processGroupId, DateTimeOffset since, CancellationToken ct = default);
}

public record NiFiSyncResult(
    bool Success,
    string? PipelineName,
    int ProcessorCount,
    List<string> ProcessorNames,
    string? ErrorMessage);

public record NiFiProvenanceMapping(
    string NiFiEventId,
    string EventType,
    string ProcessorName,
    string? FlowFileUuid,
    long DurationMs,
    DateTimeOffset Timestamp);

public class NiFiBridge : INiFiBridge
{
    private readonly INiFiClient _client;
    private readonly ILogger<NiFiBridge> _logger;

    public NiFiBridge(INiFiClient client, ILogger<NiFiBridge> logger)
    {
        _client = client;
        _logger = logger;
    }

    public async Task<NiFiSyncResult> SyncProcessGroupAsync(string processGroupId, CancellationToken ct = default)
    {
        try
        {
            var pg = await _client.GetProcessGroupAsync(processGroupId, ct);
            var component = pg.GetProperty("component");
            var name = component.GetProperty("name").GetString() ?? "Unknown";

            var status = await _client.GetProcessGroupStatusAsync(processGroupId, ct);
            var processorCount = 0;
            var processorNames = new List<string>();

            if (status.TryGetProperty("processGroupStatus", out var pgs) &&
                pgs.TryGetProperty("aggregateSnapshot", out var snapshot))
            {
                processorCount = snapshot.TryGetProperty("activeThreadCount", out var tc) ? tc.GetInt32() : 0;
            }

            _logger.LogInformation("Synced NiFi process group '{Name}' ({Id}): {Count} processors",
                name, processGroupId, processorCount);

            return new NiFiSyncResult(true, name, processorCount, processorNames, null);
        }
        catch (Exception ex)
        {
            _logger.LogError(ex, "Failed to sync NiFi process group {Id}", processGroupId);
            return new NiFiSyncResult(false, null, 0, new(), ex.Message);
        }
    }

    public async Task PushRecipeToNiFiAsync(string paramContextId, Dictionary<string, string> recipeParams, CancellationToken ct = default)
    {
        await _client.SetParameterContextAsync(paramContextId, recipeParams, ct);
        _logger.LogInformation("Pushed {Count} recipe parameters to NiFi context {Id}",
            recipeParams.Count, paramContextId);
    }

    public async Task<List<NiFiProvenanceMapping>> MapProvenanceEventsAsync(
        string processGroupId, DateTimeOffset since, CancellationToken ct = default)
    {
        var provenance = await _client.GetProvenanceEventsAsync(processGroupId, ct: ct);
        var mappings = new List<NiFiProvenanceMapping>();

        if (provenance.TryGetProperty("provenance", out var prov) &&
            prov.TryGetProperty("results", out var results) &&
            results.TryGetProperty("provenanceEvents", out var events))
        {
            foreach (var evt in events.EnumerateArray())
            {
                var ts = evt.TryGetProperty("eventTime", out var et)
                    ? DateTimeOffset.Parse(et.GetString()!) : DateTimeOffset.UtcNow;
                if (ts < since) continue;

                mappings.Add(new NiFiProvenanceMapping(
                    NiFiEventId: evt.GetProperty("eventId").ToString(),
                    EventType: evt.TryGetProperty("eventType", out var evtType) ? evtType.GetString()! : "UNKNOWN",
                    ProcessorName: evt.TryGetProperty("componentName", out var cn) ? cn.GetString()! : "",
                    FlowFileUuid: evt.TryGetProperty("flowFileUuid", out var ff) ? ff.GetString() : null,
                    DurationMs: evt.TryGetProperty("eventDuration", out var dur) ? dur.GetInt64() : 0,
                    Timestamp: ts));
            }
        }

        _logger.LogDebug("Mapped {Count} NiFi provenance events since {Since}", mappings.Count, since);
        return mappings;
    }
}
