"""E2E: Stub mode visibility — verify EngineClient stub mode is detectable.

Risk addressed: EngineClient silently falls back to stub mode when gRPC
is unavailable. Operators may think activation/reprocess succeeded when
only a stub response was returned.

These tests verify:
1. Stub mode is detectable via is_connected property
2. Stub responses are clearly marked with status='stub'
3. Callers have enough information to build a health check that surfaces degradation
"""

from __future__ import annotations

import pytest

from vessel import engine_client as engine_client_module


@pytest.mark.asyncio
async def test_stub_mode_detectable_via_is_connected(monkeypatch):
    """EngineClient.is_connected returns False when in stub mode."""
    monkeypatch.setattr(engine_client_module, "_GRPC_AVAILABLE", False)
    client = engine_client_module.EngineClient(host="engine", port=50051)

    await client.connect()

    assert not client.is_connected, (
        "EngineClient must report is_connected=False in stub mode"
    )


@pytest.mark.asyncio
async def test_stub_responses_clearly_marked(monkeypatch):
    """All stub-mode responses must include status='stub' for caller detection."""
    monkeypatch.setattr(engine_client_module, "_GRPC_AVAILABLE", False)
    client = engine_client_module.EngineClient(host="engine", port=50051)
    await client.connect()

    # Every method that talks to the engine must return status='stub'
    result = await client.activate_pipeline("test-pipeline-id")
    assert result["status"] == "stub", "activate_pipeline stub must be detectable"

    result = await client.deactivate_pipeline("test-pipeline-id")
    assert result["status"] == "stub", "deactivate_pipeline stub must be detectable"

    result = await client.reprocess_work_item("test-work-item-id")
    assert result["status"] == "stub", "reprocess_work_item stub must be detectable"

    result = await client.get_engine_status()
    assert result["status"] == "stub", "get_engine_status stub must be detectable"
    assert result["engine"] == "not_connected"

    result = await client.get_pipeline_status("test-pipeline-id")
    assert result["status"] == "stub", "get_pipeline_status stub must be detectable"


@pytest.mark.asyncio
async def test_bulk_reprocess_stub_returns_count(monkeypatch):
    """Bulk reprocess in stub mode returns item count so caller can detect stub."""
    monkeypatch.setattr(engine_client_module, "_GRPC_AVAILABLE", False)
    client = engine_client_module.EngineClient(host="engine", port=50051)
    await client.connect()

    result = await client.bulk_reprocess(
        work_item_ids=["item-1", "item-2", "item-3"],
        requested_by="admin",
    )
    assert result["status"] == "stub"
    assert result["count"] == 3


@pytest.mark.asyncio
async def test_health_check_can_detect_degraded_engine_transport():
    """Verify callers have enough data to build a degradation-aware health check.

    This is NOT a production health endpoint test. It validates the contract
    that EngineClient exposes sufficient state (is_connected + get_engine_status)
    for a health check to surface engine transport degradation.

    A real production health check would:
    1. Call client.is_connected -> False means degraded
    2. Call client.get_engine_status() -> status='stub' means engine unreachable
    3. Surface this in /health as { engine: 'degraded', reason: 'stub_mode' }

    That health endpoint does not exist yet. This test documents the contract
    that makes it implementable.
    """
    client = engine_client_module.EngineClient(host="engine", port=50051)
    # Without calling connect(), client is not connected
    assert not client.is_connected

    status = await client.get_engine_status()

    # Health check building blocks are present
    assert status["status"] == "stub", "Status must indicate stub mode"
    assert status["engine"] == "not_connected", "Engine field must indicate no connection"

    # A health check implementation would use these two signals:
    is_degraded = (not client.is_connected) or (status["status"] == "stub")
    assert is_degraded, "Degradation must be detectable from available client state"
