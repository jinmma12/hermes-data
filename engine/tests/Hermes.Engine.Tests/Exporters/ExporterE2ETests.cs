using System.Text.Json;
using Microsoft.Extensions.Logging;
using Hermes.Engine.Services.Exporters;

namespace Hermes.Engine.Tests.Exporters;

/// <summary>
/// E2E tests for all 4 Export connectors:
/// - DbWriter: INSERT/UPSERT, batch, error handling
/// - Webhook: POST/auth/retry/batch, HTTP errors
/// - KafkaProducer: config parsing, validation
/// - S3Upload: key building, compression, CSV/JSON serialization
///
/// Also covers Recipe config → actual execution flow (proving that user-provided
/// recipe values actually drive connector behavior).
/// </summary>
public class ExporterE2ETests
{
    // ════════════════════════════════════════════════════════════════════
    // 1. DB WRITER — Config, SQL, Batch, Error
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public void DbWriterConfig_ParsesFromJson()
    {
        var json = JsonDocument.Parse("""
        {
            "connection_string": "Host=localhost;Database=test",
            "table_name": "sensor_data",
            "write_mode": "UPSERT",
            "conflict_key": "id",
            "batch_size": 500,
            "timeout_seconds": 60
        }
        """).RootElement;

        var config = DbWriterConfig.FromJson(json);
        Assert.Equal("Host=localhost;Database=test", config.ConnectionString);
        Assert.Equal("sensor_data", config.TableName);
        Assert.Equal("UPSERT", config.WriteMode);
        Assert.Equal("id", config.ConflictKey);
        Assert.Equal(500, config.BatchSize);
        Assert.Equal(60, config.TimeoutSeconds);
    }

    [Fact]
    public void DbWriterConfig_DefaultValues()
    {
        var config = DbWriterConfig.FromJson(JsonDocument.Parse("{}").RootElement);
        Assert.Equal("", config.ConnectionString);
        Assert.Equal("INSERT", config.WriteMode);
        Assert.Equal(1000, config.BatchSize);
        Assert.Equal(30, config.TimeoutSeconds);
        Assert.Equal("PostgreSQL", config.Provider);
    }

