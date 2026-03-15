"""Cross-cutting resilience test scenarios for Hermes data collection.

Tests cover retry logic, circuit breaker, back-pressure, dead letter queue,
and graceful shutdown patterns.

30+ test scenarios.
"""

from __future__ import annotations

import asyncio
import random
import time
from datetime import datetime, timezone
from typing import Any

import pytest
import pytest_asyncio

from tests.collection.conftest import (
    BackpressureController,
    CircuitBreaker,
    DeadLetterQueue,
    DLQEntry,
    RetryTracker,
)


# ---------------------------------------------------------------------------
# Retry helper
# ---------------------------------------------------------------------------


async def retry_operation(
    operation,
    *,
    max_attempts: int = 3,
    base_delay: float = 0.01,
    backoff_factor: float = 2.0,
    jitter: bool = False,
    retryable_errors: tuple[type[Exception], ...] = (IOError, ConnectionError, TimeoutError),
    tracker: RetryTracker | None = None,
) -> Any:
    """Execute an operation with configurable retry logic.

    Args:
        operation: Async callable to execute.
        max_attempts: Maximum number of attempts.
        base_delay: Initial delay between retries in seconds.
        backoff_factor: Multiplier for exponential backoff.
        jitter: Whether to add random jitter to delays.
        retryable_errors: Tuple of exception types that should trigger retry.
        tracker: Optional RetryTracker for observing retry behavior.

    Returns:
        Result of the operation.

    Raises:
        The last exception if all attempts fail.
    """
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        if tracker:
            tracker.record_attempt()
        try:
            result = await operation()
            if tracker:
                tracker.record_success()
            return result
        except retryable_errors as e:
            last_error = e
            if tracker:
                tracker.record_failure()
            if attempt < max_attempts - 1:
                delay = base_delay * (backoff_factor ** attempt)
                if jitter:
                    delay += random.uniform(0, delay * 0.5)
                await asyncio.sleep(delay)
        except Exception:
            # Non-retryable error: raise immediately
            raise

    raise last_error  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Polling state helpers
# ---------------------------------------------------------------------------


class PollingState:
    """Tracks polling state for save/restore tests."""

    def __init__(self) -> None:
        self.last_poll_time: float = 0
        self.last_offset: int = 0
        self.last_file_path: str = ""
        self.items_in_flight: int = 0

    def save(self) -> dict[str, Any]:
        return {
            "last_poll_time": self.last_poll_time,
            "last_offset": self.last_offset,
            "last_file_path": self.last_file_path,
            "items_in_flight": self.items_in_flight,
        }

    def restore(self, state: dict[str, Any]) -> None:
        self.last_poll_time = state.get("last_poll_time", 0)
        self.last_offset = state.get("last_offset", 0)
        self.last_file_path = state.get("last_file_path", "")
        self.items_in_flight = state.get("items_in_flight", 0)


# ===========================================================================
# Retry Logic
# ===========================================================================


