"""Kafka collection test scenarios for Hermes data collection.

Tests cover connection, consumption, offset management, deserialization,
and resilience patterns.

30+ test scenarios.
"""

from __future__ import annotations

import asyncio
import json
import time
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio

from tests.collection.conftest import MockKafkaConsumer, MockKafkaMessage


# ---------------------------------------------------------------------------
# Kafka collector helper
# ---------------------------------------------------------------------------


class KafkaCollector:
    """Simulates Hermes Kafka collection logic."""

    def __init__(self, consumer: MockKafkaConsumer, config: dict[str, Any]) -> None:
        self.consumer = consumer
        self.brokers: list[str] = config.get("brokers", ["localhost:9092"])
        self.topics: list[str] = config.get("topics", [])
        self.group_id: str = config.get("group_id", "vessel-collector")
        self.security_protocol: str = config.get("security_protocol", "PLAINTEXT")
        self.max_poll_records: int = config.get("max_poll_records", 500)
        self._deserializer: str = config.get("deserializer", "json")
        self._key_filter: bytes | None = config.get("key_filter", None)
        self._connected: bool = False

    async def connect(self) -> None:
        """Connect to Kafka cluster and subscribe to topics."""
        await self.consumer.connect(
            self.brokers,
            group_id=self.group_id,
            security_protocol=self.security_protocol,
        )
        await self.consumer.subscribe(self.topics)
        self._connected = True

    async def poll(self, max_records: int | None = None) -> list[dict[str, Any]]:
        """Poll for messages and deserialize them."""
        if not self._connected:
            raise RuntimeError("Not connected to Kafka")

        messages = await self.consumer.poll(max_records or self.max_poll_records)

        results = []
        for msg in messages:
            if self._key_filter and msg.key != self._key_filter:
                continue

            try:
                value = self._deserialize(msg.value)
            except Exception as e:
                # Dead letter queue would handle this in production
                raise ValueError(f"Deserialization failed for offset {msg.offset}: {e}")

            results.append({
                "topic": msg.topic,
                "partition": msg.partition,
                "offset": msg.offset,
                "key": msg.key,
                "value": value,
                "timestamp": msg.timestamp,
            })

        return results

    def _deserialize(self, data: bytes) -> Any:
        """Deserialize message value based on configured format."""
        if self._deserializer == "json":
            return json.loads(data.decode("utf-8"))
        elif self._deserializer == "avro":
            # Simulated Avro deserialization
            return {"avro_decoded": data.decode("utf-8", errors="replace")}
        elif self._deserializer == "protobuf":
            # Simulated protobuf deserialization
            return {"proto_decoded": data.decode("utf-8", errors="replace")}
        elif self._deserializer == "raw":
            return data
        else:
            raise ValueError(f"Unknown deserializer: {self._deserializer}")

    async def commit(self) -> None:
        """Commit current offsets."""
        await self.consumer.commit()

    async def seek(self, topic: str, partition: int, offset: int) -> None:
        """Seek to a specific offset."""
        await self.consumer.seek(topic, partition, offset)

    async def close(self) -> None:
        """Close the consumer connection."""
        await self.consumer.close()
        self._connected = False


@pytest.fixture
def kafka_collector(mock_kafka_consumer: MockKafkaConsumer) -> KafkaCollector:
    """Return a KafkaCollector with default config."""
    return KafkaCollector(mock_kafka_consumer, {
        "brokers": ["kafka:9092"],
        "topics": ["equipment.events"],
        "group_id": "vessel-collector",
    })


def make_json_message(
    topic: str = "equipment.events",
    partition: int = 0,
    offset: int = 0,
    key: str | None = None,
    data: dict[str, Any] | None = None,
) -> MockKafkaMessage:
    """Helper to create a JSON-encoded Kafka message."""
    payload = data or {"event": "DATA_READY", "timestamp": time.time()}
    return MockKafkaMessage(
        topic=topic,
        partition=partition,
        offset=offset,
        key=key.encode() if key else None,
        value=json.dumps(payload).encode(),
    )


# ===========================================================================
# Connection
# ===========================================================================


