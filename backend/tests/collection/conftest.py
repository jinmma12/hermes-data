"""Shared fixtures for data collection test scenarios.

Provides mock implementations for FTP, SFTP, Kafka, REST API, and database
connections, along with filesystem helpers for folder traversal and file
matching tests.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import stat
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


# ---------------------------------------------------------------------------
# Date / time helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def utc_now() -> datetime:
    """Current UTC datetime."""
    return datetime.now(timezone.utc)


@pytest.fixture
def date_folders(tmp_path: Path) -> dict[str, Path]:
    """Create a set of date-named folders for traversal tests.

    Returns a dict mapping folder name to path, e.g.
    {"20260315": Path(...), "20260314": Path(...), ...}
    """
    folders: dict[str, Path] = {}
    base = datetime(2026, 3, 15)
    for i in range(7):
        d = base - timedelta(days=i)
        name = d.strftime("%Y%m%d")
        folder = tmp_path / name
        folder.mkdir()
        folders[name] = folder
    return folders


@pytest.fixture
def nested_date_folders(tmp_path: Path) -> dict[str, Path]:
    """Create yyyy/MM/dd nested folder structure."""
    folders: dict[str, Path] = {}
    for year in [2025, 2026]:
        for month in [1, 6, 12]:
            for day in [1, 15, 28]:
                name = f"{year}/{month:02d}/{day:02d}"
                folder = tmp_path / str(year) / f"{month:02d}" / f"{day:02d}"
                folder.mkdir(parents=True, exist_ok=True)
                folders[name] = folder
    return folders


# ---------------------------------------------------------------------------
# File creation helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def create_file(tmp_path: Path):
    """Factory to create a file with given name, content, and optional mtime."""

    def _create(
        name: str,
        content: str = "test data",
        size: int | None = None,
        mtime: float | None = None,
        parent: Path | None = None,
    ) -> Path:
        base = parent or tmp_path
        filepath = base / name
        filepath.parent.mkdir(parents=True, exist_ok=True)
        if size is not None:
            filepath.write_bytes(b"x" * size)
        else:
            filepath.write_text(content)
        if mtime is not None:
            os.utime(filepath, (mtime, mtime))
        return filepath

    return _create


# ---------------------------------------------------------------------------
# Mock FTP/SFTP
# ---------------------------------------------------------------------------


@dataclass
class MockFTPFile:
    """Represents a file on a mock FTP server."""

    name: str
    size: int = 1024
    content: bytes = b""
    modified: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self) -> None:
        if not self.content:
            self.content = b"x" * self.size


class MockFTPServer:
    """Mock FTP server for testing without network dependencies."""

    def __init__(self) -> None:
        self.connected: bool = False
        self.authenticated: bool = False
        self.host: str = ""
        self.port: int = 21
        self.username: str = ""
        self.passive_mode: bool = True
        self.use_tls: bool = False
        self.files: dict[str, list[MockFTPFile]] = {}
        self.downloads: list[str] = []
        self._connect_error: Exception | None = None
        self._auth_error: Exception | None = None
        self._list_error: Exception | None = None
        self._download_error: Exception | None = None
        self._download_fail_count: int = 0
        self._download_attempts: int = 0
        self._busy: bool = False
        self._timeout_seconds: float = 0
        self._max_connections: int = 10
        self._active_connections: int = 0

    def set_connect_error(self, error: Exception) -> None:
        self._connect_error = error

    def set_auth_error(self, error: Exception) -> None:
        self._auth_error = error

    def set_list_error(self, error: Exception) -> None:
        self._list_error = error

    def set_download_error(self, error: Exception, fail_count: int = 1) -> None:
        self._download_error = error
        self._download_fail_count = fail_count

    def add_files(self, directory: str, files: list[MockFTPFile]) -> None:
        self.files.setdefault(directory, []).extend(files)

    async def connect(self, host: str, port: int = 21) -> None:
        if self._connect_error:
            raise self._connect_error
        if self._active_connections >= self._max_connections:
            raise ConnectionError("Too many connections")
        self.host = host
        self.port = port
        self.connected = True
        self._active_connections += 1

    async def login(self, username: str, password: str) -> None:
        if self._auth_error:
            raise self._auth_error
        if not self.connected:
            raise ConnectionError("Not connected")
        self.username = username
        self.authenticated = True

    async def list_directory(self, path: str) -> list[MockFTPFile]:
        if not self.connected or not self.authenticated:
            raise ConnectionError("Not connected or authenticated")
        if self._list_error:
            raise self._list_error
        return self.files.get(path, [])

    async def download(self, remote_path: str, local_path: str) -> bytes:
        if not self.connected:
            raise ConnectionError("Not connected")
        self._download_attempts += 1
        if self._download_error and self._download_attempts <= self._download_fail_count:
            raise self._download_error
        directory = os.path.dirname(remote_path)
        filename = os.path.basename(remote_path)
        for f in self.files.get(directory, []):
            if f.name == filename:
                self.downloads.append(remote_path)
                return f.content
        raise FileNotFoundError(f"File not found: {remote_path}")

    async def disconnect(self) -> None:
        self.connected = False
        self.authenticated = False
        if self._active_connections > 0:
            self._active_connections -= 1

    def reset_download_attempts(self) -> None:
        self._download_attempts = 0


@pytest.fixture
def mock_ftp_server() -> MockFTPServer:
    """Return a fresh MockFTPServer instance."""
    return MockFTPServer()


class MockSFTPServer(MockFTPServer):
    """Mock SFTP server extending MockFTPServer with key-based auth."""

    def __init__(self) -> None:
        super().__init__()
        self.port = 22
        self.key_file: str | None = None
        self.host_key_verified: bool = False

    async def login_with_key(self, username: str, key_path: str) -> None:
        if self._auth_error:
            raise self._auth_error
        if not self.connected:
            raise ConnectionError("Not connected")
        self.username = username
        self.key_file = key_path
        self.authenticated = True

    async def verify_host_key(self, fingerprint: str) -> bool:
        self.host_key_verified = True
        return True


@pytest.fixture
def mock_sftp_server() -> MockSFTPServer:
    """Return a fresh MockSFTPServer instance."""
    return MockSFTPServer()


# ---------------------------------------------------------------------------
# Mock REST API
# ---------------------------------------------------------------------------


@dataclass
class MockAPIResponse:
    """Mock HTTP response object."""

    status_code: int = 200
    body: str = ""
    headers: dict[str, str] = field(default_factory=dict)
    json_data: Any = None
    raw_bytes: bytes = b""

    @property
    def text(self) -> str:
        return self.body

    def json(self) -> Any:
        if self.json_data is not None:
            return self.json_data
        import json
        return json.loads(self.body)

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP {self.status_code}")


class MockAPIClient:
    """Mock REST API client for testing collection scenarios."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self._responses: list[MockAPIResponse] = []
        self._response_index: int = 0
        self._error: Exception | None = None
        self._error_count: int = 0
        self._request_count: int = 0

    def add_response(self, response: MockAPIResponse) -> None:
        self._responses.append(response)

    def set_error(self, error: Exception, count: int = 1) -> None:
        self._error = error
        self._error_count = count

    async def request(
        self,
        method: str,
        url: str,
        headers: dict[str, str] | None = None,
        body: Any = None,
        timeout: float = 30.0,
    ) -> MockAPIResponse:
        self._request_count += 1
        self.requests.append({
            "method": method,
            "url": url,
            "headers": headers or {},
            "body": body,
            "timestamp": datetime.now(timezone.utc),
        })

        if self._error and self._request_count <= self._error_count:
            raise self._error

        if self._responses:
            idx = min(self._response_index, len(self._responses) - 1)
            self._response_index += 1
            return self._responses[idx]

        return MockAPIResponse(status_code=200, body="{}")


