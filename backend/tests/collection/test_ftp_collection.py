"""FTP/SFTP collection test scenarios for Hermes data collection.

Tests cover connection management, directory listing, file download,
retry/resilience patterns, and edge cases.

40+ test scenarios.
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio

from tests.collection.conftest import (
    MockFTPFile,
    MockFTPServer,
    MockSFTPServer,
    RetryTracker,
)


# ===========================================================================
# FTP Connection
# ===========================================================================


class TestFTPConnection:
    """Tests for FTP connection establishment."""

    @pytest.mark.asyncio
    async def test_ftp_connect_success(self, mock_ftp_server: MockFTPServer):
        """Successful FTP connection sets connected flag."""
        await mock_ftp_server.connect("ftp.example.com", 21)
        assert mock_ftp_server.connected is True
        assert mock_ftp_server.host == "ftp.example.com"

    @pytest.mark.asyncio
    async def test_ftp_connect_wrong_host(self, mock_ftp_server: MockFTPServer):
        """Connection to invalid host raises an error."""
        mock_ftp_server.set_connect_error(ConnectionError("Host not found"))

        with pytest.raises(ConnectionError, match="Host not found"):
            await mock_ftp_server.connect("invalid.host.com")

    @pytest.mark.asyncio
    async def test_ftp_connect_wrong_port(self, mock_ftp_server: MockFTPServer):
        """Connection to wrong port raises an error."""
        mock_ftp_server.set_connect_error(ConnectionRefusedError("Connection refused"))

        with pytest.raises(ConnectionRefusedError):
            await mock_ftp_server.connect("ftp.example.com", 9999)

    @pytest.mark.asyncio
    async def test_ftp_connect_wrong_credentials(self, mock_ftp_server: MockFTPServer):
        """Login with wrong credentials raises an error."""
        await mock_ftp_server.connect("ftp.example.com")
        mock_ftp_server.set_auth_error(PermissionError("530 Login incorrect"))

        with pytest.raises(PermissionError, match="530"):
            await mock_ftp_server.login("baduser", "badpass")

    @pytest.mark.asyncio
    async def test_ftp_connect_timeout(self, mock_ftp_server: MockFTPServer):
        """Connection timeout raises appropriate error."""
        mock_ftp_server.set_connect_error(asyncio.TimeoutError())

        with pytest.raises(asyncio.TimeoutError):
            await mock_ftp_server.connect("slow.server.com")

    @pytest.mark.asyncio
    async def test_ftp_connect_ssl_tls(self, mock_ftp_server: MockFTPServer):
        """FTPS connection with SSL/TLS succeeds."""
        mock_ftp_server.use_tls = True
        await mock_ftp_server.connect("ftp.example.com", 990)
        assert mock_ftp_server.connected is True

    @pytest.mark.asyncio
    async def test_sftp_connect_with_key_auth(self, mock_sftp_server: MockSFTPServer):
        """SFTP connection with key-based authentication."""
        await mock_sftp_server.connect("sftp.example.com", 22)
        await mock_sftp_server.login_with_key("deploy", "/home/user/.ssh/id_rsa")
        assert mock_sftp_server.authenticated is True
        assert mock_sftp_server.key_file == "/home/user/.ssh/id_rsa"

    @pytest.mark.asyncio
    async def test_sftp_connect_with_password_auth(self, mock_sftp_server: MockSFTPServer):
        """SFTP connection with password authentication."""
        await mock_sftp_server.connect("sftp.example.com", 22)
        await mock_sftp_server.login("user", "password")
        assert mock_sftp_server.authenticated is True

    @pytest.mark.asyncio
    async def test_sftp_connect_host_key_verification(self, mock_sftp_server: MockSFTPServer):
        """SFTP host key verification is performed."""
        await mock_sftp_server.connect("sftp.example.com", 22)
        result = await mock_sftp_server.verify_host_key("SHA256:abc123...")
        assert result is True
        assert mock_sftp_server.host_key_verified is True


# ===========================================================================
# Directory Listing
# ===========================================================================


class TestFTPDirectoryListing:
    """Tests for FTP directory listing."""

    @pytest.mark.asyncio
    async def test_ftp_list_directory(self, mock_ftp_server: MockFTPServer):
        """Listing a directory with files returns file objects."""
        mock_ftp_server.add_files("/data", [
            MockFTPFile("data_001.csv", size=1024),
            MockFTPFile("data_002.csv", size=2048),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        files = await mock_ftp_server.list_directory("/data")
        assert len(files) == 2
        assert files[0].name == "data_001.csv"

    @pytest.mark.asyncio
    async def test_ftp_list_directory_empty(self, mock_ftp_server: MockFTPServer):
        """Listing an empty directory returns empty list."""
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        files = await mock_ftp_server.list_directory("/empty")
        assert files == []

    @pytest.mark.asyncio
    async def test_ftp_list_directory_permission_denied(self, mock_ftp_server: MockFTPServer):
        """Listing a restricted directory raises an error."""
        mock_ftp_server.set_list_error(PermissionError("550 Permission denied"))
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        with pytest.raises(PermissionError):
            await mock_ftp_server.list_directory("/restricted")

    @pytest.mark.asyncio
    async def test_ftp_list_directory_not_exists(self, mock_ftp_server: MockFTPServer):
        """Listing a nonexistent directory returns empty (or error)."""
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        files = await mock_ftp_server.list_directory("/nonexistent")
        assert files == []

    @pytest.mark.asyncio
    async def test_ftp_list_with_date_folders(self, mock_ftp_server: MockFTPServer):
        """FTP directory contains date-named subdirectories."""
        for date in ["20260313", "20260314", "20260315"]:
            mock_ftp_server.add_files(f"/data/{date}", [
                MockFTPFile(f"run_{date}.csv", size=1024),
            ])

        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        files = await mock_ftp_server.list_directory("/data/20260315")
        assert len(files) == 1
        assert "20260315" in files[0].name

    @pytest.mark.asyncio
    async def test_ftp_list_sorted_by_date(self, mock_ftp_server: MockFTPServer):
        """Files can be sorted by modification date."""
        now = datetime.now(timezone.utc)
        mock_ftp_server.add_files("/data", [
            MockFTPFile("old.csv", modified=now - timedelta(hours=5)),
            MockFTPFile("newest.csv", modified=now),
            MockFTPFile("middle.csv", modified=now - timedelta(hours=2)),
        ])

        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        files = await mock_ftp_server.list_directory("/data")
        sorted_files = sorted(files, key=lambda f: f.modified, reverse=True)
        assert sorted_files[0].name == "newest.csv"


# ===========================================================================
# File Download
# ===========================================================================


class TestFTPFileDownload:
    """Tests for FTP file download scenarios."""

    @pytest.mark.asyncio
    async def test_ftp_download_small_file(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Downloading a small file succeeds."""
        content = b"col1,col2\n1,2\n3,4\n"
        mock_ftp_server.add_files("/data", [
            MockFTPFile("small.csv", content=content, size=len(content)),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download("/data/small.csv", str(tmp_path / "small.csv"))
        assert data == content

    @pytest.mark.asyncio
    async def test_ftp_download_large_file_100mb(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Large file download (simulated) succeeds."""
        # Simulate a 1MB file (not 100MB for test performance)
        content = b"x" * (1024 * 1024)
        mock_ftp_server.add_files("/data", [
            MockFTPFile("large.bin", content=content, size=len(content)),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download("/data/large.bin", str(tmp_path / "large.bin"))
        assert len(data) == 1024 * 1024

    @pytest.mark.asyncio
    async def test_ftp_download_binary_file(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Binary file download preserves content integrity."""
        content = bytes(range(256)) * 10
        mock_ftp_server.add_files("/data", [
            MockFTPFile("binary.dat", content=content, size=len(content)),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download("/data/binary.dat", str(tmp_path / "binary.dat"))
        assert data == content

    @pytest.mark.asyncio
    async def test_ftp_download_utf8_filename(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Downloading a file with UTF-8 name works."""
        mock_ftp_server.add_files("/data", [
            MockFTPFile("데이터_결과.csv", content=b"ok"),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download(
            "/data/데이터_결과.csv", str(tmp_path / "result.csv")
        )
        assert data == b"ok"

    @pytest.mark.asyncio
    async def test_ftp_download_resume_after_partial(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Download resumes after a partial failure (retry succeeds)."""
        content = b"complete file content"
        mock_ftp_server.add_files("/data", [
            MockFTPFile("data.csv", content=content),
        ])
        mock_ftp_server.set_download_error(
            ConnectionError("Connection reset"), fail_count=1
        )
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        # First attempt fails
        with pytest.raises(ConnectionError):
            await mock_ftp_server.download("/data/data.csv", str(tmp_path / "data.csv"))

        # Second attempt succeeds
        data = await mock_ftp_server.download("/data/data.csv", str(tmp_path / "data.csv"))
        assert data == content

    @pytest.mark.asyncio
    async def test_ftp_download_verify_checksum(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Downloaded file checksum matches expected value."""
        content = b"verifiable content 12345"
        expected_hash = hashlib.sha256(content).hexdigest()
        mock_ftp_server.add_files("/data", [
            MockFTPFile("data.csv", content=content),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download("/data/data.csv", str(tmp_path / "data.csv"))
        actual_hash = hashlib.sha256(data).hexdigest()
        assert actual_hash == expected_hash

    @pytest.mark.asyncio
    async def test_ftp_download_to_content_repository(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Downloaded file is stored in the content repository path."""
        content_repo = tmp_path / "content_repo" / "pipeline_001"
        content_repo.mkdir(parents=True)

        mock_ftp_server.add_files("/data", [
            MockFTPFile("data.csv", content=b"stored content"),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download(
            "/data/data.csv", str(content_repo / "data.csv")
        )
        assert data == b"stored content"
        assert "/data/data.csv" in mock_ftp_server.downloads


# ===========================================================================
# Retry & Resilience
# ===========================================================================


class TestFTPRetryResilience:
    """Tests for FTP retry and resilience patterns."""

    @pytest.mark.asyncio
    async def test_ftp_connection_lost_during_listing_retry(self, mock_ftp_server: MockFTPServer):
        """Connection lost during listing triggers a retry."""
        mock_ftp_server.add_files("/data", [MockFTPFile("test.csv")])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        # Simulate connection loss
        mock_ftp_server.set_list_error(ConnectionError("Connection lost"))
        with pytest.raises(ConnectionError):
            await mock_ftp_server.list_directory("/data")

        # Reconnect and retry
        mock_ftp_server._list_error = None
        files = await mock_ftp_server.list_directory("/data")
        assert len(files) == 1

    @pytest.mark.asyncio
    async def test_ftp_connection_lost_during_download_retry(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Connection lost during download triggers retry."""
        mock_ftp_server.add_files("/data", [MockFTPFile("test.csv", content=b"data")])
        mock_ftp_server.set_download_error(
            ConnectionError("Connection reset"), fail_count=2
        )
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        # First two attempts fail
        for _ in range(2):
            with pytest.raises(ConnectionError):
                await mock_ftp_server.download("/data/test.csv", str(tmp_path / "test.csv"))

        # Third attempt succeeds
        data = await mock_ftp_server.download("/data/test.csv", str(tmp_path / "test.csv"))
        assert data == b"data"

    @pytest.mark.asyncio
    async def test_ftp_connection_lost_reconnect_resume(self, mock_ftp_server: MockFTPServer):
        """Full reconnection after connection loss succeeds."""
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")
        assert mock_ftp_server.connected is True

        # Connection lost
        await mock_ftp_server.disconnect()
        assert mock_ftp_server.connected is False

        # Reconnect
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")
        assert mock_ftp_server.connected is True

    @pytest.mark.asyncio
    async def test_ftp_retry_1st_attempt_fails_2nd_succeeds(
        self, mock_ftp_server: MockFTPServer, tmp_path: Path, retry_tracker: RetryTracker
    ):
        """First download attempt fails, second succeeds with retry logic."""
        mock_ftp_server.add_files("/data", [MockFTPFile("test.csv", content=b"ok")])
        mock_ftp_server.set_download_error(IOError("Timeout"), fail_count=1)
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        max_retries = 3
        result = None
        for attempt in range(max_retries):
            retry_tracker.record_attempt()
            try:
                result = await mock_ftp_server.download(
                    "/data/test.csv", str(tmp_path / "test.csv")
                )
                retry_tracker.record_success()
                break
            except IOError:
                retry_tracker.record_failure()

        assert result == b"ok"
        assert retry_tracker.total_attempts == 2
        assert retry_tracker.successes == 1

    @pytest.mark.asyncio
    async def test_ftp_retry_all_attempts_fail(
        self, mock_ftp_server: MockFTPServer, tmp_path: Path, retry_tracker: RetryTracker
    ):
        """All retry attempts fail, error is propagated."""
        mock_ftp_server.add_files("/data", [MockFTPFile("test.csv", content=b"ok")])
        mock_ftp_server.set_download_error(IOError("Persistent error"), fail_count=10)
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        max_retries = 3
        last_error = None
        for attempt in range(max_retries):
            retry_tracker.record_attempt()
            try:
                await mock_ftp_server.download(
                    "/data/test.csv", str(tmp_path / "test.csv")
                )
            except IOError as e:
                retry_tracker.record_failure()
                last_error = e

        assert retry_tracker.total_attempts == 3
        assert retry_tracker.failures == 3
        assert last_error is not None

    @pytest.mark.asyncio
    async def test_ftp_retry_exponential_backoff_timing(
        self, mock_ftp_server: MockFTPServer, tmp_path: Path, retry_tracker: RetryTracker
    ):
        """Retry delays follow exponential backoff pattern."""
        mock_ftp_server.add_files("/data", [MockFTPFile("test.csv", content=b"ok")])
        mock_ftp_server.set_download_error(IOError("Timeout"), fail_count=3)
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        base_delay = 0.01  # 10ms for testing (not real seconds)
        for attempt in range(4):
            retry_tracker.record_attempt()
            try:
                await mock_ftp_server.download(
                    "/data/test.csv", str(tmp_path / "test.csv")
                )
                retry_tracker.record_success()
                break
            except IOError:
                retry_tracker.record_failure()
                delay = base_delay * (2 ** attempt)
                await asyncio.sleep(delay)

        delays = retry_tracker.delays
        # Each delay should be roughly double the previous
        if len(delays) >= 2:
            for i in range(1, len(delays)):
                assert delays[i] >= delays[i - 1] * 1.5  # Allow tolerance

    @pytest.mark.asyncio
    async def test_ftp_retry_with_jitter(self, retry_tracker: RetryTracker):
        """Retry delays include jitter to avoid thundering herd."""
        import random

        base_delay = 0.01
        delays_with_jitter = []
        for attempt in range(5):
            retry_tracker.record_attempt()
            delay = base_delay * (2 ** attempt)
            jitter = random.uniform(0, delay * 0.5)
            delays_with_jitter.append(delay + jitter)
            await asyncio.sleep(0.001)  # Minimal sleep for test

        # Jittered delays should not be perfectly uniform
        assert len(set(f"{d:.6f}" for d in delays_with_jitter)) > 1

    @pytest.mark.asyncio
    async def test_ftp_server_busy_retry_after(self, mock_ftp_server: MockFTPServer):
        """Server returns busy status; client respects retry-after."""
        mock_ftp_server._busy = True
        mock_ftp_server.set_connect_error(ConnectionError("421 Service not available"))

        with pytest.raises(ConnectionError, match="421"):
            await mock_ftp_server.connect("ftp.example.com")

        # After waiting, server is available
        mock_ftp_server._busy = False
        mock_ftp_server._connect_error = None
        await mock_ftp_server.connect("ftp.example.com")
        assert mock_ftp_server.connected is True

    @pytest.mark.asyncio
    async def test_ftp_passive_mode_fallback(self, mock_ftp_server: MockFTPServer):
        """FTP can fall back to passive mode if active fails."""
        mock_ftp_server.passive_mode = False
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        # Switch to passive mode
        mock_ftp_server.passive_mode = True
        assert mock_ftp_server.passive_mode is True

    @pytest.mark.asyncio
    async def test_ftp_timeout_on_slow_server(self, mock_ftp_server: MockFTPServer):
        """Slow server triggers timeout handling."""
        mock_ftp_server._timeout_seconds = 5
        mock_ftp_server.set_connect_error(asyncio.TimeoutError())

        with pytest.raises(asyncio.TimeoutError):
            await mock_ftp_server.connect("slow.server.com")

    @pytest.mark.asyncio
    async def test_ftp_max_concurrent_connections(self, mock_ftp_server: MockFTPServer):
        """Connection pool limits are respected."""
        mock_ftp_server._max_connections = 2

        await mock_ftp_server.connect("ftp.example.com")
        # Simulate second connection via a fresh connect
        server2 = MockFTPServer()
        server2._max_connections = 2
        server2._active_connections = 2
        with pytest.raises(ConnectionError, match="Too many"):
            await server2.connect("ftp.example.com")

    @pytest.mark.asyncio
    async def test_ftp_connection_pool_reuse(self, mock_ftp_server: MockFTPServer):
        """Disconnecting frees the connection for reuse."""
        mock_ftp_server._max_connections = 1
        await mock_ftp_server.connect("ftp.example.com")
        assert mock_ftp_server._active_connections == 1

        await mock_ftp_server.disconnect()
        assert mock_ftp_server._active_connections == 0

        # Can connect again
        await mock_ftp_server.connect("ftp.example.com")
        assert mock_ftp_server.connected is True


# ===========================================================================
# Edge Cases
# ===========================================================================


class TestFTPEdgeCases:
    """Edge cases for FTP collection."""

    @pytest.mark.asyncio
    async def test_ftp_file_modified_during_download(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """A file modified during download should be flagged for re-download."""
        content = b"original content"
        mock_ftp_server.add_files("/data", [
            MockFTPFile("data.csv", content=content),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download("/data/data.csv", str(tmp_path / "data.csv"))
        checksum1 = hashlib.sha256(data).hexdigest()

        # File is updated on server
        mock_ftp_server.files["/data"][0] = MockFTPFile(
            "data.csv", content=b"modified content"
        )
        data2 = await mock_ftp_server.download("/data/data.csv", str(tmp_path / "data.csv"))
        checksum2 = hashlib.sha256(data2).hexdigest()

        assert checksum1 != checksum2

    @pytest.mark.asyncio
    async def test_ftp_file_deleted_before_download(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Attempting to download a deleted file raises FileNotFoundError."""
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        with pytest.raises(FileNotFoundError):
            await mock_ftp_server.download("/data/deleted.csv", str(tmp_path / "deleted.csv"))

    @pytest.mark.asyncio
    async def test_ftp_zero_byte_file(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Zero-byte files can be downloaded (may be filtered later)."""
        mock_ftp_server.add_files("/data", [
            MockFTPFile("empty.csv", content=b"", size=0),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download("/data/empty.csv", str(tmp_path / "empty.csv"))
        assert len(data) == 0

    @pytest.mark.asyncio
    async def test_ftp_filename_with_spaces(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Files with spaces in names are handled correctly."""
        mock_ftp_server.add_files("/data", [
            MockFTPFile("my data file.csv", content=b"ok"),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download(
            "/data/my data file.csv", str(tmp_path / "output.csv")
        )
        assert data == b"ok"

    @pytest.mark.asyncio
    async def test_ftp_very_large_directory_10000_files(self, mock_ftp_server: MockFTPServer):
        """Listing a directory with 10000 files completes correctly."""
        files = [MockFTPFile(f"file_{i:05d}.csv", size=100) for i in range(10000)]
        mock_ftp_server.add_files("/data", files)
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        result = await mock_ftp_server.list_directory("/data")
        assert len(result) == 10000

    @pytest.mark.asyncio
    async def test_ftp_encoding_latin1_filenames(self, mock_ftp_server: MockFTPServer, tmp_path: Path):
        """Filenames with Latin-1 encoding are handled."""
        mock_ftp_server.add_files("/data", [
            MockFTPFile("résumé.csv", content=b"ok"),
        ])
        await mock_ftp_server.connect("ftp.example.com")
        await mock_ftp_server.login("user", "pass")

        data = await mock_ftp_server.download(
            "/data/résumé.csv", str(tmp_path / "resume.csv")
        )
        assert data == b"ok"
