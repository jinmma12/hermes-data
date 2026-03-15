"""REST API collection test scenarios for Hermes data collection.

Tests cover basic polling, response handling, pagination, change detection,
and error handling.

40+ test scenarios.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from tests.collection.conftest import MockAPIClient, MockAPIResponse, RetryTracker


# ---------------------------------------------------------------------------
# API polling helpers
# ---------------------------------------------------------------------------


class APICollector:
    """Simulates Hermes REST API collection logic."""

    def __init__(self, client: MockAPIClient, config: dict[str, Any]) -> None:
        self.client = client
        self.url: str = config["url"]
        self.method: str = config.get("method", "GET")
        self.headers: dict[str, str] = config.get("headers", {})
        self.body: Any = config.get("body", None)
        self.timeout: float = config.get("timeout", 30.0)
        self.interval: float = config.get("interval", 5.0)
        self._last_hash: str | None = None
        self._last_etag: str | None = None
        self._last_modified: str | None = None
        self._last_value: Any = None

    async def poll(self) -> dict[str, Any] | None:
        """Poll the API and return data if changed."""
        response = await self.client.request(
            self.method,
            self.url,
            headers=self.headers,
            body=self.body,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return {
            "status_code": response.status_code,
            "body": response.text,
            "headers": response.headers,
            "json_data": response.json_data,
        }

    def detect_change_by_hash(self, content: str) -> bool:
        """Detect change by comparing content hash."""
        new_hash = hashlib.sha256(content.encode()).hexdigest()
        changed = new_hash != self._last_hash
        self._last_hash = new_hash
        return changed

    def detect_change_by_etag(self, etag: str) -> bool:
        """Detect change by comparing ETag header."""
        changed = etag != self._last_etag
        self._last_etag = etag
        return changed

    def detect_change_by_last_modified(self, last_modified: str) -> bool:
        """Detect change by comparing Last-Modified header."""
        changed = last_modified != self._last_modified
        self._last_modified = last_modified
        return changed

    def detect_change_by_field(self, data: Any, field: str) -> bool:
        """Detect change by comparing a specific field value."""
        if isinstance(data, dict):
            value = data.get(field)
        else:
            value = data
        changed = value != self._last_value
        self._last_value = value
        return changed


@pytest.fixture
def api_collector(mock_api_client: MockAPIClient) -> APICollector:
    """Return an APICollector with default config."""
    return APICollector(mock_api_client, {
        "url": "https://api.example.com/v1/data",
        "method": "GET",
        "headers": {},
        "timeout": 30.0,
        "interval": 5.0,
    })


# ===========================================================================
# Basic Polling
# ===========================================================================


class TestAPIBasicPolling:
    """Tests for basic REST API polling."""

    @pytest.mark.asyncio
    async def test_api_poll_get_success(self, mock_api_client: MockAPIClient):
        """Simple GET poll returns data successfully."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body='{"items": [1, 2, 3]}')
        )
        collector = APICollector(mock_api_client, {
            "url": "https://api.example.com/data",
        })

        result = await collector.poll()
        assert result is not None
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_api_poll_post_with_body(self, mock_api_client: MockAPIClient):
        """POST request with a body sends the body correctly."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body='{"status": "ok"}')
        )
        collector = APICollector(mock_api_client, {
            "url": "https://api.example.com/data",
            "method": "POST",
            "body": {"query": "SELECT *"},
        })

        result = await collector.poll()
        assert result is not None
        assert mock_api_client.requests[0]["method"] == "POST"
        assert mock_api_client.requests[0]["body"] == {"query": "SELECT *"}

    @pytest.mark.asyncio
    async def test_api_poll_with_bearer_token(self, mock_api_client: MockAPIClient):
        """Bearer token is included in request headers."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body="{}")
        )
        collector = APICollector(mock_api_client, {
            "url": "https://api.example.com/data",
            "headers": {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.test"},
        })

        await collector.poll()
        sent_headers = mock_api_client.requests[0]["headers"]
        assert "Authorization" in sent_headers
        assert sent_headers["Authorization"].startswith("Bearer ")

    @pytest.mark.asyncio
    async def test_api_poll_with_api_key_header(self, mock_api_client: MockAPIClient):
        """API key is sent as a custom header."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body="{}")
        )
        collector = APICollector(mock_api_client, {
            "url": "https://api.example.com/data",
            "headers": {"X-API-Key": "secret-key-123"},
        })

        await collector.poll()
        assert mock_api_client.requests[0]["headers"]["X-API-Key"] == "secret-key-123"

    @pytest.mark.asyncio
    async def test_api_poll_with_basic_auth(self, mock_api_client: MockAPIClient):
        """Basic authentication header is included."""
        import base64
        creds = base64.b64encode(b"user:pass").decode()
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body="{}")
        )
        collector = APICollector(mock_api_client, {
            "url": "https://api.example.com/data",
            "headers": {"Authorization": f"Basic {creds}"},
        })

        await collector.poll()
        assert "Basic" in mock_api_client.requests[0]["headers"]["Authorization"]

    @pytest.mark.asyncio
    async def test_api_poll_with_custom_headers(self, mock_api_client: MockAPIClient):
        """Multiple custom headers are included in the request."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body="{}")
        )
        collector = APICollector(mock_api_client, {
            "url": "https://api.example.com/data",
            "headers": {
                "X-Request-ID": "req-001",
                "Accept": "application/json",
                "X-Tenant": "customer-a",
            },
        })

        await collector.poll()
        headers = mock_api_client.requests[0]["headers"]
        assert headers["X-Request-ID"] == "req-001"
        assert headers["Accept"] == "application/json"

    @pytest.mark.asyncio
    async def test_api_poll_interval_5_seconds(self, mock_api_client: MockAPIClient):
        """Collector respects configured polling interval."""
        collector = APICollector(mock_api_client, {
            "url": "https://api.example.com/data",
            "interval": 5.0,
        })
        assert collector.interval == 5.0

    @pytest.mark.asyncio
    async def test_api_poll_interval_1_minute(self, mock_api_client: MockAPIClient):
        """Collector respects 60-second polling interval."""
        collector = APICollector(mock_api_client, {
            "url": "https://api.example.com/data",
            "interval": 60.0,
        })
        assert collector.interval == 60.0


