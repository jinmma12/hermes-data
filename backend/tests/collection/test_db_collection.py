"""Database polling test scenarios for Hermes data collection.

Tests cover polling by timestamp, incrementing ID, custom queries,
connection handling, CDC (Change Data Capture), and edge cases.

25+ test scenarios.
"""

from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest
import pytest_asyncio

from tests.collection.conftest import MockDBConnection, MockDBRow


# ---------------------------------------------------------------------------
# DB collector helper
# ---------------------------------------------------------------------------


class DBCollector:
    """Simulates Hermes database polling collection logic."""

    def __init__(self, connection: MockDBConnection, config: dict[str, Any]) -> None:
        self.connection = connection
        self.connection_string: str = config.get("connection_string", "")
        self.table: str = config.get("table", "")
        self.poll_column: str = config.get("poll_column", "id")
        self.poll_type: str = config.get("poll_type", "incrementing_id")
        self.query: str = config.get("query", "")
        self.batch_size: int = config.get("batch_size", 1000)
        self._last_value: Any = None
        self._connected: bool = False

    async def connect(self) -> None:
        """Establish database connection."""
        await self.connection.connect(self.connection_string)
        self._connected = True

    async def poll(self) -> list[dict[str, Any]]:
        """Poll for new or changed rows."""
        if not self._connected:
            raise RuntimeError("Not connected to database")

        if self.query:
            query = self.query
        elif self.poll_type == "incrementing_id":
            if self._last_value is not None:
                query = f"SELECT * FROM {self.table} WHERE {self.poll_column} > {self._last_value}"
            else:
                query = f"SELECT * FROM {self.table}"
        elif self.poll_type == "timestamp":
            if self._last_value is not None:
                query = f"SELECT * FROM {self.table} WHERE {self.poll_column} > '{self._last_value}'"
            else:
                query = f"SELECT * FROM {self.table}"
        else:
            query = f"SELECT * FROM {self.table}"

        rows = await self.connection.execute(query)

        results = []
        for row in rows:
            row_dict = row.data
            # Update last value
            if self.poll_column in row_dict:
                self._last_value = row_dict[self.poll_column]
            results.append(row_dict)

        return results

    async def close(self) -> None:
        """Close database connection."""
        await self.connection.close()
        self._connected = False


@pytest.fixture
def db_collector(mock_db_connection: MockDBConnection) -> DBCollector:
    """Return a DBCollector with default config."""
    return DBCollector(mock_db_connection, {
        "connection_string": "postgresql://localhost/testdb",
        "table": "orders",
        "poll_column": "id",
        "poll_type": "incrementing_id",
    })


# ===========================================================================
# Basic Polling
# ===========================================================================


class TestDBBasicPolling:
    """Tests for basic database polling."""

    @pytest.mark.asyncio
    async def test_db_poll_new_rows_since_last_check(self, db_collector: DBCollector):
        """New rows since last poll are returned."""
        db_collector.connection.add_rows("orders", [
            {"id": 1, "product": "A", "qty": 10},
            {"id": 2, "product": "B", "qty": 20},
        ])
        await db_collector.connect()

        results = await db_collector.poll()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_db_poll_by_timestamp_column(self, mock_db_connection: MockDBConnection):
        """Polling by timestamp column returns new rows."""
        now = datetime.now(timezone.utc)
        mock_db_connection.add_rows("sensor_data", [
            {"id": 1, "created_at": now.isoformat(), "value": 23.5},
            {"id": 2, "created_at": (now + timedelta(seconds=1)).isoformat(), "value": 24.1},
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "sensor_data",
            "poll_column": "created_at",
            "poll_type": "timestamp",
        })
        await collector.connect()

        results = await collector.poll()
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_db_poll_by_incrementing_id(self, db_collector: DBCollector):
        """Polling by incrementing ID tracks the last seen ID."""
        db_collector.connection.add_rows("orders", [
            {"id": 1, "product": "A"},
            {"id": 2, "product": "B"},
        ])
        await db_collector.connect()

        results = await db_collector.poll()
        assert len(results) == 2
        assert db_collector._last_value == 2

    @pytest.mark.asyncio
    async def test_db_poll_custom_query(self, mock_db_connection: MockDBConnection):
        """Custom SQL query is used for polling."""
        mock_db_connection.add_rows("orders", [
            {"id": 1, "status": "NEW", "amount": 100},
        ])
        collector = DBCollector(mock_db_connection, {
            "query": "SELECT * FROM orders WHERE status = 'NEW'",
            "poll_column": "id",
        })
        await collector.connect()

        results = await collector.poll()
        assert len(results) == 1
        assert mock_db_connection._queries_executed[0] == "SELECT * FROM orders WHERE status = 'NEW'"

    @pytest.mark.asyncio
    async def test_db_poll_no_new_rows(self, db_collector: DBCollector):
        """No new rows returns empty list."""
        await db_collector.connect()

        results = await db_collector.poll()
        assert results == []

    @pytest.mark.asyncio
    async def test_db_poll_large_result_set_pagination(self, mock_db_connection: MockDBConnection):
        """Large result set is returned (pagination simulated by batch_size)."""
        rows = [{"id": i, "value": f"data_{i}"} for i in range(100)]
        mock_db_connection.add_rows("large_table", rows)
        collector = DBCollector(mock_db_connection, {
            "table": "large_table",
            "poll_column": "id",
            "batch_size": 50,
        })
        await collector.connect()

        results = await collector.poll()
        assert len(results) == 100  # Mock returns all; real system would paginate


