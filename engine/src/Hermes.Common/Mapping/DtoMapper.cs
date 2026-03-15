namespace Hermes.Common.Mapping;

/// <summary>
/// Static mapper methods for converting between domain entities and DTOs.
/// Used by both the REST API layer and gRPC service layer so mapping logic
/// is consistent across transport protocols.
///
/// Note: This references DTOs only. Entity mapping is done via extension
/// methods in the respective API/Engine projects that reference both
/// Hermes.Common and Hermes.Engine.Domain.
/// </summary>
public static class DtoMapper
{
    /// <summary>Parse a duration string (e.g. "5s", "30m", "1h") to milliseconds.</summary>
    public static int ParseIntervalMs(string? interval, int defaultMs = 5000)
    {
        if (string.IsNullOrWhiteSpace(interval)) return defaultMs;

        var val = interval.AsSpan().TrimEnd();
        if (val.EndsWith("ms") && int.TryParse(val[..^2], out var ms)) return ms;
        if (val.EndsWith("s") && int.TryParse(val[..^1], out var s)) return s * 1000;
        if (val.EndsWith("m") && int.TryParse(val[..^1], out var m)) return m * 60_000;
        if (val.EndsWith("h") && int.TryParse(val[..^1], out var h)) return h * 3_600_000;
        return int.TryParse(interval, out var raw) ? raw : defaultMs;
    }

    /// <summary>Format milliseconds as a human-readable duration string.</summary>
    public static string FormatDuration(long? durationMs)
    {
        if (durationMs == null) return "-";
        var ts = TimeSpan.FromMilliseconds(durationMs.Value);
        if (ts.TotalHours >= 1) return $"{ts.TotalHours:F1}h";
        if (ts.TotalMinutes >= 1) return $"{ts.TotalMinutes:F1}m";
        if (ts.TotalSeconds >= 1) return $"{ts.TotalSeconds:F1}s";
        return $"{durationMs}ms";
    }

    /// <summary>Compute a simple success rate percentage.</summary>
    public static double ComputeSuccessRate(long completed, long failed)
    {
        var total = completed + failed;
        return total == 0 ? 100.0 : Math.Round((double)completed / total * 100, 2);
    }
}
