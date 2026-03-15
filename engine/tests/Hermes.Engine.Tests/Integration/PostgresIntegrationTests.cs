using System.Text.Json;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Logging.Abstractions;
using Hermes.Engine.Domain;
using Hermes.Engine.Domain.Entities;
using Hermes.Engine.Infrastructure.Data;
using Hermes.Engine.Services;

namespace Hermes.Engine.Tests.Integration;

/// <summary>
/// Integration tests against a real PostgreSQL instance.
/// Requires: docker run -d --name hermes-test-pg -e POSTGRES_USER=hermes -e POSTGRES_PASSWORD=hermes
///           -e POSTGRES_DB=hermes_test -p 5433:5432 postgres:15-alpine
/// </summary>
[Collection("PostgresTests")]
public class PostgresIntegrationTests : IAsyncLifetime
{
    private const string ConnectionString =
        "Host=localhost;Port=5433;Database=hermes_test;Username=hermes;Password=hermes";

    private HermesDbContext _db = null!;

    public async Task InitializeAsync()
    {
        var options = new DbContextOptionsBuilder<HermesDbContext>()
            .UseNpgsql(ConnectionString)
            .Options;
        _db = new HermesDbContext(options);

        // Drop and recreate all tables for clean state
        await _db.Database.EnsureDeletedAsync();
        await _db.Database.EnsureCreatedAsync();
    }

    public async Task DisposeAsync()
    {
        await _db.Database.EnsureDeletedAsync();
        await _db.DisposeAsync();
    }

    // ── Schema Creation ──

    [Fact]
    public async Task Schema_AllTablesCreated()
    {
        var tables = await GetTableNamesRaw();

        // Check core tables exist (lowercase — as specified in ToTable())
        Assert.Contains("pipeline_instances", tables);
        Assert.Contains("pipeline_steps", tables);
        Assert.Contains("pipeline_activations", tables);
        Assert.Contains("work_items", tables);
        Assert.Contains("work_item_executions", tables);
        Assert.Contains("work_item_step_executions", tables);
        Assert.Contains("execution_snapshots", tables);
        Assert.Contains("execution_event_logs", tables);
        Assert.Contains("reprocess_requests", tables);
        Assert.Contains("collector_definitions", tables);
        Assert.Contains("algorithm_definitions", tables);
        Assert.Contains("transfer_definitions", tables);
        Assert.Contains("collector_instances", tables);
        Assert.Contains("algorithm_instances", tables);
        Assert.Contains("transfer_instances", tables);
    }

    [Fact]
    public async Task Schema_JsonbColumnsWork()
    {
        var pipeline = new PipelineInstance
        {
            Name = "JSONB Test Pipeline",
            MonitoringType = MonitoringType.FileMonitor,
            MonitoringConfig = JsonSerializer.Serialize(new
            {
                watch_path = "/data/incoming",
                file_pattern = "*.csv",
                interval = "30s",
                recursive = true
            }),
            Status = PipelineStatus.Draft
        };
        _db.PipelineInstances.Add(pipeline);
        await _db.SaveChangesAsync();

        // Read back and verify JSONB round-trips
        var loaded = await _db.PipelineInstances.FindAsync(pipeline.Id);
        Assert.NotNull(loaded);
        var config = JsonDocument.Parse(loaded.MonitoringConfig);
        Assert.Equal("/data/incoming", config.RootElement.GetProperty("watch_path").GetString());
        Assert.True(config.RootElement.GetProperty("recursive").GetBoolean());
    }

    // ── Definition CRUD ──