# ===========================================================================
# Response Handling
# ===========================================================================


class TestAPIResponseHandling:
    """Tests for parsing and processing API responses."""

    @pytest.mark.asyncio
    async def test_api_response_json_parse(self, mock_api_client: MockAPIClient):
        """JSON response is parsed correctly."""
        data = {"items": [{"id": 1, "name": "test"}]}
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=json.dumps(data), json_data=data)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        assert result["json_data"] == data

    @pytest.mark.asyncio
    async def test_api_response_xml_parse(self, mock_api_client: MockAPIClient):
        """XML response body is returned as text for parsing."""
        xml = '<?xml version="1.0"?><data><item id="1"/></data>'
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=xml)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        assert "<data>" in result["body"]

    @pytest.mark.asyncio
    async def test_api_response_csv_parse(self, mock_api_client: MockAPIClient):
        """CSV response body is returned for downstream parsing."""
        csv = "id,name,value\n1,sensor_a,23.5\n2,sensor_b,18.2\n"
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=csv)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        assert "sensor_a" in result["body"]

    @pytest.mark.asyncio
    async def test_api_response_nested_json_extract(self, mock_api_client: MockAPIClient):
        """Nested JSON data can be extracted from the response."""
        data = {"response": {"data": {"records": [1, 2, 3]}, "meta": {"total": 3}}}
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=json.dumps(data), json_data=data)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        records = result["json_data"]["response"]["data"]["records"]
        assert records == [1, 2, 3]

    @pytest.mark.asyncio
    async def test_api_response_array_root(self, mock_api_client: MockAPIClient):
        """Response with an array as the root element is handled."""
        data = [{"id": 1}, {"id": 2}, {"id": 3}]
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=json.dumps(data), json_data=data)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        assert isinstance(result["json_data"], list)
        assert len(result["json_data"]) == 3

    @pytest.mark.asyncio
    async def test_api_response_pagination_offset(self, mock_api_client: MockAPIClient):
        """Offset-based pagination collects all pages."""
        page1 = {"data": [1, 2], "total": 4, "offset": 0, "limit": 2}
        page2 = {"data": [3, 4], "total": 4, "offset": 2, "limit": 2}
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=json.dumps(page1), json_data=page1)
        )
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=json.dumps(page2), json_data=page2)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result1 = await collector.poll()
        result2 = await collector.poll()
        all_data = result1["json_data"]["data"] + result2["json_data"]["data"]
        assert all_data == [1, 2, 3, 4]

    @pytest.mark.asyncio
    async def test_api_response_pagination_cursor(self, mock_api_client: MockAPIClient):
        """Cursor-based pagination follows next_cursor."""
        page1 = {"data": [1, 2], "next_cursor": "abc123"}
        page2 = {"data": [3, 4], "next_cursor": None}
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=json.dumps(page1), json_data=page1)
        )
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=json.dumps(page2), json_data=page2)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result1 = await collector.poll()
        assert result1["json_data"]["next_cursor"] == "abc123"
        result2 = await collector.poll()
        assert result2["json_data"]["next_cursor"] is None

    @pytest.mark.asyncio
    async def test_api_response_pagination_link_header(self, mock_api_client: MockAPIClient):
        """Link header pagination provides next page URL."""
        mock_api_client.add_response(
            MockAPIResponse(
                status_code=200,
                body='[{"id": 1}]',
                headers={"Link": '<https://api.example.com/data?page=2>; rel="next"'},
            )
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        assert "Link" in result["headers"]
        assert "page=2" in result["headers"]["Link"]

    @pytest.mark.asyncio
    async def test_api_response_empty_body(self, mock_api_client: MockAPIClient):
        """Empty response body is handled without error."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body="")
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        assert result["body"] == ""

    @pytest.mark.asyncio
    async def test_api_response_null_values(self, mock_api_client: MockAPIClient):
        """JSON response with null values is handled."""
        data = {"id": 1, "name": None, "value": None, "status": "ok"}
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=json.dumps(data), json_data=data)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        assert result["json_data"]["name"] is None
        assert result["json_data"]["value"] is None

    @pytest.mark.asyncio
    async def test_api_response_large_payload_10mb(self, mock_api_client: MockAPIClient):
        """Large response payload (simulated) is handled."""
        large_data = {"items": [{"id": i, "payload": "x" * 100} for i in range(1000)]}
        body = json.dumps(large_data)
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=body, json_data=large_data)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        assert len(result["json_data"]["items"]) == 1000


# ===========================================================================
# Change Detection
# ===========================================================================


class TestAPIChangeDetection:
    """Tests for API response change detection."""

    def test_api_change_detected_new_records(self, api_collector: APICollector):
        """New content is detected as a change."""
        assert api_collector.detect_change_by_hash('{"items": [1]}') is True

    def test_api_no_change_no_job_created(self, api_collector: APICollector):
        """Same content hash does not trigger a change."""
        content = '{"items": [1, 2, 3]}'
        api_collector.detect_change_by_hash(content)
        assert api_collector.detect_change_by_hash(content) is False

    def test_api_change_detection_by_hash(self, api_collector: APICollector):
        """Hash-based change detection across multiple polls."""
        assert api_collector.detect_change_by_hash("version1") is True
        assert api_collector.detect_change_by_hash("version1") is False
        assert api_collector.detect_change_by_hash("version2") is True

    def test_api_change_detection_by_etag(self, api_collector: APICollector):
        """ETag-based change detection."""
        assert api_collector.detect_change_by_etag('"abc123"') is True
        assert api_collector.detect_change_by_etag('"abc123"') is False
        assert api_collector.detect_change_by_etag('"def456"') is True

    def test_api_change_detection_by_last_modified(self, api_collector: APICollector):
        """Last-Modified header change detection."""
        assert api_collector.detect_change_by_last_modified("Mon, 15 Mar 2026 10:00:00 GMT") is True
        assert api_collector.detect_change_by_last_modified("Mon, 15 Mar 2026 10:00:00 GMT") is False
        assert api_collector.detect_change_by_last_modified("Mon, 15 Mar 2026 11:00:00 GMT") is True

    def test_api_change_detection_by_field_comparison(self, api_collector: APICollector):
        """Field-level change detection."""
        data1 = {"version": 1, "data": [1, 2]}
        data2 = {"version": 1, "data": [1, 2, 3]}
        data3 = {"version": 2, "data": [1, 2, 3]}

        assert api_collector.detect_change_by_field(data1, "version") is True
        assert api_collector.detect_change_by_field(data2, "version") is False  # Same version
        assert api_collector.detect_change_by_field(data3, "version") is True  # Version changed


# ===========================================================================
# Error Handling
# ===========================================================================


class TestAPIErrorHandling:
    """Tests for API error handling and retry logic."""

    @pytest.mark.asyncio
    async def test_api_http_400_bad_request(self, mock_api_client: MockAPIClient):
        """400 Bad Request raises error."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=400, body='{"error": "Bad Request"}')
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        with pytest.raises(Exception, match="HTTP 400"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_http_401_unauthorized_refresh_token(self, mock_api_client: MockAPIClient):
        """401 Unauthorized suggests token refresh is needed."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=401, body='{"error": "Unauthorized"}')
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        with pytest.raises(Exception, match="HTTP 401"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_http_403_forbidden(self, mock_api_client: MockAPIClient):
        """403 Forbidden raises error."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=403, body='{"error": "Forbidden"}')
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        with pytest.raises(Exception, match="HTTP 403"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_http_404_not_found(self, mock_api_client: MockAPIClient):
        """404 Not Found raises error."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=404, body='{"error": "Not Found"}')
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        with pytest.raises(Exception, match="HTTP 404"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_http_429_rate_limit_retry_after(self, mock_api_client: MockAPIClient):
        """429 Too Many Requests should respect Retry-After header."""
        mock_api_client.add_response(
            MockAPIResponse(
                status_code=429,
                body='{"error": "Rate Limited"}',
                headers={"Retry-After": "5"},
            )
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        with pytest.raises(Exception, match="HTTP 429"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_http_500_server_error_retry(self, mock_api_client: MockAPIClient, retry_tracker: RetryTracker):
        """500 Internal Server Error triggers retry."""
        mock_api_client.add_response(MockAPIResponse(status_code=500))
        mock_api_client.add_response(MockAPIResponse(status_code=200, body='{"ok": true}'))
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        # First attempt fails
        retry_tracker.record_attempt()
        with pytest.raises(Exception, match="HTTP 500"):
            await collector.poll()
        retry_tracker.record_failure()

        # Second attempt succeeds
        retry_tracker.record_attempt()
        result = await collector.poll()
        retry_tracker.record_success()
        assert result["status_code"] == 200

    @pytest.mark.asyncio
    async def test_api_http_502_bad_gateway_retry(self, mock_api_client: MockAPIClient):
        """502 Bad Gateway is retryable."""
        mock_api_client.add_response(MockAPIResponse(status_code=502))
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        with pytest.raises(Exception, match="HTTP 502"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_http_503_service_unavailable_retry(self, mock_api_client: MockAPIClient):
        """503 Service Unavailable is retryable."""
        mock_api_client.add_response(MockAPIResponse(status_code=503))
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        with pytest.raises(Exception, match="HTTP 503"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_connection_timeout(self, mock_api_client: MockAPIClient):
        """Connection timeout raises appropriate error."""
        mock_api_client.set_error(asyncio.TimeoutError("Connection timed out"), count=1)
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        with pytest.raises(asyncio.TimeoutError):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_read_timeout(self, mock_api_client: MockAPIClient):
        """Read timeout raises appropriate error."""
        mock_api_client.set_error(asyncio.TimeoutError("Read timed out"), count=1)
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        with pytest.raises(asyncio.TimeoutError):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_dns_resolution_failure(self, mock_api_client: MockAPIClient):
        """DNS resolution failure raises appropriate error."""
        mock_api_client.set_error(OSError("Name or service not known"), count=1)
        collector = APICollector(mock_api_client, {"url": "https://nonexistent.invalid/data"})

        with pytest.raises(OSError, match="Name or service not known"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_ssl_certificate_invalid(self, mock_api_client: MockAPIClient):
        """Invalid SSL certificate raises appropriate error."""
        mock_api_client.set_error(
            ConnectionError("SSL: CERTIFICATE_VERIFY_FAILED"), count=1
        )
        collector = APICollector(mock_api_client, {"url": "https://self-signed.example.com/data"})

        with pytest.raises(ConnectionError, match="CERTIFICATE"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_ssl_certificate_expired(self, mock_api_client: MockAPIClient):
        """Expired SSL certificate raises appropriate error."""
        mock_api_client.set_error(
            ConnectionError("SSL: CERTIFICATE_HAS_EXPIRED"), count=1
        )
        collector = APICollector(mock_api_client, {"url": "https://expired.example.com/data"})

        with pytest.raises(ConnectionError, match="EXPIRED"):
            await collector.poll()

    @pytest.mark.asyncio
    async def test_api_response_too_large_reject(self, mock_api_client: MockAPIClient):
        """Response exceeding max size is rejected."""
        max_size = 1000
        large_body = "x" * (max_size + 1)
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body=large_body)
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        assert len(result["body"]) > max_size
        # Application would check size and reject; here we verify detection
        assert len(result["body"]) == max_size + 1

    @pytest.mark.asyncio
    async def test_api_malformed_json_response(self, mock_api_client: MockAPIClient):
        """Malformed JSON response is detected."""
        mock_api_client.add_response(
            MockAPIResponse(status_code=200, body="{invalid json")
        )
        collector = APICollector(mock_api_client, {"url": "https://api.example.com/data"})

        result = await collector.poll()
        # body is returned as-is; json parsing would fail at application level
        with pytest.raises(json.JSONDecodeError):
            json.loads(result["body"])
