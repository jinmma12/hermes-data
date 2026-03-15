using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;

namespace Hermes.Engine.Services.Nifi;

/// <summary>
/// HTTP client for the Apache NiFi REST API.
/// Handles authentication, token refresh, and common operations.
/// Reference: https://nifi.apache.org/docs/nifi-docs/rest-api/
/// </summary>
public interface INiFiClient
{
    Task<bool> IsAvailableAsync(CancellationToken ct = default);
    Task<JsonElement> GetProcessGroupAsync(string processGroupId, CancellationToken ct = default);
    Task<JsonElement> GetProcessGroupStatusAsync(string processGroupId, CancellationToken ct = default);
    Task StartProcessGroupAsync(string processGroupId, CancellationToken ct = default);
    Task StopProcessGroupAsync(string processGroupId, CancellationToken ct = default);
    Task<JsonElement> ListProcessGroupsAsync(string parentGroupId = "root", CancellationToken ct = default);
    Task<JsonElement> GetProvenanceEventsAsync(string? processorId = null, int maxResults = 100, CancellationToken ct = default);
    Task SetParameterContextAsync(string paramContextId, Dictionary<string, string> parameters, CancellationToken ct = default);
}

public class NiFiClientConfig
{
    public string BaseUrl { get; set; } = "http://localhost:8080/nifi-api";
    public string? Username { get; set; }
    public string? Password { get; set; }
    public int TimeoutSeconds { get; set; } = 30;
    public bool Enabled { get; set; }
}

public class NiFiClient : INiFiClient
{
    private readonly HttpClient _http;
    private readonly NiFiClientConfig _config;
    private readonly ILogger<NiFiClient> _logger;
    private string? _accessToken;
    private DateTimeOffset _tokenExpiry;

    public NiFiClient(HttpClient http, NiFiClientConfig config, ILogger<NiFiClient> logger)
    {
        _http = http;
        _config = config;
        _logger = logger;
        _http.BaseAddress = new Uri(config.BaseUrl.TrimEnd('/') + "/");
        _http.Timeout = TimeSpan.FromSeconds(config.TimeoutSeconds);
    }

    public async Task<bool> IsAvailableAsync(CancellationToken ct = default)
    {
        try
        {
            await EnsureAuthenticatedAsync(ct);
            var response = await _http.GetAsync("system-diagnostics", ct);
            return response.IsSuccessStatusCode;
        }
        catch (Exception ex)
        {
            _logger.LogWarning(ex, "NiFi not available at {Url}", _config.BaseUrl);
            return false;
        }
    }

    public async Task<JsonElement> GetProcessGroupAsync(string processGroupId, CancellationToken ct = default)
    {
        await EnsureAuthenticatedAsync(ct);
        var response = await _http.GetAsync($"process-groups/{processGroupId}", ct);
        response.EnsureSuccessStatusCode();
        var json = await response.Content.ReadAsStringAsync(ct);
        return JsonDocument.Parse(json).RootElement;
    }

    public async Task<JsonElement> GetProcessGroupStatusAsync(string processGroupId, CancellationToken ct = default)
    {
        await EnsureAuthenticatedAsync(ct);
        var response = await _http.GetAsync($"flow/process-groups/{processGroupId}/status", ct);
        response.EnsureSuccessStatusCode();
        var json = await response.Content.ReadAsStringAsync(ct);
        return JsonDocument.Parse(json).RootElement;
    }

    public async Task StartProcessGroupAsync(string processGroupId, CancellationToken ct = default)
    {
        await EnsureAuthenticatedAsync(ct);
        var body = JsonSerializer.Serialize(new
        {
            id = processGroupId,
            state = "RUNNING",
            disconnectedNodeAcknowledged = false
        });
        var response = await _http.PutAsync($"flow/process-groups/{processGroupId}",
            new StringContent(body, Encoding.UTF8, "application/json"), ct);
        response.EnsureSuccessStatusCode();
        _logger.LogInformation("NiFi process group {Id} started", processGroupId);
    }

    public async Task StopProcessGroupAsync(string processGroupId, CancellationToken ct = default)
    {
        await EnsureAuthenticatedAsync(ct);
        var body = JsonSerializer.Serialize(new
        {
            id = processGroupId,
            state = "STOPPED",
            disconnectedNodeAcknowledged = false
        });
        var response = await _http.PutAsync($"flow/process-groups/{processGroupId}",
            new StringContent(body, Encoding.UTF8, "application/json"), ct);
        response.EnsureSuccessStatusCode();
        _logger.LogInformation("NiFi process group {Id} stopped", processGroupId);
    }