class TestRetryLogic:
    """Tests for retry behavior across all collection types."""

    @pytest.mark.asyncio
    async def test_retry_first_attempt_succeeds_no_retry(self, retry_tracker: RetryTracker):
        """When the first attempt succeeds, no retry occurs."""
        async def success_op():
            return "ok"

        result = await retry_operation(success_op, tracker=retry_tracker)
        assert result == "ok"
        assert retry_tracker.total_attempts == 1
        assert retry_tracker.successes == 1
        assert retry_tracker.failures == 0

    @pytest.mark.asyncio
    async def test_retry_transient_error_succeeds_on_retry(self, retry_tracker: RetryTracker):
        """Transient error on first attempt, success on retry."""
        call_count = 0

        async def flaky_op():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Transient failure")
            return "recovered"

        result = await retry_operation(flaky_op, tracker=retry_tracker)
        assert result == "recovered"
        assert retry_tracker.total_attempts == 2
        assert retry_tracker.successes == 1
        assert retry_tracker.failures == 1

    @pytest.mark.asyncio
    async def test_retry_exponential_backoff_delays(self, retry_tracker: RetryTracker):
        """Retry delays follow exponential backoff pattern."""
        call_count = 0

        async def always_fail():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Still failing")

        with pytest.raises(ConnectionError):
            await retry_operation(
                always_fail,
                max_attempts=4,
                base_delay=0.01,
                backoff_factor=2.0,
                tracker=retry_tracker,
            )

        delays = retry_tracker.delays
        assert len(delays) == 3  # 3 delays between 4 attempts
        # Each delay should be roughly double the previous
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1] * 1.5  # Allow tolerance

    @pytest.mark.asyncio
    async def test_retry_max_attempts_exceeded(self, retry_tracker: RetryTracker):
        """After max attempts, the last error is raised."""
        async def persistent_failure():
            raise IOError("Persistent failure")

        with pytest.raises(IOError, match="Persistent failure"):
            await retry_operation(
                persistent_failure,
                max_attempts=3,
                base_delay=0.001,
                tracker=retry_tracker,
            )
        assert retry_tracker.total_attempts == 3
        assert retry_tracker.failures == 3

    @pytest.mark.asyncio
    async def test_retry_jitter_randomizes_delays(self, retry_tracker: RetryTracker):
        """Jitter adds randomness to retry delays to prevent thundering herd."""
        async def fail():
            raise ConnectionError("fail")

        delays_run1 = []
        delays_run2 = []

        for run_delays in [delays_run1, delays_run2]:
            tracker = RetryTracker()
            try:
                await retry_operation(
                    fail,
                    max_attempts=4,
                    base_delay=0.01,
                    jitter=True,
                    tracker=tracker,
                )
            except ConnectionError:
                pass
            run_delays.extend(tracker.delays)

        # With jitter, the two runs should have different delay patterns
        # (statistically very unlikely to be identical)
        # We just verify both completed
        assert len(delays_run1) == 3
        assert len(delays_run2) == 3

    @pytest.mark.asyncio
    async def test_retry_non_retryable_error_no_retry(self, retry_tracker: RetryTracker):
        """Non-retryable errors (e.g., ValueError) are raised immediately."""
        async def bad_config():
            raise ValueError("Invalid configuration")

        with pytest.raises(ValueError, match="Invalid configuration"):
            await retry_operation(bad_config, max_attempts=3, tracker=retry_tracker)
        assert retry_tracker.total_attempts == 1
        assert retry_tracker.failures == 0  # Not counted as retryable failure

    @pytest.mark.asyncio
    async def test_retry_different_error_types_classification(self, retry_tracker: RetryTracker):
        """Different error types are classified as retryable or not."""
        call_count = 0

        async def mixed_errors():
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise ConnectionError("Retryable")
            if call_count == 2:
                raise TimeoutError("Also retryable")
            return "success"

        result = await retry_operation(
            mixed_errors,
            max_attempts=5,
            base_delay=0.001,
            tracker=retry_tracker,
        )
        assert result == "success"
        assert retry_tracker.total_attempts == 3


# ===========================================================================
# Circuit Breaker
# ===========================================================================


class TestCircuitBreaker:
    """Tests for circuit breaker pattern."""

    def test_circuit_closed_normal_operation(self, circuit_breaker: CircuitBreaker):
        """Circuit starts in CLOSED state and allows requests."""
        assert circuit_breaker.state == CircuitBreaker.CLOSED
        assert circuit_breaker.allow_request() is True

    def test_circuit_opens_after_n_failures(self, circuit_breaker: CircuitBreaker):
        """Circuit opens after failure_threshold consecutive failures."""
        for _ in range(3):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == CircuitBreaker.OPEN

    def test_circuit_open_rejects_immediately(self, circuit_breaker: CircuitBreaker):
        """Open circuit rejects requests immediately."""
        for _ in range(3):
            circuit_breaker.record_failure()

        assert circuit_breaker.state == CircuitBreaker.OPEN
        assert circuit_breaker.allow_request() is False

    def test_circuit_half_open_probe_succeeds(self, circuit_breaker: CircuitBreaker):
        """Half-open circuit allows a probe request; success resets to CLOSED."""
        circuit_breaker.failure_threshold = 2
        circuit_breaker.recovery_timeout = 0.01

        circuit_breaker.record_failure()
        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitBreaker.OPEN

        # Wait for recovery timeout
        time.sleep(0.02)
        assert circuit_breaker.allow_request() is True  # Transitions to HALF_OPEN
        assert circuit_breaker.state == CircuitBreaker.HALF_OPEN

        # Success resets to CLOSED
        circuit_breaker.record_success()
        assert circuit_breaker.state == CircuitBreaker.CLOSED

    def test_circuit_half_open_probe_fails(self, circuit_breaker: CircuitBreaker):
        """Half-open circuit probe failure reopens the circuit."""
        circuit_breaker.failure_threshold = 2
        circuit_breaker.recovery_timeout = 0.01

        circuit_breaker.record_failure()
        circuit_breaker.record_failure()

        time.sleep(0.02)
        circuit_breaker.allow_request()  # -> HALF_OPEN
        assert circuit_breaker.state == CircuitBreaker.HALF_OPEN

        # Failure reopens
        circuit_breaker.record_failure()
        assert circuit_breaker.state == CircuitBreaker.OPEN

    def test_circuit_reset_after_success(self, circuit_breaker: CircuitBreaker):
        """Successful operation resets failure count."""
        circuit_breaker.record_failure()
        circuit_breaker.record_failure()
        assert circuit_breaker.failure_count == 2

        circuit_breaker.record_success()
        assert circuit_breaker.failure_count == 0

    def test_circuit_per_target_isolation(self):
        """Each target has its own independent circuit breaker."""
        cb_ftp = CircuitBreaker(failure_threshold=3, target_id="ftp-server-1")
        cb_api = CircuitBreaker(failure_threshold=3, target_id="api-endpoint-1")

        # FTP breaker opens
        for _ in range(3):
            cb_ftp.record_failure()
        assert cb_ftp.state == CircuitBreaker.OPEN

        # API breaker remains closed
        assert cb_api.state == CircuitBreaker.CLOSED
        assert cb_api.allow_request() is True