    [Fact]
    public async Task Definitions_CRUD_Roundtrip()
    {
        var def = new CollectorDefinition
        {
            Code = "pg-test-collector",
            Name = "PostgreSQL Test Collector",
            Description = "Integration test",
            Category = "Test",
            Status = DefinitionStatus.Active
        };
        _db.CollectorDefinitions.Add(def);
        await _db.SaveChangesAsync();

        var version = new CollectorDefinitionVersion
        {
            DefinitionId = def.Id,
            VersionNo = 1,
            InputSchema = JsonSerializer.Serialize(new
            {
                type = "object",
                properties = new { url = new { type = "string" } }
            }),
            OutputSchema = "{}",
            ExecutionType = ExecutionType.Plugin,
            ExecutionRef = "COLLECTOR:pg-test-collector",
            IsPublished = true
        };
        _db.CollectorDefinitionVersions.Add(version);
        await _db.SaveChangesAsync();

        // Read back
        var loaded = await _db.CollectorDefinitions
            .Include(d => d.Versions)
            .FirstAsync(d => d.Code == "pg-test-collector");
        Assert.Equal("PostgreSQL Test Collector", loaded.Name);
        Assert.Single(loaded.Versions);
        Assert.Contains("url", loaded.Versions[0].InputSchema);
    }

    // ── Full Pipeline with Real DB ──

    [Fact]
    public async Task FullPipeline_CreateAndProcess_WithRealPostgres()
    {
        // 1. Seed definitions + instances
        var collDef = new CollectorDefinition { Code = "pg-coll", Name = "PG Collector", Status = DefinitionStatus.Active };
        var algoDef = new AlgorithmDefinition { Code = "pg-algo", Name = "PG Algorithm", Status = DefinitionStatus.Active };
        var transDef = new TransferDefinition { Code = "pg-trans", Name = "PG Transfer", Status = DefinitionStatus.Active };
        _db.CollectorDefinitions.Add(collDef);
        _db.AlgorithmDefinitions.Add(algoDef);
        _db.TransferDefinitions.Add(transDef);
        await _db.SaveChangesAsync();

        var collDefV = new CollectorDefinitionVersion { DefinitionId = collDef.Id, VersionNo = 1, ExecutionType = ExecutionType.Plugin, ExecutionRef = "COLLECTOR:pg-coll", IsPublished = true };
        var algoDefV = new AlgorithmDefinitionVersion { DefinitionId = algoDef.Id, VersionNo = 1, ExecutionType = ExecutionType.Plugin, ExecutionRef = "ALGORITHM:pg-algo", IsPublished = true };
        var transDefV = new TransferDefinitionVersion { DefinitionId = transDef.Id, VersionNo = 1, ExecutionType = ExecutionType.Plugin, ExecutionRef = "TRANSFER:pg-trans", IsPublished = true };
        _db.CollectorDefinitionVersions.Add(collDefV);
        _db.AlgorithmDefinitionVersions.Add(algoDefV);
        _db.TransferDefinitionVersions.Add(transDefV);
        await _db.SaveChangesAsync();

        var collInst = new CollectorInstance { DefinitionId = collDef.Id, Name = "PG Coll Inst", Status = InstanceStatus.Active };
        var algoInst = new AlgorithmInstance { DefinitionId = algoDef.Id, Name = "PG Algo Inst", Status = InstanceStatus.Active };
        var transInst = new TransferInstance { DefinitionId = transDef.Id, Name = "PG Trans Inst", Status = InstanceStatus.Active };
        _db.CollectorInstances.Add(collInst);
        _db.AlgorithmInstances.Add(algoInst);
        _db.TransferInstances.Add(transInst);
        await _db.SaveChangesAsync();

        _db.CollectorInstanceVersions.Add(new() { InstanceId = collInst.Id, DefVersionId = collDefV.Id, VersionNo = 1, ConfigJson = "{\"source\":\"pg\"}", IsCurrent = true });
        _db.AlgorithmInstanceVersions.Add(new() { InstanceId = algoInst.Id, DefVersionId = algoDefV.Id, VersionNo = 1, ConfigJson = "{\"mode\":\"test\"}", IsCurrent = true });
        _db.TransferInstanceVersions.Add(new() { InstanceId = transInst.Id, DefVersionId = transDefV.Id, VersionNo = 1, ConfigJson = "{\"dest\":\"pg\"}", IsCurrent = true });
        await _db.SaveChangesAsync();

        // 2. Create pipeline with steps
        var pipeline = new PipelineInstance
        {
            Name = "PG Integration Pipeline",
            MonitoringType = MonitoringType.FileMonitor,
            MonitoringConfig = "{}",
            Status = PipelineStatus.Active,
            Steps = new List<PipelineStep>
            {
                new() { StepOrder = 1, StepType = StageType.Collect, RefType = RefType.Collector, RefId = collInst.Id },
                new() { StepOrder = 2, StepType = StageType.Algorithm, RefType = RefType.Algorithm, RefId = algoInst.Id, OnError = OnErrorAction.Skip },
                new() { StepOrder = 3, StepType = StageType.Transfer, RefType = RefType.Transfer, RefId = transInst.Id },
            }
        };
        _db.PipelineInstances.Add(pipeline);
        await _db.SaveChangesAsync();

        var activation = new PipelineActivation
        {
            PipelineInstanceId = pipeline.Id,
            Status = ActivationStatus.Running,
            WorkerId = "pg-test-worker"
        };
        _db.PipelineActivations.Add(activation);
        await _db.SaveChangesAsync();

        // 3. Create work item
        var workItem = new WorkItem
        {
            PipelineActivationId = activation.Id,
            PipelineInstanceId = pipeline.Id,
            SourceType = SourceType.File,
            SourceKey = "/data/pg_test.csv",
            SourceMetadata = "{\"rows\":100}",
            DedupKey = "FILE:pg_test_hash",
            Status = JobStatus.Queued
        };
        _db.WorkItems.Add(workItem);
        await _db.SaveChangesAsync();

        // 4. Process through orchestrator with real DB
        var snapshotResolver = new SnapshotResolver(_db);
        var fakeDispatcher = new FakeSuccessDispatcher();
        var orchestrator = new ProcessingOrchestrator(_db, fakeDispatcher, snapshotResolver,
            NullLogger<ProcessingOrchestrator>.Instance);

        var execution = await orchestrator.ProcessWorkItemAsync(workItem.Id);

        // 5. Verify everything persisted correctly in PostgreSQL
        Assert.Equal(ExecutionStatus.Completed, execution.Status);

        // Re-query from DB (fresh read)
        var savedItem = await _db.WorkItems.FindAsync(workItem.Id);
        Assert.Equal(JobStatus.Completed, savedItem!.Status);
        Assert.Equal(1, savedItem.ExecutionCount);

        var savedExecution = await _db.WorkItemExecutions.FirstAsync(e => e.WorkItemId == workItem.Id);
        Assert.Equal(ExecutionStatus.Completed, savedExecution.Status);
        Assert.True(savedExecution.DurationMs > 0);

        var savedSteps = await _db.WorkItemStepExecutions
            .Where(se => se.ExecutionId == savedExecution.Id)
            .OrderBy(se => se.StepOrder)
            .ToListAsync();
        Assert.Equal(3, savedSteps.Count);

        var savedSnapshot = await _db.ExecutionSnapshots.FirstAsync(s => s.ExecutionId == savedExecution.Id);
        Assert.NotNull(savedSnapshot.SnapshotHash);
        Assert.Contains("pg", savedSnapshot.CollectorConfig);

        var savedLogs = await _db.ExecutionEventLogs
            .Where(l => l.ExecutionId == savedExecution.Id)
            .ToListAsync();
        Assert.True(savedLogs.Count >= 2);
    }

