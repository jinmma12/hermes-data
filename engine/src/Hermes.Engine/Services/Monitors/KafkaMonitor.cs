using Confluent.Kafka;
using Hermes.Engine.Domain;

namespace Hermes.Engine.Services.Monitors;

public class KafkaMonitor : BaseMonitor
{
    private readonly string _topic;
    private readonly IConsumer<string, string> _consumer;

    public KafkaMonitor(string bootstrapServers, string topic, string groupId)
    {
        _topic = topic;
        var config = new ConsumerConfig
        {
            BootstrapServers = bootstrapServers,
            GroupId = groupId,
            AutoOffsetReset = AutoOffsetReset.Latest,
            EnableAutoCommit = true
        };
        _consumer = new ConsumerBuilder<string, string>(config).Build();
        _consumer.Subscribe(topic);
    }

    public override Task<List<MonitorEvent>> PollAsync(CancellationToken ct = default)
    {
        var events = new List<MonitorEvent>();
        // Non-blocking consume with short timeout
        while (true)
        {
            var result = _consumer.Consume(TimeSpan.FromMilliseconds(100));
            if (result == null) break;

            events.Add(new MonitorEvent(
                EventType: "EVENT",
                Key: result.Message.Key ?? result.Offset.Value.ToString(),
                Metadata: new Dictionary<string, object>
                {
                    ["topic"] = _topic,
                    ["partition"] = result.Partition.Value,
                    ["offset"] = result.Offset.Value,
                    ["value"] = result.Message.Value ?? ""
                },
                DetectedAt: DateTimeOffset.UtcNow
            ));
        }
        return Task.FromResult(events);
    }
}
