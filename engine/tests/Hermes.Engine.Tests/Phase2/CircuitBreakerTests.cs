using Microsoft.Extensions.Logging.Abstractions;
using Hermes.Engine.Services;

namespace Hermes.Engine.Tests.Phase2;

/// <summary>
/// Tests for circuit breaker system.
/// References: Polly CircuitBreaker, Netflix Hystrix, MassTransit circuit breaker.
///
/// Circuit breaker states:
/// - Closed: all calls pass through (normal operation)
/// - Open: calls are blocked (after N consecutive failures)
/// - Half-Open: one probe call allowed (after recovery window)
/// </summary>
public class CircuitBreakerTests
{
    [Fact]
    public void NewResource_IsClosed()
    {
        var manager = new CircuitBreakerManager(NullLogger<CircuitBreakerManager>.Instance);
        Assert.False(manager.IsOpen("http://api.vendor.com"));
    }

    [Fact]
    public void AfterConsecutiveFailures_Opens()
    {
        var manager = new CircuitBreakerManager(NullLogger<CircuitBreakerManager>.Instance);
        var resource = "http://api.vendor.com/status";

        // Default threshold is 5 consecutive failures
        for (int i = 0; i < 5; i++)
            manager.RecordFailure(resource);

        Assert.True(manager.IsOpen(resource));
        var state = manager.GetState(resource);
        Assert.True(state.IsOpen);
        Assert.Equal(5, state.ConsecutiveFailures);
        Assert.Equal(5, state.TotalFailures);
    }

    [Fact]
    public void SuccessResets_ConsecutiveFailures()
    {
        var manager = new CircuitBreakerManager(NullLogger<CircuitBreakerManager>.Instance);
        var resource = "db-connection";

        manager.RecordFailure(resource);
        manager.RecordFailure(resource);
        manager.RecordFailure(resource);
        manager.RecordSuccess(resource); // Reset consecutive count

        var state = manager.GetState(resource);
        Assert.False(state.IsOpen);
        Assert.Equal(0, state.ConsecutiveFailures);
        Assert.Equal(3, state.TotalFailures);
        Assert.Equal(1, state.TotalSuccesses);
    }

    [Fact]
    public void Success_ClosesOpenCircuit()
    {
        var manager = new CircuitBreakerManager(NullLogger<CircuitBreakerManager>.Instance);
        var resource = "s3-upload";

        // Open the circuit
        for (int i = 0; i < 5; i++)
            manager.RecordFailure(resource);
        Assert.True(manager.IsOpen(resource));

        // Success closes it
        manager.RecordSuccess(resource);
        Assert.False(manager.IsOpen(resource));
    }

    [Fact]
    public void MultipleResources_Independent()
    {
        var manager = new CircuitBreakerManager(NullLogger<CircuitBreakerManager>.Instance);

        // Open circuit for resource A
        for (int i = 0; i < 5; i++)
            manager.RecordFailure("resource-a");

        // Resource B is unaffected
        Assert.True(manager.IsOpen("resource-a"));
        Assert.False(manager.IsOpen("resource-b"));
    }

    [Fact]
    public void GetAllStates_ReturnsAllTracked()
    {
        var manager = new CircuitBreakerManager(NullLogger<CircuitBreakerManager>.Instance);

        manager.RecordSuccess("api-1");
        manager.RecordFailure("api-2");
        manager.RecordFailure("api-3");

        var states = manager.GetAllStates();
        Assert.Equal(3, states.Count);
        Assert.Contains("api-1", states.Keys);
        Assert.Contains("api-2", states.Keys);
        Assert.Contains("api-3", states.Keys);
    }

    [Fact]
    public void State_TracksTimestamps()
    {
        var manager = new CircuitBreakerManager(NullLogger<CircuitBreakerManager>.Instance);
        var resource = "timestamp-test";

        manager.RecordFailure(resource);
        var state = manager.GetState(resource);
        Assert.NotNull(state.LastFailureAt);
        Assert.Null(state.OpenedAt); // Not yet open (only 1 failure)

        // Open the circuit
        for (int i = 0; i < 4; i++)
            manager.RecordFailure(resource);

        state = manager.GetState(resource);
        Assert.NotNull(state.OpenedAt);
    }

    [Fact]
    public void BelowThreshold_StaysClosed()
    {
        var manager = new CircuitBreakerManager(NullLogger<CircuitBreakerManager>.Instance);
        var resource = "almost-failing";

        // 4 failures (threshold is 5)
        for (int i = 0; i < 4; i++)
            manager.RecordFailure(resource);

        Assert.False(manager.IsOpen(resource));
        Assert.Equal(4, manager.GetState(resource).ConsecutiveFailures);
    }

    [Fact]
    public void InterleavedSuccessAndFailure_NeverOpens()
    {
        var manager = new CircuitBreakerManager(NullLogger<CircuitBreakerManager>.Instance);
        var resource = "flaky-service";

        // Alternating pattern: never reaches 5 consecutive
        for (int i = 0; i < 20; i++)
        {
            manager.RecordFailure(resource);
            manager.RecordFailure(resource);
            manager.RecordSuccess(resource); // Resets consecutive count
        }

        Assert.False(manager.IsOpen(resource));
        Assert.Equal(40, manager.GetState(resource).TotalFailures);
        Assert.Equal(20, manager.GetState(resource).TotalSuccesses);
    }
}
