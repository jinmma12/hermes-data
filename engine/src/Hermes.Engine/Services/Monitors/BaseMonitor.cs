using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Hermes.Engine.Domain;

namespace Hermes.Engine.Services.Monitors;

public abstract class BaseMonitor
{
    public abstract Task<List<MonitorEvent>> PollAsync(CancellationToken ct = default);
}

public class FileMonitor : BaseMonitor
{
    private readonly string _watchPath;
    private readonly string _filePattern;
    private readonly bool _recursive;
    private readonly System.Text.RegularExpressions.Regex? _pathFilterRegex;
    private readonly System.Text.RegularExpressions.Regex? _fileFilterRegex;
    private readonly string _sortBy;
    private readonly int _maxFiles;
    private readonly HashSet<string> _seenFiles = new();

    public FileMonitor(string watchPath, string filePattern = "*", bool recursive = false,
        string? pathFilterRegex = null, string? fileFilterRegex = null,
        string sortBy = "modified_desc", int maxFiles = 0)
    {
        _watchPath = watchPath;
        _filePattern = filePattern;
        _recursive = recursive;
        _pathFilterRegex = pathFilterRegex != null
            ? new System.Text.RegularExpressions.Regex(pathFilterRegex, System.Text.RegularExpressions.RegexOptions.Compiled | System.Text.RegularExpressions.RegexOptions.IgnoreCase)
            : null;
        _fileFilterRegex = fileFilterRegex != null
            ? new System.Text.RegularExpressions.Regex(fileFilterRegex, System.Text.RegularExpressions.RegexOptions.Compiled | System.Text.RegularExpressions.RegexOptions.IgnoreCase)
            : null;
        _sortBy = sortBy;
        _maxFiles = maxFiles;
    }

    public override Task<List<MonitorEvent>> PollAsync(CancellationToken ct = default)
    {
        var events = new List<MonitorEvent>();
        if (!Directory.Exists(_watchPath)) return Task.FromResult(events);

        var searchOption = _recursive ? SearchOption.AllDirectories : SearchOption.TopDirectoryOnly;
        var files = Directory.EnumerateFiles(_watchPath, _filePattern, searchOption)
            .Where(f => !_seenFiles.Contains(f))
            .Select(f => new FileInfo(f))
            .AsEnumerable();

        // Apply regex filters
        if (_pathFilterRegex != null)
            files = files.Where(f => _pathFilterRegex.IsMatch(f.FullName));
        if (_fileFilterRegex != null)
            files = files.Where(f => _fileFilterRegex.IsMatch(f.Name));

        // Sort
        files = _sortBy switch
        {
            "modified_asc" => files.OrderBy(f => f.LastWriteTimeUtc),
            "name_asc" => files.OrderBy(f => f.Name),
            "name_desc" => files.OrderByDescending(f => f.Name),
            "size_desc" => files.OrderByDescending(f => f.Length),
            _ => files.OrderByDescending(f => f.LastWriteTimeUtc), // modified_desc (default)
        };

        // Limit
        if (_maxFiles > 0)
            files = files.Take(_maxFiles);

        foreach (var info in files)
        {
            _seenFiles.Add(info.FullName);
            events.Add(new MonitorEvent(
                EventType: "FILE",
                Key: info.FullName,
                Metadata: new Dictionary<string, object>
                {
                    ["path"] = info.FullName,
                    ["filename"] = info.Name,
                    ["size"] = info.Length,
                    ["last_modified"] = info.LastWriteTimeUtc.ToString("O")
                },
                DetectedAt: DateTimeOffset.UtcNow
            ));
        }
        return Task.FromResult(events);
    }
}

public class ApiPollMonitor : BaseMonitor
{
    private readonly HttpClient _httpClient;
    private readonly string _url;
    private readonly Dictionary<string, string> _headers;
    private string? _lastContentHash;

    public ApiPollMonitor(HttpClient httpClient, string url, Dictionary<string, string>? headers = null)
    {
        _httpClient = httpClient;
        _url = url;
        _headers = headers ?? new();
    }

    public override async Task<List<MonitorEvent>> PollAsync(CancellationToken ct = default)
    {
        var events = new List<MonitorEvent>();
        var request = new HttpRequestMessage(HttpMethod.Get, _url);
        foreach (var (key, value) in _headers)
            request.Headers.TryAddWithoutValidation(key, value);

        var response = await _httpClient.SendAsync(request, ct);
        var content = await response.Content.ReadAsStringAsync(ct);
        var hash = Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(content))).ToLowerInvariant();

        if (hash != _lastContentHash)
        {
            _lastContentHash = hash;
            events.Add(new MonitorEvent(
                EventType: "API_RESPONSE",
                Key: _url,
                Metadata: new Dictionary<string, object>
                {
                    ["url"] = _url,
                    ["status_code"] = (int)response.StatusCode,
                    ["content_hash"] = hash,
                    ["content_length"] = content.Length
                },
                DetectedAt: DateTimeOffset.UtcNow
            ));
        }
        return events;
    }
}