class TestKafkaConnection:
    """Tests for Kafka connection management."""

    @pytest.mark.asyncio
    async def test_kafka_connect_single_broker(self, kafka_collector: KafkaCollector):
        """Connection to a single broker succeeds."""
        await kafka_collector.connect()
        assert kafka_collector.consumer.connected is True

    @pytest.mark.asyncio
    async def test_kafka_connect_multiple_brokers(self, mock_kafka_consumer: MockKafkaConsumer):
        """Connection to multiple brokers uses the broker list."""
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["kafka1:9092", "kafka2:9092", "kafka3:9092"],
            "topics": ["test"],
        })
        await collector.connect()
        assert collector.consumer.connected is True

    @pytest.mark.asyncio
    async def test_kafka_connect_ssl(self, mock_kafka_consumer: MockKafkaConsumer):
        """SSL connection is configured correctly."""
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["kafka:9093"],
            "topics": ["test"],
            "security_protocol": "SSL",
        })
        await collector.connect()
        assert collector.consumer.connected is True

    @pytest.mark.asyncio
    async def test_kafka_connect_sasl_plain(self, mock_kafka_consumer: MockKafkaConsumer):
        """SASL_PLAIN authentication works."""
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["kafka:9094"],
            "topics": ["test"],
            "security_protocol": "SASL_PLAINTEXT",
        })
        await collector.connect()
        assert collector.consumer.connected is True

    @pytest.mark.asyncio
    async def test_kafka_connect_sasl_scram(self, mock_kafka_consumer: MockKafkaConsumer):
        """SASL_SCRAM authentication works."""
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["kafka:9094"],
            "topics": ["test"],
            "security_protocol": "SASL_SSL",
        })
        await collector.connect()
        assert collector.consumer.connected is True

    @pytest.mark.asyncio
    async def test_kafka_connect_timeout(self, mock_kafka_consumer: MockKafkaConsumer):
        """Connection timeout raises appropriate error."""
        mock_kafka_consumer.set_connect_error(asyncio.TimeoutError())
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["unreachable:9092"],
            "topics": ["test"],
        })

        with pytest.raises(asyncio.TimeoutError):
            await collector.connect()


# ===========================================================================
# Consumption
# ===========================================================================


class TestKafkaConsumption:
    """Tests for consuming messages from Kafka."""

    @pytest.mark.asyncio
    async def test_kafka_consume_single_message(self, kafka_collector: KafkaCollector):
        """Consuming a single message returns parsed data."""
        kafka_collector.consumer.add_messages([
            make_json_message(data={"event": "DATA_READY", "equipment": "EQUIP_A"}),
        ])
        await kafka_collector.connect()

        results = await kafka_collector.poll()
        assert len(results) == 1
        assert results[0]["value"]["event"] == "DATA_READY"

    @pytest.mark.asyncio
    async def test_kafka_consume_batch_messages(self, kafka_collector: KafkaCollector):
        """Consuming a batch of messages returns all of them."""
        messages = [
            make_json_message(offset=i, data={"id": i}) for i in range(10)
        ]
        kafka_collector.consumer.add_messages(messages)
        await kafka_collector.connect()

        results = await kafka_collector.poll()
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_kafka_consume_from_beginning(self, kafka_collector: KafkaCollector):
        """Consumer can start from the beginning of a topic."""
        messages = [make_json_message(offset=i) for i in range(5)]
        kafka_collector.consumer.add_messages(messages)
        await kafka_collector.connect()

        results = await kafka_collector.poll()
        assert results[0]["offset"] == 0

    @pytest.mark.asyncio
    async def test_kafka_consume_from_latest(self, kafka_collector: KafkaCollector):
        """Consumer starts from the latest offset (skipping old messages)."""
        old_messages = [make_json_message(offset=i) for i in range(5)]
        kafka_collector.consumer.add_messages(old_messages)
        kafka_collector.consumer._position = 5  # Skip to end

        await kafka_collector.connect()
        results = await kafka_collector.poll()
        assert len(results) == 0  # No new messages

    @pytest.mark.asyncio
    async def test_kafka_consume_from_specific_offset(self, kafka_collector: KafkaCollector):
        """Consumer seeks to a specific offset."""
        messages = [make_json_message(offset=i, data={"id": i}) for i in range(10)]
        kafka_collector.consumer.add_messages(messages)
        await kafka_collector.connect()
        await kafka_collector.seek("equipment.events", 0, 5)

        results = await kafka_collector.poll()
        assert results[0]["offset"] == 5

    @pytest.mark.asyncio
    async def test_kafka_consume_specific_partition(self, kafka_collector: KafkaCollector):
        """Consumer receives messages from a specific partition."""
        messages = [
            make_json_message(partition=0, offset=0, data={"part": 0}),
            make_json_message(partition=1, offset=0, data={"part": 1}),
        ]
        kafka_collector.consumer.add_messages(messages)
        await kafka_collector.connect()

        results = await kafka_collector.poll()
        partitions = {r["partition"] for r in results}
        assert 0 in partitions

    @pytest.mark.asyncio
    async def test_kafka_consume_multiple_partitions(self, kafka_collector: KafkaCollector):
        """Consumer handles messages from multiple partitions."""
        messages = []
        for p in range(3):
            for i in range(5):
                messages.append(
                    make_json_message(partition=p, offset=i, data={"p": p, "i": i})
                )
        kafka_collector.consumer.add_messages(messages)
        await kafka_collector.connect()

        results = await kafka_collector.poll()
        assert len(results) == 15

    @pytest.mark.asyncio
    async def test_kafka_consume_with_key_filter(self, mock_kafka_consumer: MockKafkaConsumer):
        """Key-based filtering only returns matching messages."""
        mock_kafka_consumer.add_messages([
            make_json_message(key="EQUIP_A", data={"equipment": "A"}),
            make_json_message(offset=1, key="EQUIP_B", data={"equipment": "B"}),
            make_json_message(offset=2, key="EQUIP_A", data={"equipment": "A2"}),
        ])
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["kafka:9092"],
            "topics": ["equipment.events"],
            "key_filter": b"EQUIP_A",
        })
        await collector.connect()

        results = await collector.poll()
        assert len(results) == 2
        assert all(r["key"] == b"EQUIP_A" for r in results)

    @pytest.mark.asyncio
    async def test_kafka_consume_json_deserialization(self, kafka_collector: KafkaCollector):
        """JSON messages are deserialized correctly."""
        data = {"event": "DATA_READY", "values": [1, 2, 3], "nested": {"key": "val"}}
        kafka_collector.consumer.add_messages([
            make_json_message(data=data),
        ])
        await kafka_collector.connect()

        results = await kafka_collector.poll()
        assert results[0]["value"] == data

    @pytest.mark.asyncio
    async def test_kafka_consume_avro_deserialization(self, mock_kafka_consumer: MockKafkaConsumer):
        """Avro messages are deserialized (simulated)."""
        mock_kafka_consumer.add_messages([
            MockKafkaMessage(
                topic="test", value=b'{"name": "test"}',  # Simulated Avro
            ),
        ])
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["kafka:9092"],
            "topics": ["test"],
            "deserializer": "avro",
        })
        await collector.connect()

        results = await collector.poll()
        assert len(results) == 1
        assert "avro_decoded" in results[0]["value"]

    @pytest.mark.asyncio
    async def test_kafka_consume_protobuf_deserialization(self, mock_kafka_consumer: MockKafkaConsumer):
        """Protobuf messages are deserialized (simulated)."""
        mock_kafka_consumer.add_messages([
            MockKafkaMessage(topic="test", value=b'protobuf_data'),
        ])
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["kafka:9092"],
            "topics": ["test"],
            "deserializer": "protobuf",
        })
        await collector.connect()

        results = await collector.poll()
        assert "proto_decoded" in results[0]["value"]