@pytest.fixture
def mock_api_client() -> MockAPIClient:
    """Return a fresh MockAPIClient instance."""
    return MockAPIClient()


# ---------------------------------------------------------------------------
# Mock Kafka
# ---------------------------------------------------------------------------


@dataclass
class MockKafkaMessage:
    """Represents a Kafka message."""

    topic: str
    partition: int = 0
    offset: int = 0
    key: bytes | None = None
    value: bytes = b""
    headers: list[tuple[str, bytes]] = field(default_factory=list)
    timestamp: int = 0

    def __post_init__(self) -> None:
        if self.timestamp == 0:
            self.timestamp = int(time.time() * 1000)


class MockKafkaConsumer:
    """Mock Kafka consumer for testing without a Kafka cluster."""

    def __init__(self) -> None:
        self.connected: bool = False
        self.subscribed_topics: list[str] = []
        self.group_id: str = ""
        self.messages: list[MockKafkaMessage] = []
        self._consumed: list[MockKafkaMessage] = []
        self._committed_offsets: dict[tuple[str, int], int] = {}
        self._connect_error: Exception | None = None
        self._consume_error: Exception | None = None
        self._consume_error_count: int = 0
        self._consume_attempts: int = 0
        self._auto_commit: bool = True
        self._max_poll_records: int = 500
        self._position: int = 0

    def set_connect_error(self, error: Exception) -> None:
        self._connect_error = error

    def set_consume_error(self, error: Exception, count: int = 1) -> None:
        self._consume_error = error
        self._consume_error_count = count

    def add_messages(self, messages: list[MockKafkaMessage]) -> None:
        self.messages.extend(messages)

    async def connect(
        self,
        brokers: list[str],
        group_id: str = "",
        security_protocol: str = "PLAINTEXT",
        **kwargs: Any,
    ) -> None:
        if self._connect_error:
            raise self._connect_error
        self.connected = True
        self.group_id = group_id

    async def subscribe(self, topics: list[str]) -> None:
        if not self.connected:
            raise ConnectionError("Not connected")
        self.subscribed_topics = topics

    async def poll(self, max_records: int | None = None) -> list[MockKafkaMessage]:
        if not self.connected:
            raise ConnectionError("Not connected")
        self._consume_attempts += 1
        if self._consume_error and self._consume_attempts <= self._consume_error_count:
            raise self._consume_error

        limit = max_records or self._max_poll_records
        batch = self.messages[self._position: self._position + limit]
        self._position += len(batch)
        self._consumed.extend(batch)
        return batch

    async def commit(self, offsets: dict[tuple[str, int], int] | None = None) -> None:
        if offsets:
            self._committed_offsets.update(offsets)
        elif self._consumed:
            last = self._consumed[-1]
            self._committed_offsets[(last.topic, last.partition)] = last.offset + 1

    async def seek(self, topic: str, partition: int, offset: int) -> None:
        # Find index matching the offset
        for i, msg in enumerate(self.messages):
            if msg.topic == topic and msg.partition == partition and msg.offset == offset:
                self._position = i
                return

    async def close(self) -> None:
        self.connected = False


