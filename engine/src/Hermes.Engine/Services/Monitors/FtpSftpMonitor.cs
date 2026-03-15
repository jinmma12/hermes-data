using System.Text.Json;
using System.Text.RegularExpressions;
using FluentFTP;
using Renci.SshNet;
using Renci.SshNet.Sftp;
using Microsoft.Extensions.Logging;
using Hermes.Engine.Domain;

namespace Hermes.Engine.Services.Monitors;

/// <summary>
/// FTP/SFTP Collector monitor with full directory traversal.
/// Supports recursive scanning, regex filtering, latest-first sorting.
///
/// Config (JSON):
/// {
///   "protocol": "sftp",           // "ftp" or "sftp"
///   "host": "ftp.example.com",
///   "port": 22,
///   "username": "user",
///   "password": "pass",
///   "base_path": "/incoming/data",
///   "recursive": true,
///   "path_filter_regex": "^/incoming/data/(2026|2025)/",
///   "file_filter_regex": ".*\\.csv$",
///   "sort_by": "modified_desc",   // "modified_desc", "modified_asc", "name_asc", "name_desc", "size_desc"
///   "max_files_per_poll": 100,
///   "min_age_seconds": 10         // Skip files still being written (< 10s old)
/// }
/// </summary>
public class FtpSftpMonitor : BaseMonitor
{
    private readonly FtpSftpConfig _config;
    private readonly HashSet<string> _seenFiles = new();
    private readonly ILogger? _logger;

    public FtpSftpMonitor(FtpSftpConfig config, ILogger? logger = null)
    {
        _config = config;
        _logger = logger;
    }

    public override async Task<List<MonitorEvent>> PollAsync(CancellationToken ct = default)
    {
        return _config.Protocol.Equals("sftp", StringComparison.OrdinalIgnoreCase)
            ? await PollSftpAsync(ct)
            : await PollFtpAsync(ct);
    }

    // ── SFTP (SSH.NET) ──

    private Task<List<MonitorEvent>> PollSftpAsync(CancellationToken ct)
    {
        var events = new List<MonitorEvent>();
        try
        {
            using var client = new SftpClient(_config.Host, _config.Port, _config.Username, _config.Password);
            client.Connect();

            var allFiles = new List<(ISftpFile File, string FullPath)>();
            ScanSftpDirectory(client, _config.BasePath, allFiles, _config.Recursive);

            // Apply filters and sorting
            var filtered = ApplyFilters(allFiles.Select(f => new RemoteFileInfo
            {
                FullPath = f.FullPath,
                FileName = f.File.Name,
                Size = f.File.Length,
                LastModified = f.File.LastWriteTimeUtc,
                IsDirectory = f.File.IsDirectory,
            }));

            foreach (var file in filtered)
            {
                if (_seenFiles.Contains(file.FullPath)) continue;
                _seenFiles.Add(file.FullPath);

                events.Add(CreateEvent(file));
            }

            client.Disconnect();
        }
        catch (Exception ex)
        {
            _logger?.LogWarning(ex, "SFTP poll failed: {Host}:{Port}{Path}", _config.Host, _config.Port, _config.BasePath);
        }

        if (events.Count > 0)
            _logger?.LogInformation("FTP/SFTP: {Count} new files detected at {Host}{Path}", events.Count, _config.Host, _config.BasePath);

        return Task.FromResult(events);
    }

    private void ScanSftpDirectory(SftpClient client, string path, List<(ISftpFile, string)> results, bool recursive)
    {
        IEnumerable<ISftpFile> listing;
        try { listing = client.ListDirectory(path); }
        catch { return; }

        foreach (var item in listing)
        {
            if (item.Name == "." || item.Name == "..") continue;
            var fullPath = $"{path.TrimEnd('/')}/{item.Name}";

            if (item.IsDirectory && recursive)
            {
                ScanSftpDirectory(client, fullPath, results, true);
            }
            else if (!item.IsDirectory)
            {
                results.Add((item, fullPath));
            }
        }
    }

    // ── FTP (FluentFTP) ──

    private async Task<List<MonitorEvent>> PollFtpAsync(CancellationToken ct)
    {
        var events = new List<MonitorEvent>();
        try
        {
            using var client = new AsyncFtpClient(_config.Host, _config.Username, _config.Password, _config.Port);
            await client.Connect(ct);

            var option = _config.Recursive ? FtpListOption.Recursive : FtpListOption.Auto;
            var listing = await client.GetListing(_config.BasePath, option, ct);

            var files = listing
                .Where(f => f.Type == FtpObjectType.File)
                .Select(f => new RemoteFileInfo
                {
                    FullPath = f.FullName,
                    FileName = f.Name,
                    Size = f.Size,
                    LastModified = f.Modified.ToUniversalTime(),
                    IsDirectory = false,
                });

            var filtered = ApplyFilters(files);

            foreach (var file in filtered)
            {
                if (_seenFiles.Contains(file.FullPath)) continue;
                _seenFiles.Add(file.FullPath);
                events.Add(CreateEvent(file));
            }

            await client.Disconnect(ct);
        }
        catch (Exception ex)
        {
            _logger?.LogWarning(ex, "FTP poll failed: {Host}:{Port}{Path}", _config.Host, _config.Port, _config.BasePath);
        }

        if (events.Count > 0)
            _logger?.LogInformation("FTP: {Count} new files detected at {Host}{Path}", events.Count, _config.Host, _config.BasePath);

        return events;
    }