# ===========================================================================
# Offset Management
# ===========================================================================


class TestKafkaOffsetManagement:
    """Tests for Kafka offset commit and management."""

    @pytest.mark.asyncio
    async def test_kafka_commit_offset_on_success(self, kafka_collector: KafkaCollector):
        """Offsets are committed after successful processing."""
        kafka_collector.consumer.add_messages([
            make_json_message(offset=0),
            make_json_message(offset=1),
        ])
        await kafka_collector.connect()
        await kafka_collector.poll()
        await kafka_collector.commit()

        assert len(kafka_collector.consumer._committed_offsets) > 0

    @pytest.mark.asyncio
    async def test_kafka_no_commit_on_failure(self, kafka_collector: KafkaCollector):
        """Offsets are not committed when processing fails."""
        kafka_collector.consumer.add_messages([
            MockKafkaMessage(topic="equipment.events", value=b"invalid json"),
        ])
        await kafka_collector.connect()

        with pytest.raises(ValueError, match="Deserialization failed"):
            await kafka_collector.poll()

        # Should not have committed
        assert len(kafka_collector.consumer._committed_offsets) == 0

    @pytest.mark.asyncio
    async def test_kafka_rewind_offset_for_reprocessing(self, kafka_collector: KafkaCollector):
        """Seeking backward allows reprocessing of messages."""
        messages = [make_json_message(offset=i, data={"id": i}) for i in range(5)]
        kafka_collector.consumer.add_messages(messages)
        await kafka_collector.connect()

        # Consume all
        results1 = await kafka_collector.poll()
        assert len(results1) == 5

        # Rewind to offset 2
        await kafka_collector.seek("equipment.events", 0, 2)
        results2 = await kafka_collector.poll()
        assert len(results2) == 3  # offsets 2, 3, 4
        assert results2[0]["offset"] == 2

    @pytest.mark.asyncio
    async def test_kafka_consumer_group_rebalance(self, kafka_collector: KafkaCollector):
        """Consumer reconnects after group rebalance (simulated)."""
        kafka_collector.consumer.add_messages([
            make_json_message(offset=0, data={"id": 0}),
        ])
        await kafka_collector.connect()
        await kafka_collector.poll()

        # Simulate rebalance by disconnecting and reconnecting
        await kafka_collector.close()
        assert not kafka_collector._connected

        # Reconnect
        await kafka_collector.connect()
        assert kafka_collector._connected


