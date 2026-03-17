using System.Net;
using System.Net.Http.Headers;
using System.Text;
using System.Text.Json;
using Microsoft.Extensions.Logging;
using Polly;

namespace Hermes.Engine.Services.Exporters;

/// <summary>
/// Exports data by sending HTTP requests to webhook endpoints.
/// Supports POST/PUT/PATCH, authentication (bearer, basic, api_key),
/// retry with exponential backoff, and batch mode.
/// </summary>
public class WebhookSenderExporter : BaseExporter
{
    private readonly WebhookSenderConfig _config;
    private readonly HttpClient _httpClient;
    private readonly ILogger? _logger;

    public WebhookSenderExporter(WebhookSenderConfig config, HttpClient httpClient, ILogger? logger = null)
    {
        _config = config;
        _httpClient = httpClient;
        _logger = logger;
    }

    public override async Task<ExportResult> ExportAsync(ExportContext context, CancellationToken ct = default)
    {
        if (string.IsNullOrEmpty(_config.Url))
            return new ExportResult(false, 0, ErrorMessage: "Webhook URL not configured");

        var sw = System.Diagnostics.Stopwatch.StartNew();
        var records = ParseRecords(context.DataJson);
        int successCount = 0;
        int failedCount = 0;
        string? lastError = null;

        // Build retry policy
        var retryPolicy = Policy
            .Handle<HttpRequestException>()
            .Or<TaskCanceledException>()
            .WaitAndRetryAsync(
                _config.MaxRetries,
                attempt => TimeSpan.FromSeconds(Math.Pow(2, attempt)),
                (ex, delay, attempt, _) =>
                {
                    _logger?.LogWarning("Webhook retry {Attempt}/{Max} after {Delay}s: {Error}",
                        attempt, _config.MaxRetries, delay.TotalSeconds, ex.Message);
                }
            );

        try
        {
            if (_config.BatchMode)
            {
                // Send all records in one request
                var body = JsonSerializer.Serialize(records.Select(r => JsonSerializer.Deserialize<object>(r.GetRawText())));
                var result = await retryPolicy.ExecuteAsync(async (cancellation) =>
                    await SendRequestAsync(body, cancellation), ct);

                if (result.success)
                {
                    successCount = records.Count;
                }
                else
                {
                    failedCount = records.Count;
                    lastError = result.error;
                }
            }
            else
            {
                // Send each record individually
                foreach (var record in records)
                {
                    ct.ThrowIfCancellationRequested();
                    var result = await retryPolicy.ExecuteAsync(async (cancellation) =>
                        await SendRequestAsync(record.GetRawText(), cancellation), ct);

                    if (result.success) successCount++;
                    else { failedCount++; lastError = result.error; }
                }
            }
        }
        catch (Exception ex)
        {
            lastError = ex.Message;
            _logger?.LogError(ex, "Webhook export failed: {Url}", _config.Url);
        }

        sw.Stop();
        _logger?.LogInformation("Webhook: Sent {Success}/{Total} to {Url}", successCount, records.Count, _config.Url);

        return new ExportResult(
            Success: failedCount == 0,
            RecordsExported: successCount,
            DestinationInfo: _config.Url,
            ErrorMessage: lastError,
            DurationMs: sw.ElapsedMilliseconds,
            Summary: new Dictionary<string, object>
            {
                ["url"] = _config.Url,
                ["method"] = _config.Method,
                ["records_sent"] = successCount,
                ["records_failed"] = failedCount,
                ["batch_mode"] = _config.BatchMode,
            }
        );
    }

    private async Task<(bool success, string? error)> SendRequestAsync(string body, CancellationToken ct)
    {
        var request = new HttpRequestMessage(new HttpMethod(_config.Method), _config.Url)
        {
            Content = new StringContent(body, Encoding.UTF8, _config.ContentType),
        };

        // Auth headers
        switch (_config.AuthType)
        {
            case "bearer" when !string.IsNullOrEmpty(_config.AuthToken):
                request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", _config.AuthToken);
                break;
            case "basic" when !string.IsNullOrEmpty(_config.AuthToken):
                request.Headers.Authorization = new AuthenticationHeaderValue("Basic", _config.AuthToken);
                break;
            case "api_key" when !string.IsNullOrEmpty(_config.AuthToken):
                request.Headers.Add(_config.ApiKeyHeader ?? "X-API-Key", _config.AuthToken);
                break;
        }

        // Custom headers
        foreach (var (key, value) in _config.Headers)
            request.Headers.TryAddWithoutValidation(key, value);

        using var cts = CancellationTokenSource.CreateLinkedTokenSource(ct);
        cts.CancelAfter(TimeSpan.FromSeconds(_config.TimeoutSeconds));
        var response = await _httpClient.SendAsync(request, cts.Token);

        if (response.IsSuccessStatusCode)
            return (true, null);

        // Rate limit handling
        if (response.StatusCode == HttpStatusCode.TooManyRequests)
        {
            if (response.Headers.RetryAfter?.Delta is { } retryAfter)
                await Task.Delay(retryAfter, ct);
            throw new HttpRequestException($"Rate limited (429)");
        }

        // Server errors are retryable
        if ((int)response.StatusCode >= 500)
            throw new HttpRequestException($"Server error: {(int)response.StatusCode}");

        // Client errors are not retryable
        return (false, $"HTTP {(int)response.StatusCode}: {response.ReasonPhrase}");
    }

    private static List<JsonElement> ParseRecords(string dataJson)
    {
        var doc = JsonDocument.Parse(dataJson);
        if (doc.RootElement.ValueKind == JsonValueKind.Array)
            return doc.RootElement.EnumerateArray().ToList();
        if (doc.RootElement.TryGetProperty("records", out var records) && records.ValueKind == JsonValueKind.Array)
            return records.EnumerateArray().ToList();
        return new List<JsonElement> { doc.RootElement };
    }
}
