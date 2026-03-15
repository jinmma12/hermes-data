using Microsoft.AspNetCore.Server.Kestrel.Core;
using Microsoft.EntityFrameworkCore;
using Serilog;
using Hermes.Engine.Domain;
using Hermes.Engine.Grpc;
using Hermes.Engine.Infrastructure.Data;
using Hermes.Engine.Services;
using Hermes.Engine.Services.Monitors;
using Hermes.Engine.Services.Plugins;
using Hermes.Engine.Workers;
using Hermes.Engine.Observability;
using Hermes.Engine.Services.Nifi;
using Prometheus;

Log.Logger = new LoggerConfiguration()
    .WriteTo.Console(outputTemplate:
        "[{Timestamp:HH:mm:ss} {Level:u3}] [{SourceContext}] {Message:lj}{NewLine}{Exception}")
    .CreateBootstrapLogger();

try
{
    var builder = WebApplication.CreateBuilder(args);

    // Serilog with structured JSON logging
    builder.Services.AddSerilog(config => config
        .ReadFrom.Configuration(builder.Configuration)
        .Enrich.WithProperty("Application", "Hermes.Engine")
        .Enrich.WithProperty("Environment", builder.Environment.EnvironmentName)
        .WriteTo.Console(outputTemplate:
            "[{Timestamp:HH:mm:ss} {Level:u3}] [{SourceContext}] {Message:lj}{NewLine}{Exception}"));

    // gRPC
    builder.Services.AddGrpc();

    // Kestrel: HTTP/2 for gRPC on 50051, HTTP/1.1 for metrics on 9090
    var grpcPort = builder.Configuration.GetValue<int>("Grpc:Port", 50051);
    var metricsPort = builder.Configuration.GetValue<int>("Metrics:PrometheusPort", 9090);
    builder.WebHost.ConfigureKestrel(options =>
    {
        options.ListenAnyIP(grpcPort, o => o.Protocols = HttpProtocols.Http2);
        options.ListenAnyIP(metricsPort, o => o.Protocols = HttpProtocols.Http1);
    });

    // Database — supports PostgreSQL and SQL Server
    var dbProvider = builder.Configuration.GetValue<string>("Database:Provider") ?? "PostgreSQL";
    var connectionString = dbProvider.Equals("SqlServer", StringComparison.OrdinalIgnoreCase)
        ? builder.Configuration.GetConnectionString("SqlServer")
        : builder.Configuration.GetConnectionString("DefaultConnection");

    builder.Services.AddDbContext<HermesDbContext>(options =>
    {
        if (dbProvider.Equals("SqlServer", StringComparison.OrdinalIgnoreCase))
            options.UseSqlServer(connectionString);
        else
            options.UseNpgsql(connectionString);
    });

    Log.Information("Database provider: {Provider}", dbProvider);

    // HTTP client
    builder.Services.AddHttpClient();

    // Domain services
    builder.Services.AddSingleton<IConditionEvaluator, ConditionEvaluator>();
    builder.Services.AddSingleton<IBackPressureManager, BackPressureManager>();
    builder.Services.AddSingleton<IDeadLetterQueue, DeadLetterQueue>();
    builder.Services.AddSingleton<ICircuitBreakerManager, CircuitBreakerManager>();

    // Content Repository (disk-based large data storage)
    var contentRepoPath = builder.Configuration.GetValue<string>("Engine:ContentRepositoryPath")
        ?? Path.Combine(AppContext.BaseDirectory, "content-repo");
    builder.Services.AddSingleton<IContentRepository>(sp =>
        new ContentRepository(contentRepoPath, sp.GetRequiredService<ILogger<ContentRepository>>()));

    builder.Services.AddHostedService<GracefulShutdownHandler>();
    builder.Services.AddScoped<ISnapshotResolver, SnapshotResolver>();
    builder.Services.AddScoped<IProcessingOrchestrator, ProcessingOrchestrator>();

    // Plugin system
    builder.Services.AddSingleton<IPluginRegistry, PluginRegistry>();
    builder.Services.AddSingleton<IPluginExecutor>(sp =>
        new PluginExecutor(
            sp.GetRequiredService<ILogger<PluginExecutor>>(),
            builder.Configuration.GetValue<int>("Engine:PluginTimeoutSeconds", 300)));
    builder.Services.AddScoped<IExecutionDispatcher, ExecutionDispatcher>();

    // Schema registry (schema discovery & drift detection)
    builder.Services.AddSingleton<ISchemaRegistry, SchemaRegistry>();

    // Checkpoint manager (exactly-once processing with step-level checkpointing)
    builder.Services.AddSingleton<ICheckpointManager, CheckpointManager>();

    // NiFi integration (optional)
    var nifiConfig = builder.Configuration.GetSection("NiFi").Get<NiFiClientConfig>() ?? new NiFiClientConfig();
    if (nifiConfig.Enabled)
    {
        builder.Services.AddSingleton(nifiConfig);
        builder.Services.AddHttpClient<INiFiClient, NiFiClient>();
        builder.Services.AddSingleton<INiFiBridge, NiFiBridge>();
        Log.Information("NiFi integration enabled: {Url}", nifiConfig.BaseUrl);
    }

    // Monitoring engine (singleton - manages all monitoring tasks)
    builder.Services.AddSingleton<IMonitoringEngine, MonitoringEngine>();

    // Background workers
    builder.Services.AddHostedService<MonitoringWorker>();
    builder.Services.AddHostedService<ProcessingWorker>();

    // Generic repositories
    builder.Services.AddScoped(typeof(IRepository<>), typeof(Repository<>));

    var app = builder.Build();

    // gRPC endpoint
    app.MapGrpcService<HermesEngineGrpcService>();

    // Prometheus metrics endpoint: GET http://localhost:9090/metrics
    app.UseRouting();
    app.MapMetrics("/metrics").RequireHost($"*:{metricsPort}");

    // Auto-create database tables (EnsureCreated for dev; use migrations in prod)
    using (var scope = app.Services.CreateScope())
    {
        var db = scope.ServiceProvider.GetRequiredService<HermesDbContext>();
        await db.Database.EnsureCreatedAsync();
    }

    // Discover plugins
    var pluginRegistry = app.Services.GetRequiredService<IPluginRegistry>();
    var pluginsDir = Path.Combine(AppContext.BaseDirectory, "..", "..", "..", "..", "plugins");
    if (Directory.Exists(pluginsDir))
        pluginRegistry.DiscoverPlugins(pluginsDir);

    Log.Information("Hermes Engine starting — gRPC:{GrpcPort}, Metrics:{MetricsPort}",
        grpcPort, metricsPort);
    await app.RunAsync();
}
catch (Exception ex)
{
    Log.Fatal(ex, "Hermes Engine terminated unexpectedly");
}
finally
{
    await Log.CloseAndFlushAsync();
}