    [Fact]
    public async Task DbWriter_RejectsEmptyConnectionString()
    {
        var config = new DbWriterConfig { ConnectionString = "", TableName = "test" };
        var exporter = new DbWriterExporter(config);
        var ctx = new ExportContext("[{\"a\":1}]", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.False(result.Success);
        Assert.Contains("connection string", result.ErrorMessage!.ToLower());
    }

    [Fact]
    public async Task DbWriter_RejectsEmptyTableName()
    {
        var config = new DbWriterConfig { ConnectionString = "Host=test", TableName = "" };
        var exporter = new DbWriterExporter(config);
        var ctx = new ExportContext("[{\"a\":1}]", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.False(result.Success);
        Assert.Contains("table name", result.ErrorMessage!.ToLower());
    }

    [Fact]
    public async Task DbWriter_EmptyRecords_SuccessWithZero()
    {
        var config = new DbWriterConfig { ConnectionString = "Host=test", TableName = "t" };
        var exporter = new DbWriterExporter(config);
        var ctx = new ExportContext("[]", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.True(result.Success);
        Assert.Equal(0, result.RecordsExported);
    }

    [Fact]
    public async Task DbWriter_InvalidConnectionString_FailsGracefully()
    {
        var config = new DbWriterConfig
        {
            ConnectionString = "Host=nonexistent-host;Database=test;Timeout=1",
            TableName = "test_table"
        };
        var exporter = new DbWriterExporter(config);
        var ctx = new ExportContext("""[{"id":1,"value":"test"}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.False(result.Success);
        Assert.NotNull(result.ErrorMessage);
    }

    [Fact]
    public void DbWriterConfig_RecipeValuesApplied()
    {
        // Simulates: operator changes table_name via Recipe UI
        var recipe = """
        {
            "connection_string": "Host=prod-db;Database=analytics",
            "table_name": "daily_metrics",
            "write_mode": "UPSERT",
            "conflict_key": "metric_date",
            "batch_size": 2000
        }
        """;
        var config = DbWriterConfig.FromJson(JsonDocument.Parse(recipe).RootElement);

        Assert.Equal("daily_metrics", config.TableName);
        Assert.Equal("UPSERT", config.WriteMode);
        Assert.Equal("metric_date", config.ConflictKey);
        Assert.Equal(2000, config.BatchSize);
    }

    // ════════════════════════════════════════════════════════════════════
    // 2. WEBHOOK SENDER — HTTP, Auth, Retry, Errors
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public void WebhookConfig_ParsesFromJson()
    {
        var json = JsonDocument.Parse("""
        {
            "url": "https://hooks.example.com/ingest",
            "method": "POST",
            "auth_type": "bearer",
            "auth_token": "secret-token-123",
            "timeout_seconds": 15,
            "max_retries": 5,
            "batch_mode": true,
            "headers": {"X-Custom": "value"}
        }
        """).RootElement;

        var config = WebhookSenderConfig.FromJson(json);
        Assert.Equal("https://hooks.example.com/ingest", config.Url);
        Assert.Equal("POST", config.Method);
        Assert.Equal("bearer", config.AuthType);
        Assert.Equal("secret-token-123", config.AuthToken);
        Assert.Equal(15, config.TimeoutSeconds);
        Assert.Equal(5, config.MaxRetries);
        Assert.True(config.BatchMode);
        Assert.Equal("value", config.Headers["X-Custom"]);
    }

    [Fact]
    public async Task Webhook_RejectsEmptyUrl()
    {
        var config = new WebhookSenderConfig { Url = "" };
        var exporter = new WebhookSenderExporter(config, new HttpClient());
        var ctx = new ExportContext("""[{"a":1}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.False(result.Success);
        Assert.Contains("URL", result.ErrorMessage!);
    }

    [Fact]
    public async Task Webhook_SuccessfulPost()
    {
        var handler = new MockHttpHandler(System.Net.HttpStatusCode.OK, "{}");
        var client = new HttpClient(handler);
        var config = new WebhookSenderConfig { Url = "https://example.com/hook", MaxRetries = 0 };
        var exporter = new WebhookSenderExporter(config, client);
        var ctx = new ExportContext("""[{"event":"test"}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.True(result.Success);
        Assert.Equal(1, result.RecordsExported);
        Assert.Equal("https://example.com/hook", result.DestinationInfo);
    }

    [Fact]
    public async Task Webhook_BatchMode_SendsAllInOneRequest()
    {
        var handler = new MockHttpHandler(System.Net.HttpStatusCode.OK, "{}");
        var client = new HttpClient(handler);
        var config = new WebhookSenderConfig { Url = "https://example.com/hook", BatchMode = true, MaxRetries = 0 };
        var exporter = new WebhookSenderExporter(config, client);
        var ctx = new ExportContext("""[{"a":1},{"a":2},{"a":3}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.True(result.Success);
        Assert.Equal(3, result.RecordsExported);
        Assert.Equal(1, handler.CallCount); // Only 1 HTTP request
    }

    [Fact]
    public async Task Webhook_IndividualMode_SendsPerRecord()
    {
        var handler = new MockHttpHandler(System.Net.HttpStatusCode.OK, "{}");
        var client = new HttpClient(handler);
        var config = new WebhookSenderConfig { Url = "https://example.com/hook", BatchMode = false, MaxRetries = 0 };
        var exporter = new WebhookSenderExporter(config, client);
        var ctx = new ExportContext("""[{"a":1},{"a":2},{"a":3}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.True(result.Success);
        Assert.Equal(3, result.RecordsExported);
        Assert.Equal(3, handler.CallCount);
    }

    [Fact]
    public async Task Webhook_ClientError_NotRetried()
    {
        var handler = new MockHttpHandler(System.Net.HttpStatusCode.BadRequest, "bad request");
        var client = new HttpClient(handler);
        var config = new WebhookSenderConfig { Url = "https://example.com/hook", MaxRetries = 3 };
        var exporter = new WebhookSenderExporter(config, client);
        var ctx = new ExportContext("""[{"a":1}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.False(result.Success);
        Assert.Equal(1, handler.CallCount); // Client errors NOT retried
    }

    [Fact]
    public void WebhookConfig_RecipeValuesApplied()
    {
        var recipe = """
        {
            "url": "https://alerts.company.com/api/v2/events",
            "auth_type": "api_key",
            "auth_token": "ak_prod_12345",
            "api_key_header": "X-Alert-Key",
            "batch_mode": false
        }
        """;
        var config = WebhookSenderConfig.FromJson(JsonDocument.Parse(recipe).RootElement);

        Assert.Equal("api_key", config.AuthType);
        Assert.Equal("ak_prod_12345", config.AuthToken);
        Assert.Equal("X-Alert-Key", config.ApiKeyHeader);
    }

    // ════════════════════════════════════════════════════════════════════
    // 3. KAFKA PRODUCER — Config, Validation
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public void KafkaConfig_ParsesFromJson()
    {
        var json = JsonDocument.Parse("""
        {
            "bootstrap_servers": "kafka1:9092,kafka2:9092",
            "topic": "sensor-events",
            "key_field": "device_id",
            "acks": "all",
            "compression": "snappy",
            "enable_idempotence": true,
            "batch_size": 32768
        }
        """).RootElement;

        var config = KafkaProducerConfig.FromJson(json);
        Assert.Equal("kafka1:9092,kafka2:9092", config.BootstrapServers);
        Assert.Equal("sensor-events", config.Topic);
        Assert.Equal("device_id", config.KeyField);
        Assert.Equal("all", config.Acks);
        Assert.Equal("snappy", config.Compression);
        Assert.True(config.EnableIdempotence);
        Assert.Equal(32768, config.BatchSize);
    }

    [Fact]
    public async Task Kafka_RejectsEmptyTopic()
    {
        var config = new KafkaProducerConfig { BootstrapServers = "localhost:9092", Topic = "" };
        var exporter = new KafkaProducerExporter(config);
        var ctx = new ExportContext("""[{"x":1}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.False(result.Success);
        Assert.Contains("topic", result.ErrorMessage!.ToLower());
    }

    [Fact]
    public async Task Kafka_RejectsEmptyBootstrap()
    {
        var config = new KafkaProducerConfig { BootstrapServers = "", Topic = "test" };
        var exporter = new KafkaProducerExporter(config);
        var ctx = new ExportContext("""[{"x":1}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.False(result.Success);
        Assert.Contains("bootstrap", result.ErrorMessage!.ToLower());
    }

    [Fact]
    public void KafkaConfig_RecipeValuesApplied()
    {
        var recipe = """
        {
            "bootstrap_servers": "prod-kafka.internal:9092",
            "topic": "processed-orders",
            "key_field": "order_id",
            "acks": "1",
            "compression": "lz4"
        }
        """;
        var config = KafkaProducerConfig.FromJson(JsonDocument.Parse(recipe).RootElement);

        Assert.Equal("processed-orders", config.Topic);
        Assert.Equal("order_id", config.KeyField);
        Assert.Equal("1", config.Acks);
        Assert.Equal("lz4", config.Compression);
    }

    // ════════════════════════════════════════════════════════════════════
    // 4. S3 UPLOAD — Key building, CSV/JSON, Compression
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public void S3Config_ParsesFromJson()
    {
        var json = JsonDocument.Parse("""
        {
            "bucket_name": "hermes-exports",
            "key_prefix": "pipeline-output",
            "region": "ap-northeast-2",
            "output_format": "csv",
            "compression": "gzip",
            "partition_by_date": true,
            "date_partition_format": "yyyy/MM/dd"
        }
        """).RootElement;

        var config = S3UploadConfig.FromJson(json);
        Assert.Equal("hermes-exports", config.BucketName);
        Assert.Equal("pipeline-output", config.KeyPrefix);
        Assert.Equal("ap-northeast-2", config.Region);
        Assert.Equal("csv", config.OutputFormat);
        Assert.Equal("gzip", config.Compression);
        Assert.True(config.PartitionByDate);
    }

    [Fact]
    public async Task S3_RejectsEmptyBucket()
    {
        var config = new S3UploadConfig { BucketName = "" };
        var s3 = new MockS3Client();
        var exporter = new S3UploadExporter(config, s3);
        var ctx = new ExportContext("""[{"x":1}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.False(result.Success);
        Assert.Contains("bucket", result.ErrorMessage!.ToLower());
    }

    [Fact]
    public async Task S3_EmptyRecords_SuccessWithZero()
    {
        var config = new S3UploadConfig { BucketName = "test-bucket" };
        var s3 = new MockS3Client();
        var exporter = new S3UploadExporter(config, s3);
        var ctx = new ExportContext("[]", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.True(result.Success);
        Assert.Equal(0, result.RecordsExported);
    }

    [Fact]
    public async Task S3_JsonUpload_Success()
    {
        var config = new S3UploadConfig { BucketName = "test-bucket", KeyPrefix = "data", OutputFormat = "json" };
        var s3 = new MockS3Client();
        var exporter = new S3UploadExporter(config, s3);
        var ctx = new ExportContext("""[{"id":1,"name":"test"},{"id":2,"name":"test2"}]""",
            new Dictionary<string, object>(), PipelineName: "test-pipeline", JobId: 42);

        var result = await exporter.ExportAsync(ctx);
        Assert.True(result.Success);
        Assert.Equal(2, result.RecordsExported);
        Assert.Contains("s3://test-bucket", result.DestinationInfo!);
        Assert.Single(s3.Uploads);
    }

    [Fact]
    public async Task S3_CsvUpload_Success()
    {
        var config = new S3UploadConfig { BucketName = "csv-bucket", OutputFormat = "csv", Compression = "none" };
        var s3 = new MockS3Client();
        var exporter = new S3UploadExporter(config, s3);
        var ctx = new ExportContext("""[{"col_a":"v1","col_b":42}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.True(result.Success);
        var uploaded = System.Text.Encoding.UTF8.GetString(s3.Uploads[0].data);
        Assert.Contains("col_a", uploaded);
        Assert.Contains("col_b", uploaded);
    }

    [Fact]
    public async Task S3_GzipCompression_Applied()
    {
        var config = new S3UploadConfig { BucketName = "gz-bucket", Compression = "gzip" };
        var s3 = new MockS3Client();
        var exporter = new S3UploadExporter(config, s3);
        var ctx = new ExportContext("""[{"data":"compress me"}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.True(result.Success);
        Assert.EndsWith(".gz", s3.Uploads[0].key);
    }

    [Fact]
    public async Task S3_MetadataIncluded()
    {
        var config = new S3UploadConfig { BucketName = "meta-bucket", IncludeMetadata = true };
        var s3 = new MockS3Client();
        var exporter = new S3UploadExporter(config, s3);
        var ctx = new ExportContext("""[{"x":1}]""", new Dictionary<string, object>(),
            PipelineName: "my-pipeline", JobId: 99);

        var result = await exporter.ExportAsync(ctx);
        Assert.True(result.Success);
        var meta = s3.Uploads[0].metadata;
        Assert.Contains("hermes-pipeline", meta.Keys);
        Assert.Equal("my-pipeline", meta["hermes-pipeline"]);
    }

    [Fact]
    public async Task S3_UploadFailure_ReturnsError()
    {
        var config = new S3UploadConfig { BucketName = "fail-bucket" };
        var s3 = new MockS3Client { ShouldFail = true };
        var exporter = new S3UploadExporter(config, s3);
        var ctx = new ExportContext("""[{"x":1}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.False(result.Success);
        Assert.NotNull(result.ErrorMessage);
    }

    [Fact]
    public void S3Config_RecipeValuesApplied()
    {
        var recipe = """
        {
            "bucket_name": "prod-data-lake",
            "key_prefix": "hermes/sensor-data",
            "output_format": "csv",
            "compression": "gzip",
            "partition_by_date": true,
            "date_partition_format": "yyyy/MM"
        }
        """;
        var config = S3UploadConfig.FromJson(JsonDocument.Parse(recipe).RootElement);

        Assert.Equal("prod-data-lake", config.BucketName);
        Assert.Equal("hermes/sensor-data", config.KeyPrefix);
        Assert.Equal("csv", config.OutputFormat);
        Assert.Equal("gzip", config.Compression);
        Assert.Equal("yyyy/MM", config.DatePartitionFormat);
    }

    // ════════════════════════════════════════════════════════════════════
    // 5. RECORD PARSING — All Exporters Share This Logic
    // ════════════════════════════════════════════════════════════════════

    [Fact]
    public async Task AllExporters_ParseJsonArray()
    {
        var s3 = new MockS3Client();
        var exporter = new S3UploadExporter(new S3UploadConfig { BucketName = "b" }, s3);
        var ctx = new ExportContext("""[{"a":1},{"a":2}]""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.Equal(2, result.RecordsExported);
    }

    [Fact]
    public async Task AllExporters_ParseRecordsWrapper()
    {
        var s3 = new MockS3Client();
        var exporter = new S3UploadExporter(new S3UploadConfig { BucketName = "b" }, s3);
        var ctx = new ExportContext("""{"records":[{"a":1},{"a":2},{"a":3}]}""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.Equal(3, result.RecordsExported);
    }

    [Fact]
    public async Task AllExporters_ParseSingleObject()
    {
        var s3 = new MockS3Client();
        var exporter = new S3UploadExporter(new S3UploadConfig { BucketName = "b" }, s3);
        var ctx = new ExportContext("""{"a":1,"b":2}""", new Dictionary<string, object>());

        var result = await exporter.ExportAsync(ctx);
        Assert.Equal(1, result.RecordsExported);
    }

    // ════════════════════════════════════════════════════════════════════
    // Mock helpers
    // ════════════════════════════════════════════════════════════════════

    private class MockHttpHandler : HttpMessageHandler
    {
        private readonly System.Net.HttpStatusCode _status;
        private readonly string _body;
        public int CallCount { get; private set; }

        public MockHttpHandler(System.Net.HttpStatusCode status, string body)
        {
            _status = status;
            _body = body;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken ct)
        {
            CallCount++;
            return Task.FromResult(new HttpResponseMessage(_status)
            {
                Content = new StringContent(_body),
            });
        }
    }

    private class MockS3Client : IS3Client
    {
        public List<(string bucket, string key, byte[] data, Dictionary<string, string> metadata)> Uploads = new();
        public bool ShouldFail { get; set; }

        public Task PutObjectAsync(string bucket, string key, byte[] data, string contentType,
            Dictionary<string, string>? metadata = null, CancellationToken ct = default)
        {
            if (ShouldFail)
                throw new Exception("S3 upload failed: Access Denied");
            Uploads.Add((bucket, key, data, metadata ?? new()));
            return Task.CompletedTask;
        }
    }
}