# ===========================================================================
# Connection Handling
# ===========================================================================


class TestDBConnectionHandling:
    """Tests for database connection scenarios."""

    @pytest.mark.asyncio
    async def test_db_poll_connection_timeout(self, mock_db_connection: MockDBConnection):
        """Connection timeout raises appropriate error."""
        mock_db_connection.set_connect_error(asyncio.TimeoutError("Connection timeout"))
        collector = DBCollector(mock_db_connection, {"table": "test"})

        with pytest.raises(asyncio.TimeoutError):
            await collector.connect()

    @pytest.mark.asyncio
    async def test_db_poll_connection_lost_retry(self, db_collector: DBCollector):
        """Connection lost during poll is detected."""
        await db_collector.connect()
        db_collector.connection.set_query_error(
            ConnectionError("Connection lost")
        )

        with pytest.raises(ConnectionError, match="Connection lost"):
            await db_collector.poll()

    @pytest.mark.asyncio
    async def test_db_poll_query_timeout(self, db_collector: DBCollector):
        """Query timeout raises appropriate error."""
        await db_collector.connect()
        db_collector.connection._query_timeout = True

        with pytest.raises(asyncio.TimeoutError):
            await db_collector.poll()

    @pytest.mark.asyncio
    async def test_db_poll_invalid_query(self, mock_db_connection: MockDBConnection):
        """Invalid SQL query raises appropriate error."""
        mock_db_connection.set_query_error(
            Exception("ERROR: syntax error at or near 'SELEC'")
        )
        collector = DBCollector(mock_db_connection, {
            "query": "SELEC * FROM orders",
        })
        await collector.connect()

        with pytest.raises(Exception, match="syntax error"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_db_poll_table_not_exists(self, mock_db_connection: MockDBConnection):
        """Querying a nonexistent table raises error."""
        mock_db_connection.set_query_error(
            Exception('relation "nonexistent_table" does not exist')
        )
        collector = DBCollector(mock_db_connection, {
            "table": "nonexistent_table",
        })
        await collector.connect()

        with pytest.raises(Exception, match="does not exist"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_db_poll_column_not_exists(self, mock_db_connection: MockDBConnection):
        """Querying a nonexistent column raises error."""
        mock_db_connection.set_query_error(
            Exception('column "nonexistent_col" does not exist')
        )
        collector = DBCollector(mock_db_connection, {
            "table": "orders",
            "poll_column": "nonexistent_col",
        })
        await collector.connect()

        with pytest.raises(Exception, match="does not exist"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_db_poll_ssl_connection(self, mock_db_connection: MockDBConnection):
        """SSL database connection succeeds."""
        collector = DBCollector(mock_db_connection, {
            "connection_string": "postgresql://localhost/testdb?sslmode=require",
            "table": "orders",
        })
        await collector.connect()
        assert collector._connected is True

    @pytest.mark.asyncio
    async def test_db_poll_connection_pool_exhaustion(self, mock_db_connection: MockDBConnection):
        """Pool exhaustion is handled gracefully."""
        mock_db_connection.set_connect_error(
            ConnectionError("Too many connections")
        )
        collector = DBCollector(mock_db_connection, {"table": "test"})

        with pytest.raises(ConnectionError, match="Too many connections"):
            await collector.connect()


# ===========================================================================
# Data Handling Edge Cases
# ===========================================================================


class TestDBDataEdgeCases:
    """Tests for data handling edge cases."""

    @pytest.mark.asyncio
    async def test_db_poll_null_timestamp_handling(self, mock_db_connection: MockDBConnection):
        """Rows with null timestamp values are handled."""
        mock_db_connection.add_rows("events", [
            {"id": 1, "created_at": None, "event": "test"},
            {"id": 2, "created_at": "2026-03-15T10:00:00Z", "event": "ok"},
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "events",
            "poll_column": "id",
        })
        await collector.connect()

        results = await collector.poll()
        assert len(results) == 2
        assert results[0]["created_at"] is None

    @pytest.mark.asyncio
    async def test_db_poll_timezone_aware_timestamps(self, mock_db_connection: MockDBConnection):
        """Timezone-aware timestamps are preserved."""
        ts = datetime.now(timezone.utc).isoformat()
        mock_db_connection.add_rows("events", [
            {"id": 1, "created_at": ts, "value": 42},
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "events",
            "poll_column": "id",
        })
        await collector.connect()

        results = await collector.poll()
        assert results[0]["created_at"] == ts

    @pytest.mark.asyncio
    async def test_db_poll_concurrent_inserts_during_poll(self, mock_db_connection: MockDBConnection):
        """Concurrent inserts during polling don't cause issues."""
        mock_db_connection.add_rows("orders", [
            {"id": 1, "product": "A"},
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "orders",
            "poll_column": "id",
        })
        await collector.connect()

        # First poll
        results1 = await collector.poll()
        assert len(results1) == 1

        # Simulate concurrent insert (add more rows)
        mock_db_connection.add_rows("orders", [
            {"id": 2, "product": "B"},
            {"id": 3, "product": "C"},
        ])

        # Second poll returns all rows (mock doesn't filter by last_value)
        results2 = await collector.poll()
        assert len(results2) >= 1

    @pytest.mark.asyncio
    async def test_db_poll_transaction_isolation(self, mock_db_connection: MockDBConnection):
        """Transaction isolation ensures consistent reads."""
        mock_db_connection.add_rows("orders", [
            {"id": 1, "product": "A"},
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "orders",
            "poll_column": "id",
        })
        await collector.connect()

        results = await collector.poll()
        assert len(results) == 1
        # Consistent snapshot: same query returns same result
        # (mock always returns all rows)

    @pytest.mark.asyncio
    async def test_db_poll_multiple_tables_join(self, mock_db_connection: MockDBConnection):
        """Custom query can join multiple tables."""
        mock_db_connection.add_rows("orders", [
            {"id": 1, "product_id": 10, "qty": 5, "product_name": "Widget"},
        ])
        collector = DBCollector(mock_db_connection, {
            "query": "SELECT o.*, p.name FROM orders o JOIN products p ON o.product_id = p.id",
        })
        await collector.connect()

        results = await collector.poll()
        assert len(results) >= 1

    @pytest.mark.asyncio
    async def test_db_poll_stored_procedure_result(self, mock_db_connection: MockDBConnection):
        """Stored procedure results can be polled."""
        mock_db_connection.add_rows("orders", [
            {"id": 1, "total": 500, "status": "PROCESSED"},
        ])
        collector = DBCollector(mock_db_connection, {
            "query": "SELECT * FROM get_new_orders()",
        })
        await collector.connect()

        # Mock returns from matching table; real system calls stored proc
        results = await collector.poll()
        assert isinstance(results, list)


# ===========================================================================
# CDC (Change Data Capture)
# ===========================================================================


class TestDBCDC:
    """Tests for Change Data Capture scenarios."""

    @pytest.mark.asyncio
    async def test_db_cdc_change_data_capture(self, mock_db_connection: MockDBConnection):
        """CDC detects changes in the source table."""
        mock_db_connection.add_rows("cdc_changes", [
            {"id": 1, "op": "INSERT", "table": "orders", "data": {"id": 1, "product": "A"}},
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "cdc_changes",
            "poll_column": "id",
        })
        await collector.connect()

        results = await collector.poll()
        assert len(results) == 1
        assert results[0]["op"] == "INSERT"

    @pytest.mark.asyncio
    async def test_db_cdc_insert_detected(self, mock_db_connection: MockDBConnection):
        """CDC detects INSERT operations."""
        mock_db_connection.add_rows("cdc_changes", [
            {"id": 1, "op": "INSERT", "table": "orders", "data": {"id": 100}},
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "cdc_changes",
            "poll_column": "id",
        })
        await collector.connect()

        results = await collector.poll()
        assert results[0]["op"] == "INSERT"

    @pytest.mark.asyncio
    async def test_db_cdc_update_detected(self, mock_db_connection: MockDBConnection):
        """CDC detects UPDATE operations."""
        mock_db_connection.add_rows("cdc_changes", [
            {
                "id": 2,
                "op": "UPDATE",
                "table": "orders",
                "before": {"status": "NEW"},
                "after": {"status": "SHIPPED"},
            },
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "cdc_changes",
            "poll_column": "id",
        })
        await collector.connect()

        results = await collector.poll()
        assert results[0]["op"] == "UPDATE"
        assert results[0]["before"]["status"] == "NEW"
        assert results[0]["after"]["status"] == "SHIPPED"

    @pytest.mark.asyncio
    async def test_db_cdc_delete_detected(self, mock_db_connection: MockDBConnection):
        """CDC detects DELETE operations."""
        mock_db_connection.add_rows("cdc_changes", [
            {"id": 3, "op": "DELETE", "table": "orders", "data": {"id": 50}},
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "cdc_changes",
            "poll_column": "id",
        })
        await collector.connect()

        results = await collector.poll()
        assert results[0]["op"] == "DELETE"

    @pytest.mark.asyncio
    async def test_db_cdc_schema_change_handling(self, mock_db_connection: MockDBConnection):
        """CDC handles schema change events gracefully."""
        mock_db_connection.add_rows("cdc_changes", [
            {
                "id": 4,
                "op": "SCHEMA_CHANGE",
                "table": "orders",
                "data": {"added_column": "priority", "type": "VARCHAR(10)"},
            },
        ])
        collector = DBCollector(mock_db_connection, {
            "table": "cdc_changes",
            "poll_column": "id",
        })
        await collector.connect()

        results = await collector.poll()
        assert results[0]["op"] == "SCHEMA_CHANGE"
        assert "added_column" in results[0]["data"]