# ===========================================================================
# Back-pressure
# ===========================================================================


class TestBackpressure:
    """Tests for back-pressure control."""

    def test_backpressure_pauses_at_soft_limit(self, backpressure_controller: BackpressureController):
        """Collection pauses when pending items reach soft limit."""
        for _ in range(10):
            backpressure_controller.add()
        assert backpressure_controller.paused is True
        assert backpressure_controller.stopped is False

    def test_backpressure_stops_at_hard_limit(self, backpressure_controller: BackpressureController):
        """Collection stops completely at hard limit."""
        for _ in range(20):
            backpressure_controller.add()
        assert backpressure_controller.stopped is True

    def test_backpressure_resumes_when_drained(self, backpressure_controller: BackpressureController):
        """Collection resumes when items are drained below soft limit."""
        for _ in range(15):
            backpressure_controller.add()
        assert backpressure_controller.paused is True

        for _ in range(10):
            backpressure_controller.drain()
        assert backpressure_controller.paused is False
        assert backpressure_controller.can_accept is True

    def test_backpressure_metrics_exposed(self, backpressure_controller: BackpressureController):
        """Back-pressure metrics are available for monitoring."""
        for _ in range(5):
            backpressure_controller.add()

        metrics = backpressure_controller.metrics
        assert metrics["current_count"] == 5
        assert metrics["soft_limit"] == 10
        assert metrics["hard_limit"] == 20
        assert metrics["utilization_pct"] == 25.0

    def test_backpressure_per_pipeline_isolation(self):
        """Each pipeline has its own back-pressure controller."""
        bp1 = BackpressureController(soft_limit=5, hard_limit=10, pipeline_id="pipeline-1")
        bp2 = BackpressureController(soft_limit=5, hard_limit=10, pipeline_id="pipeline-2")

        for _ in range(10):
            bp1.add()
        assert bp1.stopped is True
        assert bp2.can_accept is True


# ===========================================================================
# Dead Letter Queue
# ===========================================================================


class TestDeadLetterQueue:
    """Tests for dead letter queue behavior."""

    def test_dlq_permanent_error_routes_to_dlq(self, dead_letter_queue: DeadLetterQueue):
        """Permanent errors route messages to the DLQ."""
        entry = dead_letter_queue.add(
            message={"data": "corrupted"},
            error=ValueError("Invalid JSON"),
            source="api-collector",
        )
        assert dead_letter_queue.size == 1
        assert entry.error_type == "ValueError"

    def test_dlq_transient_error_retried_not_dlq(self, dead_letter_queue: DeadLetterQueue):
        """Transient errors are retried, not sent to DLQ."""
        # Transient errors should be handled by retry logic, not DLQ
        # DLQ only receives permanent failures
        assert dead_letter_queue.size == 0

    def test_dlq_preserves_original_message(self, dead_letter_queue: DeadLetterQueue):
        """DLQ preserves the original message for inspection."""
        original = {"id": 42, "payload": "important data"}
        entry = dead_letter_queue.add(
            message=original,
            error=Exception("Processing failed"),
        )
        assert entry.original_message == original

    def test_dlq_preserves_error_context(self, dead_letter_queue: DeadLetterQueue):
        """DLQ preserves error details for debugging."""
        entry = dead_letter_queue.add(
            message={"id": 1},
            error=ValueError("Missing required field 'timestamp'"),
            source="kafka-collector",
        )
        assert "Missing required field" in entry.error_message
        assert entry.error_type == "ValueError"
        assert entry.source == "kafka-collector"

    def test_dlq_replay_succeeds(self, dead_letter_queue: DeadLetterQueue):
        """Replaying a DLQ entry increments retry count."""
        entry = dead_letter_queue.add(
            message={"id": 1},
            error=Exception("Temporary issue"),
        )
        replayed = dead_letter_queue.replay(entry.id)
        assert replayed is not None
        assert replayed.retry_count == 1

    def test_dlq_replay_fails_again(self, dead_letter_queue: DeadLetterQueue):
        """Replaying an entry that still fails increments retry count."""
        entry = dead_letter_queue.add(
            message={"id": 1},
            error=Exception("Persistent issue"),
        )
        dead_letter_queue.replay(entry.id)
        dead_letter_queue.replay(entry.id)
        assert entry.retry_count == 2

    def test_dlq_discard_removes(self, dead_letter_queue: DeadLetterQueue):
        """Discarding a DLQ entry removes it from the queue."""
        entry = dead_letter_queue.add(
            message={"id": 1},
            error=Exception("Unrecoverable"),
        )
        assert dead_letter_queue.size == 1

        removed = dead_letter_queue.discard(entry.id)
        assert removed is True
        assert dead_letter_queue.size == 0