    // ── Schema Portability ──

    [Fact]
    public async Task Schema_RecreateOnNewDatabase_Identical()
    {
        // Get tables from current DB
        var tables1 = await GetTableNamesRaw();

        // Create a second DB context pointing to same server, different DB
        var connStr2 = "Host=localhost;Port=5433;Database=hermes_test_2;Username=hermes;Password=hermes";
        var opts2 = new DbContextOptionsBuilder<HermesDbContext>()
            .UseNpgsql(connStr2).Options;
        await using var db2 = new HermesDbContext(opts2);
        await db2.Database.EnsureDeletedAsync();
        await db2.Database.EnsureCreatedAsync();

        var tables2 = await GetTableNamesRaw(connStr2);

        // Cleanup
        await db2.Database.EnsureDeletedAsync();

        // Both databases should have identical table sets
        Assert.Equal(tables1.OrderBy(t => t), tables2.OrderBy(t => t));
    }

    [Fact]
    public async Task EnumStorage_PersistedAsStrings()
    {
        var pipeline = new PipelineInstance
        {
            Name = "Enum Storage Test",
            MonitoringType = MonitoringType.ApiPoll,
            Status = PipelineStatus.Active
        };
        _db.PipelineInstances.Add(pipeline);
        await _db.SaveChangesAsync();

        // Query raw SQL to verify enum is stored as string, not integer
        using var conn = new Npgsql.NpgsqlConnection(ConnectionString);
        await conn.OpenAsync();
        await using var cmd = conn.CreateCommand();
        cmd.CommandText = $"SELECT \"Status\", \"MonitoringType\" FROM pipeline_instances WHERE \"Id\" = '{pipeline.Id}'";
        await using var reader = await cmd.ExecuteReaderAsync();
        Assert.True(await reader.ReadAsync());

        var status = reader.GetString(0);
        var monType = reader.GetString(1);
        Assert.Equal("Active", status);
        Assert.Equal("ApiPoll", monType);
    }