    public async Task<JsonElement> ListProcessGroupsAsync(string parentGroupId = "root", CancellationToken ct = default)
    {
        await EnsureAuthenticatedAsync(ct);
        var response = await _http.GetAsync($"process-groups/{parentGroupId}/process-groups", ct);
        response.EnsureSuccessStatusCode();
        var json = await response.Content.ReadAsStringAsync(ct);
        return JsonDocument.Parse(json).RootElement;
    }

    public async Task<JsonElement> GetProvenanceEventsAsync(string? processorId = null, int maxResults = 100, CancellationToken ct = default)
    {
        await EnsureAuthenticatedAsync(ct);

        // Submit provenance query
        var query = new
        {
            provenance = new
            {
                request = new
                {
                    maxResults,
                    searchTerms = processorId != null
                        ? new Dictionary<string, object> { ["ProcessorID"] = new { value = processorId } }
                        : new Dictionary<string, object>()
                }
            }
        };
        var submitResponse = await _http.PostAsync("provenance",
            new StringContent(JsonSerializer.Serialize(query), Encoding.UTF8, "application/json"), ct);
        submitResponse.EnsureSuccessStatusCode();
        var submitJson = await submitResponse.Content.ReadAsStringAsync(ct);
        var submitResult = JsonDocument.Parse(submitJson).RootElement;
        var queryId = submitResult.GetProperty("provenance").GetProperty("id").GetString()!;

        // Poll for results
        for (int i = 0; i < 10; i++)
        {
            await Task.Delay(500, ct);
            var pollResponse = await _http.GetAsync($"provenance/{queryId}", ct);
            pollResponse.EnsureSuccessStatusCode();
            var pollJson = await pollResponse.Content.ReadAsStringAsync(ct);
            var pollResult = JsonDocument.Parse(pollJson).RootElement;

            if (pollResult.GetProperty("provenance").GetProperty("finished").GetBoolean())
                return pollResult;
        }

        return submitResult; // Return whatever we have
    }

    public async Task SetParameterContextAsync(string paramContextId, Dictionary<string, string> parameters, CancellationToken ct = default)
    {
        await EnsureAuthenticatedAsync(ct);

        // Get current parameter context (for revision)
        var getResponse = await _http.GetAsync($"parameter-contexts/{paramContextId}", ct);
        getResponse.EnsureSuccessStatusCode();
        var currentJson = await getResponse.Content.ReadAsStringAsync(ct);
        var current = JsonDocument.Parse(currentJson).RootElement;
        var revision = current.GetProperty("revision");

        // Build update request
        var updateParams = parameters.Select(kvp => new
        {
            parameter = new { name = kvp.Key, value = kvp.Value, sensitive = false }
        }).ToArray();

        var updateBody = JsonSerializer.Serialize(new
        {
            revision = new
            {
                version = revision.GetProperty("version").GetInt64(),
                clientId = revision.TryGetProperty("clientId", out var cid) ? cid.GetString() : null
            },
            id = paramContextId,
            component = new
            {
                id = paramContextId,
                parameters = updateParams
            }
        });

        var updateResponse = await _http.PutAsync($"parameter-contexts/{paramContextId}",
            new StringContent(updateBody, Encoding.UTF8, "application/json"), ct);
        updateResponse.EnsureSuccessStatusCode();
        _logger.LogInformation("NiFi parameter context {Id} updated with {Count} parameters",
            paramContextId, parameters.Count);
    }

    private async Task EnsureAuthenticatedAsync(CancellationToken ct)
    {
        if (string.IsNullOrEmpty(_config.Username)) return; // No auth required

        if (_accessToken != null && DateTimeOffset.UtcNow < _tokenExpiry)
            return; // Token still valid

        var body = $"username={Uri.EscapeDataString(_config.Username)}&password={Uri.EscapeDataString(_config.Password ?? "")}";
        var response = await _http.PostAsync("access/token",
            new StringContent(body, Encoding.UTF8, "application/x-www-form-urlencoded"), ct);
        response.EnsureSuccessStatusCode();

        _accessToken = await response.Content.ReadAsStringAsync(ct);
        _tokenExpiry = DateTimeOffset.UtcNow.AddMinutes(10); // NiFi tokens expire in ~12h, refresh at 10m
        _http.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", _accessToken);
        _logger.LogDebug("NiFi authentication token acquired");
    }
}
