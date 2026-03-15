using Polly;
using Polly.CircuitBreaker;
using Polly.Retry;
using Polly.Timeout;
using Microsoft.Extensions.Logging;

namespace Hermes.Engine.Services;

/// <summary>
/// Centralized Polly resilience policies for all external calls.
/// </summary>
public static class ResiliencePolicies
{
    /// <summary>
    /// Create a resilience pipeline for plugin execution:
    /// Retry (3x, exponential + jitter) → Circuit Breaker → Timeout
    /// </summary>
    public static ResiliencePipeline<T> CreatePluginPipeline<T>(ILogger logger, string pluginName, int timeoutSeconds = 300)
    {
        return new ResiliencePipelineBuilder<T>()
            .AddRetry(new RetryStrategyOptions<T>
            {
                MaxRetryAttempts = 3,
                BackoffType = DelayBackoffType.Exponential,
                UseJitter = true,
                Delay = TimeSpan.FromSeconds(1),
                OnRetry = args =>
                {
                    logger.LogWarning("Retry {Attempt} for plugin {Plugin}: {Outcome}",
                        args.AttemptNumber, pluginName, args.Outcome.Exception?.Message ?? "failed result");
                    return ValueTask.CompletedTask;
                }
            })
            .AddCircuitBreaker(new CircuitBreakerStrategyOptions<T>
            {
                FailureRatio = 0.5,
                SamplingDuration = TimeSpan.FromSeconds(30),
                MinimumThroughput = 5,
                BreakDuration = TimeSpan.FromSeconds(30),
                OnOpened = args =>
                {
                    logger.LogError("Circuit OPEN for plugin {Plugin}: too many failures", pluginName);
                    return ValueTask.CompletedTask;
                },
                OnClosed = args =>
                {
                    logger.LogInformation("Circuit CLOSED for plugin {Plugin}: recovered", pluginName);
                    return ValueTask.CompletedTask;
                },
                OnHalfOpened = args =>
                {
                    logger.LogInformation("Circuit HALF-OPEN for plugin {Plugin}: testing recovery", pluginName);
                    return ValueTask.CompletedTask;
                }
            })
            .AddTimeout(TimeSpan.FromSeconds(timeoutSeconds))
            .Build();
    }

    /// <summary>
    /// Create a resilience pipeline for HTTP calls (API polling, HTTP step execution):
    /// Retry (5x, exponential + jitter) → Circuit Breaker → Timeout
    /// </summary>
    public static ResiliencePipeline<T> CreateHttpPipeline<T>(ILogger logger, string endpoint, int timeoutSeconds = 30)
    {
        return new ResiliencePipelineBuilder<T>()
            .AddRetry(new RetryStrategyOptions<T>
            {
                MaxRetryAttempts = 5,
                BackoffType = DelayBackoffType.Exponential,
                UseJitter = true,
                Delay = TimeSpan.FromMilliseconds(500),
                OnRetry = args =>
                {
                    logger.LogWarning("HTTP retry {Attempt} for {Endpoint}: {Error}",
                        args.AttemptNumber, endpoint, args.Outcome.Exception?.Message ?? "failed");
                    return ValueTask.CompletedTask;
                }
            })
            .AddCircuitBreaker(new CircuitBreakerStrategyOptions<T>
            {
                FailureRatio = 0.5,
                SamplingDuration = TimeSpan.FromSeconds(60),
                MinimumThroughput = 10,
                BreakDuration = TimeSpan.FromSeconds(60),
                OnOpened = args =>
                {
                    logger.LogError("HTTP circuit OPEN for {Endpoint}", endpoint);
                    return ValueTask.CompletedTask;
                },
                OnClosed = args =>
                {
                    logger.LogInformation("HTTP circuit CLOSED for {Endpoint}", endpoint);
                    return ValueTask.CompletedTask;
                }
            })
            .AddTimeout(TimeSpan.FromSeconds(timeoutSeconds))
            .Build();
    }

    /// <summary>
    /// Simple retry for database operations.
    /// </summary>
    public static ResiliencePipeline CreateDatabasePipeline(ILogger logger)
    {
        return new ResiliencePipelineBuilder()
            .AddRetry(new RetryStrategyOptions
            {
                MaxRetryAttempts = 3,
                BackoffType = DelayBackoffType.Exponential,
                UseJitter = true,
                Delay = TimeSpan.FromMilliseconds(200),
                OnRetry = args =>
                {
                    logger.LogWarning("DB retry {Attempt}: {Error}",
                        args.AttemptNumber, args.Outcome.Exception?.Message ?? "transient error");
                    return ValueTask.CompletedTask;
                }
            })
            .Build();
    }
}