    [Fact]
    public async Task Timestamps_AutoUpdated()
    {
        var pipeline = new PipelineInstance { Name = "Timestamp Test", Status = PipelineStatus.Draft };
        _db.PipelineInstances.Add(pipeline);
        await _db.SaveChangesAsync();

        var created = pipeline.CreatedAt;
        Assert.True(created > DateTimeOffset.MinValue);

        // Update
        await Task.Delay(10); // Ensure time passes
        pipeline.Name = "Timestamp Test Updated";
        await _db.SaveChangesAsync();

        Assert.True(pipeline.UpdatedAt >= created);
    }

    [Fact]
    public async Task UniqueConstraint_DefinitionCode()
    {
        _db.CollectorDefinitions.Add(new CollectorDefinition { Code = "unique-code", Name = "First" });
        await _db.SaveChangesAsync();

        _db.CollectorDefinitions.Add(new CollectorDefinition { Code = "unique-code", Name = "Duplicate" });
        await Assert.ThrowsAsync<DbUpdateException>(() => _db.SaveChangesAsync());
    }

    [Fact]
    public async Task CascadeDelete_Pipeline_RemovesSteps()
    {
        var pipeline = new PipelineInstance
        {
            Name = "Cascade Test",
            Steps = new List<PipelineStep>
            {
                new() { StepOrder = 1, StepType = StageType.Collect, RefType = RefType.Collector, RefId = Guid.NewGuid() },
                new() { StepOrder = 2, StepType = StageType.Algorithm, RefType = RefType.Algorithm, RefId = Guid.NewGuid() },
            }
        };
        _db.PipelineInstances.Add(pipeline);
        await _db.SaveChangesAsync();

        Assert.Equal(2, await _db.PipelineSteps.CountAsync(s => s.PipelineInstanceId == pipeline.Id));

        _db.PipelineInstances.Remove(pipeline);
        await _db.SaveChangesAsync();

        Assert.Equal(0, await _db.PipelineSteps.CountAsync(s => s.PipelineInstanceId == pipeline.Id));
    }

    // ── Helpers ──

    private async Task<List<string>> GetTableNamesRaw(string? connStr = null)
    {
        var tables = new List<string>();
        using var conn = new Npgsql.NpgsqlConnection(connStr ?? ConnectionString);
        await conn.OpenAsync();
        await using var cmd = conn.CreateCommand();
        cmd.CommandText = "SELECT tablename FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename";
        await using var reader = await cmd.ExecuteReaderAsync();
        while (await reader.ReadAsync())
            tables.Add(reader.GetString(0));
        return tables;
    }

    private class FakeSuccessDispatcher : IExecutionDispatcher
    {
        public Task<ExecutionResult> DispatchAsync(
            ExecutionType executionType, string? executionRef, string configJson,
            string? inputDataJson = null, Dictionary<string, string>? context = null,
            CancellationToken ct = default)
        {
            return Task.FromResult(new ExecutionResult(true,
                JsonSerializer.Serialize(new { step = context?.GetValueOrDefault("step_order"), ok = true }),
                "{\"status\":\"success\"}", 15, new()));
        }
    }
}