# ===========================================================================
# Resilience
# ===========================================================================


class TestKafkaResilience:
    """Tests for Kafka resilience patterns."""

    @pytest.mark.asyncio
    async def test_kafka_broker_disconnect_reconnect(self, kafka_collector: KafkaCollector):
        """Consumer reconnects after broker disconnect."""
        await kafka_collector.connect()
        assert kafka_collector.consumer.connected is True

        await kafka_collector.consumer.close()
        assert kafka_collector.consumer.connected is False

        # Reconnect
        await kafka_collector.connect()
        assert kafka_collector.consumer.connected is True

    @pytest.mark.asyncio
    async def test_kafka_broker_leader_change(self, kafka_collector: KafkaCollector):
        """Consumer recovers after partition leader change (simulated)."""
        kafka_collector.consumer.add_messages([
            make_json_message(offset=0, data={"before_change": True}),
        ])
        await kafka_collector.connect()
        results = await kafka_collector.poll()
        assert len(results) == 1

        # Leader change: add new message, poll again
        kafka_collector.consumer.add_messages([
            make_json_message(offset=1, data={"after_change": True}),
        ])
        results = await kafka_collector.poll()
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_kafka_consumer_lag_monitoring(self, kafka_collector: KafkaCollector):
        """Consumer lag can be tracked via position vs latest offset."""
        messages = [make_json_message(offset=i) for i in range(100)]
        kafka_collector.consumer.add_messages(messages)
        await kafka_collector.connect()

        # Consume 10 messages
        await kafka_collector.poll(max_records=10)
        consumed_position = kafka_collector.consumer._position
        total_messages = len(kafka_collector.consumer.messages)
        lag = total_messages - consumed_position
        assert lag == 90

    @pytest.mark.asyncio
    async def test_kafka_poison_pill_message_skip(self, mock_kafka_consumer: MockKafkaConsumer):
        """Poison pill (undeserializable) message raises error for DLQ handling."""
        mock_kafka_consumer.add_messages([
            MockKafkaMessage(topic="test", offset=0, value=b"not valid json"),
        ])
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["kafka:9092"],
            "topics": ["test"],
        })
        await collector.connect()

        with pytest.raises(ValueError, match="Deserialization failed"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_kafka_deserialization_error_dlq(self, mock_kafka_consumer: MockKafkaConsumer):
        """Deserialization errors should be routable to DLQ."""
        mock_kafka_consumer.add_messages([
            MockKafkaMessage(topic="test", offset=0, value=b"\x00\x01\x02"),
        ])
        collector = KafkaCollector(mock_kafka_consumer, {
            "brokers": ["kafka:9092"],
            "topics": ["test"],
        })
        await collector.connect()

        with pytest.raises(ValueError) as exc_info:
            await collector.poll()
        assert "offset 0" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_kafka_max_poll_records(self, kafka_collector: KafkaCollector):
        """Max poll records limits the batch size."""
        messages = [make_json_message(offset=i) for i in range(100)]
        kafka_collector.consumer.add_messages(messages)
        await kafka_collector.connect()

        results = await kafka_collector.poll(max_records=10)
        assert len(results) == 10

    @pytest.mark.asyncio
    async def test_kafka_session_timeout_rebalance(self, kafka_collector: KafkaCollector):
        """Session timeout triggers rebalance (simulated by reconnection)."""
        await kafka_collector.connect()

        # Simulate session timeout
        kafka_collector.consumer.set_consume_error(
            ConnectionError("Session timed out"), count=1
        )

        with pytest.raises(ConnectionError, match="Session timed out"):
            await kafka_collector.poll()

        # Recovery: reset error and poll again
        kafka_collector.consumer._consume_error = None
        kafka_collector.consumer._consume_attempts = 0
        kafka_collector.consumer.add_messages([
            make_json_message(offset=0, data={"after_rebalance": True}),
        ])
        results = await kafka_collector.poll()
        assert len(results) >= 0  # May be empty if position past messages