    // ── Filter + Sort ──

    private IEnumerable<RemoteFileInfo> ApplyFilters(IEnumerable<RemoteFileInfo> files)
    {
        var result = files.Where(f => !f.IsDirectory);

        // Path regex filter
        if (!string.IsNullOrEmpty(_config.PathFilterRegex))
        {
            var pathRegex = new Regex(_config.PathFilterRegex, RegexOptions.Compiled | RegexOptions.IgnoreCase);
            result = result.Where(f => pathRegex.IsMatch(f.FullPath));
        }

        // File name regex filter
        if (!string.IsNullOrEmpty(_config.FileFilterRegex))
        {
            var fileRegex = new Regex(_config.FileFilterRegex, RegexOptions.Compiled | RegexOptions.IgnoreCase);
            result = result.Where(f => fileRegex.IsMatch(f.FileName));
        }

        // Min age filter (skip files still being written)
        if (_config.MinAgeSeconds > 0)
        {
            var cutoff = DateTime.UtcNow.AddSeconds(-_config.MinAgeSeconds);
            result = result.Where(f => f.LastModified < cutoff);
        }

        // Sort
        result = _config.SortBy?.ToLowerInvariant() switch
        {
            "modified_desc" => result.OrderByDescending(f => f.LastModified),
            "modified_asc" => result.OrderBy(f => f.LastModified),
            "name_asc" => result.OrderBy(f => f.FileName),
            "name_desc" => result.OrderByDescending(f => f.FileName),
            "size_desc" => result.OrderByDescending(f => f.Size),
            _ => result.OrderByDescending(f => f.LastModified), // Default: latest first
        };

        // Limit
        if (_config.MaxFilesPerPoll > 0)
            result = result.Take(_config.MaxFilesPerPoll);

        return result;
    }

    private static MonitorEvent CreateEvent(RemoteFileInfo file) => new(
        EventType: "FILE",
        Key: file.FullPath,
        Metadata: new Dictionary<string, object>
        {
            ["path"] = file.FullPath,
            ["filename"] = file.FileName,
            ["size"] = file.Size,
            ["last_modified"] = file.LastModified.ToString("O"),
            ["source"] = "ftp/sftp"
        },
        DetectedAt: DateTimeOffset.UtcNow
    );

    private class RemoteFileInfo
    {
        public string FullPath { get; set; } = "";
        public string FileName { get; set; } = "";
        public long Size { get; set; }
        public DateTime LastModified { get; set; }
        public bool IsDirectory { get; set; }
    }
}

public class FtpSftpConfig
{
    public string Protocol { get; set; } = "sftp";
    public string Host { get; set; } = "";
    public int Port { get; set; } = 22;
    public string Username { get; set; } = "";
    public string Password { get; set; } = "";
    public string BasePath { get; set; } = "/";
    public bool Recursive { get; set; } = true;
    public string? PathFilterRegex { get; set; }
    public string? FileFilterRegex { get; set; }
    public string? SortBy { get; set; } = "modified_desc";
    public int MaxFilesPerPoll { get; set; } = 100;
    public int MinAgeSeconds { get; set; } = 10;

    public static FtpSftpConfig FromJson(System.Text.Json.JsonElement config)
    {
        return new FtpSftpConfig
        {
            Protocol = config.TryGetProperty("protocol", out var p) ? p.GetString() ?? "sftp" : "sftp",
            Host = config.TryGetProperty("host", out var h) ? h.GetString() ?? "" : "",
            Port = config.TryGetProperty("port", out var pt) ? pt.GetInt32() : 22,
            Username = config.TryGetProperty("username", out var u) ? u.GetString() ?? "" : "",
            Password = config.TryGetProperty("password", out var pw) ? pw.GetString() ?? "" : "",
            BasePath = config.TryGetProperty("base_path", out var bp) ? bp.GetString() ?? "/" : "/",
            Recursive = config.TryGetProperty("recursive", out var r) && r.GetBoolean(),
            PathFilterRegex = config.TryGetProperty("path_filter_regex", out var pfr) ? pfr.GetString() : null,
            FileFilterRegex = config.TryGetProperty("file_filter_regex", out var ffr) ? ffr.GetString() : null,
            SortBy = config.TryGetProperty("sort_by", out var sb) ? sb.GetString() : "modified_desc",
            MaxFilesPerPoll = config.TryGetProperty("max_files_per_poll", out var mf) ? mf.GetInt32() : 100,
            MinAgeSeconds = config.TryGetProperty("min_age_seconds", out var ma) ? ma.GetInt32() : 10,
        };
    }
}
