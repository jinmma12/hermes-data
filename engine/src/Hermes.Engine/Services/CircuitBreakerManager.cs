using System.Collections.Concurrent;
using Polly.CircuitBreaker;
using Microsoft.Extensions.Logging;

namespace Hermes.Engine.Services;

public interface ICircuitBreakerManager
{
    CircuitBreakerState GetState(string resourceKey);
    void RecordSuccess(string resourceKey);
    void RecordFailure(string resourceKey);
    bool IsOpen(string resourceKey);
    Dictionary<string, CircuitBreakerState> GetAllStates();
}

public record CircuitBreakerState(
    string ResourceKey,
    bool IsOpen,
    int ConsecutiveFailures,
    int TotalFailures,
    int TotalSuccesses,
    DateTimeOffset? LastFailureAt,
    DateTimeOffset? OpenedAt);

public class CircuitBreakerManager : ICircuitBreakerManager
{
    private readonly ConcurrentDictionary<string, ResourceState> _states = new();
    private readonly ILogger<CircuitBreakerManager> _logger;

    private const int FailureThreshold = 5;
    private const int RecoveryWindowSeconds = 60;

    public CircuitBreakerManager(ILogger<CircuitBreakerManager> logger) => _logger = logger;

    public CircuitBreakerState GetState(string resourceKey)
    {
        var state = _states.GetOrAdd(resourceKey, _ => new ResourceState());
        return new CircuitBreakerState(
            resourceKey, state.IsOpen, state.ConsecutiveFailures,
            state.TotalFailures, state.TotalSuccesses,
            state.LastFailureAt, state.OpenedAt);
    }

    public void RecordSuccess(string resourceKey)
    {
        var state = _states.GetOrAdd(resourceKey, _ => new ResourceState());
        state.TotalSuccesses++;
        state.ConsecutiveFailures = 0;
        if (state.IsOpen)
        {
            state.IsOpen = false;
            state.OpenedAt = null;
            _logger.LogInformation("Circuit closed for {Resource}", resourceKey);
        }
    }

    public void RecordFailure(string resourceKey)
    {
        var state = _states.GetOrAdd(resourceKey, _ => new ResourceState());
        state.TotalFailures++;
        state.ConsecutiveFailures++;
        state.LastFailureAt = DateTimeOffset.UtcNow;

        if (!state.IsOpen && state.ConsecutiveFailures >= FailureThreshold)
        {
            state.IsOpen = true;
            state.OpenedAt = DateTimeOffset.UtcNow;
            _logger.LogError("Circuit OPENED for {Resource} after {Failures} consecutive failures",
                resourceKey, state.ConsecutiveFailures);
        }
    }

    public bool IsOpen(string resourceKey)
    {
        if (!_states.TryGetValue(resourceKey, out var state)) return false;
        if (!state.IsOpen) return false;

        // Auto-recover after window
        if (state.OpenedAt.HasValue &&
            (DateTimeOffset.UtcNow - state.OpenedAt.Value).TotalSeconds > RecoveryWindowSeconds)
        {
            state.IsOpen = false; // Half-open → allow one attempt
            _logger.LogInformation("Circuit half-open for {Resource}, allowing probe", resourceKey);
            return false;
        }
        return true;
    }

    public Dictionary<string, CircuitBreakerState> GetAllStates()
    {
        return _states.ToDictionary(
            kvp => kvp.Key,
            kvp => GetState(kvp.Key));
    }

    private class ResourceState
    {
        public bool IsOpen;
        public int ConsecutiveFailures;
        public int TotalFailures;
        public int TotalSuccesses;
        public DateTimeOffset? LastFailureAt;
        public DateTimeOffset? OpenedAt;
    }
}