@pytest.fixture
def mock_kafka_consumer() -> MockKafkaConsumer:
    """Return a fresh MockKafkaConsumer instance."""
    return MockKafkaConsumer()


# ---------------------------------------------------------------------------
# Mock Database Poller
# ---------------------------------------------------------------------------


@dataclass
class MockDBRow:
    """Represents a database row."""

    data: dict[str, Any]

    def __getitem__(self, key: str) -> Any:
        return self.data[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.data.get(key, default)


class MockDBConnection:
    """Mock database connection for polling tests."""

    def __init__(self) -> None:
        self.connected: bool = False
        self.tables: dict[str, list[MockDBRow]] = {}
        self._connect_error: Exception | None = None
        self._query_error: Exception | None = None
        self._query_timeout: bool = False
        self._queries_executed: list[str] = []
        self._last_poll_value: Any = None

    def set_connect_error(self, error: Exception) -> None:
        self._connect_error = error

    def set_query_error(self, error: Exception) -> None:
        self._query_error = error

    def add_rows(self, table: str, rows: list[dict[str, Any]]) -> None:
        self.tables.setdefault(table, []).extend(MockDBRow(r) for r in rows)

    async def connect(self, connection_string: str = "") -> None:
        if self._connect_error:
            raise self._connect_error
        self.connected = True

    async def execute(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[MockDBRow]:
        if not self.connected:
            raise ConnectionError("Not connected")
        if self._query_error:
            raise self._query_error
        if self._query_timeout:
            raise asyncio.TimeoutError("Query timeout")
        self._queries_executed.append(query)

        # Simple simulation: return all rows from first matching table
        for table_name, rows in self.tables.items():
            if table_name.lower() in query.lower():
                return rows
        return []

    async def close(self) -> None:
        self.connected = False


@pytest.fixture
def mock_db_connection() -> MockDBConnection:
    """Return a fresh MockDBConnection instance."""
    return MockDBConnection()


# ---------------------------------------------------------------------------
# Retry / Circuit Breaker helpers
# ---------------------------------------------------------------------------


class RetryTracker:
    """Tracks retry attempts for resilience testing."""

    def __init__(self) -> None:
        self.attempts: list[float] = []
        self.successes: int = 0
        self.failures: int = 0

    def record_attempt(self) -> None:
        self.attempts.append(time.monotonic())

    def record_success(self) -> None:
        self.successes += 1

    def record_failure(self) -> None:
        self.failures += 1

    @property
    def total_attempts(self) -> int:
        return len(self.attempts)

    @property
    def delays(self) -> list[float]:
        """Return delays between consecutive attempts."""
        if len(self.attempts) < 2:
            return []
        return [
            self.attempts[i] - self.attempts[i - 1]
            for i in range(1, len(self.attempts))
        ]


@pytest.fixture
def retry_tracker() -> RetryTracker:
    """Return a fresh RetryTracker instance."""
    return RetryTracker()


class CircuitBreaker:
    """Simple circuit breaker for testing."""

    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: float = 30.0,
        target_id: str = "default",
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.target_id = target_id
        self.state = self.CLOSED
        self.failure_count = 0
        self.last_failure_time: float = 0
        self.success_count = 0

    def record_success(self) -> None:
        if self.state == self.HALF_OPEN:
            self.state = self.CLOSED
        self.failure_count = 0
        self.success_count += 1

    def record_failure(self) -> None:
        self.failure_count += 1
        self.last_failure_time = time.monotonic()
        if self.failure_count >= self.failure_threshold:
            self.state = self.OPEN

    def allow_request(self) -> bool:
        if self.state == self.CLOSED:
            return True
        if self.state == self.OPEN:
            elapsed = time.monotonic() - self.last_failure_time
            if elapsed >= self.recovery_timeout:
                self.state = self.HALF_OPEN
                return True
            return False
        # HALF_OPEN: allow one probe
        return True

    def reset(self) -> None:
        self.state = self.CLOSED
        self.failure_count = 0
        self.success_count = 0


@pytest.fixture
def circuit_breaker() -> CircuitBreaker:
    """Return a fresh CircuitBreaker instance."""
    return CircuitBreaker(failure_threshold=3, recovery_timeout=1.0)


# ---------------------------------------------------------------------------
# Dead Letter Queue
# ---------------------------------------------------------------------------


@dataclass
class DLQEntry:
    """An entry in the dead letter queue."""

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    original_message: Any = None
    error_message: str = ""
    error_type: str = ""
    source: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    retry_count: int = 0


class DeadLetterQueue:
    """Simple DLQ implementation for testing."""

    def __init__(self) -> None:
        self.entries: list[DLQEntry] = []
        self._discarded: list[DLQEntry] = []

    def add(
        self,
        message: Any,
        error: Exception,
        source: str = "",
    ) -> DLQEntry:
        entry = DLQEntry(
            original_message=message,
            error_message=str(error),
            error_type=type(error).__name__,
            source=source,
        )
        self.entries.append(entry)
        return entry

    def replay(self, entry_id: str) -> DLQEntry | None:
        for entry in self.entries:
            if entry.id == entry_id:
                entry.retry_count += 1
                return entry
        return None

    def discard(self, entry_id: str) -> bool:
        for i, entry in enumerate(self.entries):
            if entry.id == entry_id:
                self._discarded.append(self.entries.pop(i))
                return True
        return False

    @property
    def size(self) -> int:
        return len(self.entries)


@pytest.fixture
def dead_letter_queue() -> DeadLetterQueue:
    """Return a fresh DeadLetterQueue instance."""
    return DeadLetterQueue()


# ---------------------------------------------------------------------------
# Back-pressure controller
# ---------------------------------------------------------------------------


class BackpressureController:
    """Simple back-pressure controller for testing."""

    def __init__(
        self,
        soft_limit: int = 100,
        hard_limit: int = 200,
        pipeline_id: str = "default",
    ) -> None:
        self.soft_limit = soft_limit
        self.hard_limit = hard_limit
        self.pipeline_id = pipeline_id
        self.current_count: int = 0
        self.paused: bool = False
        self.stopped: bool = False
        self.total_processed: int = 0

    def add(self, count: int = 1) -> None:
        self.current_count += count
        if self.current_count >= self.hard_limit:
            self.stopped = True
            self.paused = True
        elif self.current_count >= self.soft_limit:
            self.paused = True

    def drain(self, count: int = 1) -> None:
        self.current_count = max(0, self.current_count - count)
        self.total_processed += count
        if self.current_count < self.soft_limit:
            self.paused = False
            self.stopped = False

    @property
    def can_accept(self) -> bool:
        return not self.stopped

    @property
    def metrics(self) -> dict[str, Any]:
        return {
            "current_count": self.current_count,
            "soft_limit": self.soft_limit,
            "hard_limit": self.hard_limit,
            "paused": self.paused,
            "stopped": self.stopped,
            "total_processed": self.total_processed,
            "utilization_pct": (self.current_count / self.hard_limit) * 100,
        }


@pytest.fixture
def backpressure_controller() -> BackpressureController:
    """Return a fresh BackpressureController instance."""
    return BackpressureController(soft_limit=10, hard_limit=20)