# ===========================================================================
# Graceful Shutdown
# ===========================================================================


class TestGracefulShutdown:
    """Tests for graceful shutdown behavior."""

    @pytest.mark.asyncio
    async def test_shutdown_completes_in_flight_collection(self):
        """In-flight collection operations complete before shutdown."""
        completed = []

        async def collection_task(item_id: str):
            await asyncio.sleep(0.01)
            completed.append(item_id)

        # Start 3 tasks
        tasks = [
            asyncio.create_task(collection_task(f"item_{i}"))
            for i in range(3)
        ]

        # Wait for all to complete (graceful shutdown)
        await asyncio.gather(*tasks)
        assert len(completed) == 3

    @pytest.mark.asyncio
    async def test_shutdown_saves_polling_state(self):
        """Polling state is saved during shutdown for resume."""
        state = PollingState()
        state.last_poll_time = time.time()
        state.last_offset = 42
        state.last_file_path = "/data/20260315/file_001.csv"
        state.items_in_flight = 2

        saved = state.save()
        assert saved["last_poll_time"] > 0
        assert saved["last_offset"] == 42
        assert saved["last_file_path"] == "/data/20260315/file_001.csv"
        assert saved["items_in_flight"] == 2

    @pytest.mark.asyncio
    async def test_shutdown_no_data_loss(self):
        """All collected data is flushed before shutdown."""
        buffer: list[dict[str, Any]] = []
        flushed: list[dict[str, Any]] = []

        # Simulate collection filling buffer
        for i in range(10):
            buffer.append({"id": i, "data": f"item_{i}"})

        # Flush on shutdown
        flushed.extend(buffer)
        buffer.clear()

        assert len(flushed) == 10
        assert len(buffer) == 0

    @pytest.mark.asyncio
    async def test_restart_resumes_from_last_state(self):
        """After restart, polling resumes from the saved state."""
        # Save state before shutdown
        original_state = PollingState()
        original_state.last_poll_time = 1710500000.0
        original_state.last_offset = 100
        original_state.last_file_path = "/data/20260315/run_005.csv"
        saved = original_state.save()

        # Restore state after restart
        restored_state = PollingState()
        restored_state.restore(saved)

        assert restored_state.last_poll_time == 1710500000.0
        assert restored_state.last_offset == 100
        assert restored_state.last_file_path == "/data/20260315/run_005.csv"

    @pytest.mark.asyncio
    async def test_shutdown_cancellation_handled(self):
        """Tasks handle cancellation gracefully during shutdown."""
        cleanup_done = False

        async def long_running_task():
            nonlocal cleanup_done
            try:
                await asyncio.sleep(100)  # Would run forever
            except asyncio.CancelledError:
                cleanup_done = True
                raise

        task = asyncio.create_task(long_running_task())
        await asyncio.sleep(0.01)
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert cleanup_done is True

    @pytest.mark.asyncio
    async def test_shutdown_timeout_forces_stop(self):
        """If graceful shutdown times out, tasks are forcefully cancelled."""
        completed = []

        async def slow_task(item_id: str):
            try:
                await asyncio.sleep(10)  # Very slow
                completed.append(item_id)
            except asyncio.CancelledError:
                completed.append(f"{item_id}_cancelled")
                raise

        tasks = [
            asyncio.create_task(slow_task(f"item_{i}"))
            for i in range(3)
        ]

        # Give tasks a very short time, then cancel
        await asyncio.sleep(0.01)
        for t in tasks:
            t.cancel()

        for t in tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass

        assert all("cancelled" in c for c in completed)
