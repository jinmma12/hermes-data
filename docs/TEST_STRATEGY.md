# Hermes Test Strategy

> Comprehensive test plan informed by research into Airbyte, Dagster, Prefect, n8n, and Redpanda Connect testing patterns, tailored to Hermes's unique features.

---

## 1. Lessons from Open-Source Data Pipeline Projects

### 1.1 Airbyte

- **Connector Development Kit (CDK)** provides a base test class (`SourceAcceptanceTest`) that every connector must pass. Tests are auto-generated from a `acceptance-test-config.yml` declaring expected streams, schemas, and connection specifications.
- **Standard Acceptance Tests (SAT)** run against a real or mocked source and verify: `spec()` returns valid JSON Schema, `check()` succeeds with valid config, `discover()` returns at least one stream, `read()` produces records matching the declared schema.
- **Unit tests** per connector use `conftest.py` with pytest fixtures providing mock HTTP responses (via `responses` or `requests_mock`).
- **Key takeaway for Hermes**: Build a **Plugin Acceptance Test** harness that validates any plugin against the Hermes Plugin Protocol contract automatically.

### 1.2 Dagster

- **Component-based test directories** (`core_tests/`, `asset_defs_tests/`, `execution_tests/`, `storage_tests/`, `daemon_tests/`, `scheduler_tests/`, etc.) rather than strict unit/integration/e2e splits.
- **Direct invocation testing**: ops and assets are called as plain Python functions with a mock `build_op_context()` / `build_asset_context()`. No server required.
- **`dagster._check`**: internal runtime type checking module used pervasively.
- **`environments/`** directory provides per-backend test configurations.
- **Key takeaway for Hermes**: Domain services (PipelineManager, RecipeEngine) should be testable via direct invocation with an injected AsyncSession -- already the case in Hermes's architecture.

### 1.3 Prefect

- **Dual-database testing**: All tests run against both SQLite and PostgreSQL.
- **`conftest.py` fixtures**: `generate_test_database_connection_url` creates worker-specific databases; `safety_check_settings` ensures tests use isolated settings; `reset_registered_blocks` cleans test state.
- **Service filtering**: `--exclude-services`, `--only-service` pytest flags to skip tests requiring Docker, external APIs, etc.
- **Reliability tests**: `engine/reliability/` directory with dedicated long-running and chaos tests.
- **Key takeaway for Hermes**: Build a test database fixture that creates isolated PostgreSQL databases per test session. Add `--slow` / `--integration` markers.

### 1.4 n8n

- **`createMockExecuteFunction` helper**: Factory that generates mock `IExecuteFunctions` for unit testing any node without a running workflow engine. Parameterized by node config and continue-on-fail flag.
- **Workflow JSON fixtures**: Integration tests load workflow JSON files, execute them via a test runner, and assert on output data.
- **Dedicated `packages/testing`** package shares test utilities across the monorepo.
- **Key takeaway for Hermes**: Build a `create_mock_plugin_context()` helper and a workflow-JSON-based scenario runner.

### 1.5 Redpanda Connect (Benthos)

- **`*_test.go` files** co-located with source in each `internal/impl/<component>/` directory.
- **Integration tests** use build tags (`//go:build integration`) and require real services (Kafka, Redis, etc.) via docker-compose.
- **Processor contract tests**: A generic test harness validates that any processor implementation conforms to the expected interface (input batches in, output batches out, proper error propagation).
- **Key takeaway for Hermes**: Co-locate plugin-specific tests with plugin directories. Build a generic processor contract test.

---

## 2. Test Directory Structure

```
backend/
  tests/
    conftest.py                    # Shared fixtures: db session, factories, helpers
    factories.py                   # Factory functions for domain objects
    helpers/
      __init__.py
      db.py                        # Database setup/teardown, test session
      plugin.py                    # Mock plugin helpers, protocol test utilities
      pipeline.py                  # Pipeline + Job builder helpers
      assertions.py                # Custom assertion helpers

    # --- Layer 1: Unit Tests (no DB, no subprocess) ---
    unit/
      __init__.py
      test_plugin_protocol.py      # HermesMessage serialization/deserialization
      test_plugin_registry.py      # PluginManifest parsing, registry CRUD
      test_recipe_diff.py          # RecipeDiff computation (pure logic)
      test_config_validation.py    # JSON Schema validation
      test_models.py               # SQLAlchemy model construction
      test_schemas.py              # Pydantic API schema validation

    # --- Layer 2: Service Tests (async, real DB session) ---
    service/
      __init__.py
      test_recipe_engine.py        # Create/publish/rollback/compare recipes
      test_pipeline_manager.py     # CRUD, validation, activate/deactivate
      test_job_lifecycle.py  # Job state machine transitions
      test_reprocess_engine.py     # Reprocess request workflow
      test_snapshot_service.py     # Execution snapshot capture/restore
      test_dedup_service.py        # Dedup key logic

    # --- Layer 3: Integration Tests (subprocess, real plugins) ---
    integration/
      __init__.py
      test_plugin_executor.py      # Real subprocess execution of test plugins
      test_plugin_acceptance.py    # Generic plugin contract tests
      test_nifi_client.py          # NiFi API integration (mocked HTTP)
      test_monitoring_engine.py    # FileWatcher, APIPoller (temp files, mock server)
      test_pipeline_execution.py   # Full pipeline: detect -> collect -> process -> transfer

    # --- Layer 4: End-to-End Scenario Tests ---
    e2e/
      __init__.py
      test_full_pipeline_flow.py   # API-driven: create pipeline, activate, process items
      test_reprocess_scenario.py   # Reprocess single item, bulk, from step N
      test_recipe_versioning.py    # Create v1, update to v2, rollback to v1, compare
      test_concurrent_pipelines.py # Multiple pipelines processing simultaneously
      test_error_recovery.py       # Plugin crash, timeout, retry behavior
      test_api_endpoints.py        # FastAPI TestClient full CRUD

    # --- Test Plugins (fixtures) ---
    fixtures/
      plugins/
        echo-plugin/
          hermes-plugin.json
          main.py                  # Echoes input as output
        slow-plugin/
          hermes-plugin.json
          main.py                  # Sleeps N seconds (timeout testing)
        error-plugin/
          hermes-plugin.json
          main.py                  # Always returns ERROR
        multi-output-plugin/
          hermes-plugin.json
          main.py                  # Emits multiple OUTPUT messages
        crash-plugin/
          hermes-plugin.json
          main.py                  # Exits with non-zero code
        stateful-plugin/
          hermes-plugin.json
          main.py                  # Tracks invocation count (idempotency testing)
      workflows/
        simple_pipeline.json       # 1 collector + 1 algorithm + 1 transfer
        multi_step.json            # Multiple algorithm steps
        error_pipeline.json        # Pipeline with error-prone step
      nifi/
        mock_responses.py          # Canned NiFi API responses
```

---

## 3. Shared Test Infrastructure

### 3.1 conftest.py -- Core Fixtures

```python
import asyncio
import uuid
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from hermes.domain.models.base import Base


# ---------- Database ----------

@pytest.fixture(scope="session")
def event_loop():
    """Session-scoped event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture(scope="session")
async def engine():
    """Create a test database engine.

    Uses a dedicated test database. Falls back to SQLite for fast local runs,
    but CI runs against PostgreSQL for full fidelity.
    """
    url = os.environ.get(
        "TEST_DATABASE_URL",
        "sqlite+aiosqlite:///./test.db"  # local fast mode
    )
    eng = create_async_engine(url, echo=False)
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield eng
    async with eng.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await eng.dispose()


@pytest_asyncio.fixture
async def db(engine) -> AsyncGenerator[AsyncSession, None]:
    """Per-test database session with automatic rollback."""
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    async with session_factory() as session:
        async with session.begin():
            yield session
            await session.rollback()  # Clean slate per test


# ---------- Plugin Registry ----------

@pytest.fixture
def plugin_registry(tmp_path):
    """Registry pre-loaded with test fixture plugins."""
    from hermes.plugins.registry import PluginRegistry
    registry = PluginRegistry()
    fixtures_dir = Path(__file__).parent / "fixtures" / "plugins"
    registry.discover_plugins(fixtures_dir)
    return registry


# ---------- Factories ----------

@pytest.fixture
def make_pipeline(db):
    """Factory fixture for creating test pipelines with steps."""
    async def _make(name="test-pipeline", steps=None, activate=False):
        from hermes.domain.services.pipeline_manager import PipelineManager
        mgr = PipelineManager(db)
        pipeline = await mgr.create_pipeline(
            name=name, monitoring_type="API_POLL"
        )
        if steps:
            for i, step_cfg in enumerate(steps, 1):
                await mgr.add_step(pipeline.id, **step_cfg, stage_order=i)
        if activate:
            await mgr.activate_pipeline(pipeline.id)
        await db.flush()
        return pipeline
    return _make
```

### 3.2 Factory Functions (factories.py)

```python
"""Object factories for tests. Inspired by Dagster's test helper pattern."""

import uuid
from datetime import datetime, timezone
from typing import Any


def make_job(
    pipeline_instance_id: uuid.UUID | None = None,
    pipeline_activation_id: uuid.UUID | None = None,
    source_key: str = "test-file.csv",
    source_type: str = "FILE",
    dedup_key: str | None = None,
    status: str = "DETECTED",
) -> dict[str, Any]:
    """Return kwargs dict for Job construction."""
    return {
        "pipeline_instance_id": pipeline_instance_id or uuid.uuid4(),
        "pipeline_activation_id": pipeline_activation_id or uuid.uuid4(),
        "source_type": source_type,
        "source_key": source_key,
        "source_metadata": {"size": 1024},
        "dedup_key": dedup_key,
        "status": status,
        "detected_at": datetime.now(timezone.utc),
    }


def make_plugin_manifest(
    name: str = "test-plugin",
    plugin_type: str = "ALGORITHM",
    runtime: str = "python",
    entrypoint: str = "main.py",
    input_schema: dict | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "version": "1.0.0",
        "type": plugin_type,
        "description": f"Test {name}",
        "author": "test",
        "license": "MIT",
        "runtime": runtime,
        "entrypoint": entrypoint,
        "inputSchema": input_schema or {},
    }


def make_recipe_config(
    url: str = "https://api.example.com/data",
    interval_seconds: int = 300,
    **overrides,
) -> dict[str, Any]:
    cfg = {
        "url": url,
        "method": "GET",
        "interval_seconds": interval_seconds,
        "timeout_seconds": 30,
        "auth_type": "NONE",
    }
    cfg.update(overrides)
    return cfg
```

### 3.3 Plugin Test Helpers (helpers/plugin.py)

```python
"""Helpers for testing the Hermes Plugin Protocol.

Inspired by n8n's createMockExecuteFunction and Airbyte's SAT pattern.
"""

import io
import json
from typing import Any

from hermes.plugins.protocol import HermesMessage, PluginProtocol


class MockPluginStream:
    """Simulates a plugin subprocess's stdout for protocol testing.

    Usage:
        stream = MockPluginStream()
        stream.add_output({"key": "value"})
        stream.add_log("Processing started")
        stream.add_done({"records_processed": 1})

        messages = PluginProtocol.read_all_messages(stream.as_readable())
    """

    def __init__(self):
        self._messages: list[HermesMessage] = []

    def add_output(self, data: Any) -> "MockPluginStream":
        self._messages.append(HermesMessage.output(data))
        return self

    def add_log(self, message: str, level: str = "INFO") -> "MockPluginStream":
        self._messages.append(HermesMessage.log(message, level))
        return self

    def add_error(self, message: str, code: str = "TEST_ERROR") -> "MockPluginStream":
        self._messages.append(HermesMessage.error(message, code))
        return self

    def add_status(self, progress: float) -> "MockPluginStream":
        self._messages.append(HermesMessage.status(progress))
        return self

    def add_done(self, summary: dict | None = None) -> "MockPluginStream":
        self._messages.append(HermesMessage.done(summary))
        return self

    def as_readable(self) -> io.StringIO:
        lines = [msg.to_json() + "\n" for msg in self._messages]
        return io.StringIO("".join(lines))


def capture_plugin_stdin(config: dict, input_data: Any) -> str:
    """Generate the stdin content that Hermes Core would send to a plugin."""
    stream = io.StringIO()
    PluginProtocol.send_message(HermesMessage.configure(config), stream)
    PluginProtocol.send_message(HermesMessage.execute(input_data), stream)
    return stream.getvalue()


class PluginAcceptanceChecker:
    """Generic acceptance test for any Hermes plugin.

    Inspired by Airbyte's Standard Acceptance Tests.
    Validates that a plugin:
      1. Responds to CONFIGURE without crashing
      2. Produces at least one OUTPUT or DONE on EXECUTE
      3. Ends with a DONE message
      4. Exits with code 0 on success
      5. Exits with code 2 on bad config
      6. Produces valid JSON in all messages
    """

    def __init__(self, plugin_dir: str, config: dict, input_data: Any = None):
        self.plugin_dir = plugin_dir
        self.config = config
        self.input_data = input_data

    async def run_all(self) -> list[tuple[str, bool, str]]:
        """Run all acceptance checks. Returns list of (check_name, passed, detail)."""
        results = []
        results.append(await self._check_valid_config())
        results.append(await self._check_produces_output())
        results.append(await self._check_done_message())
        results.append(await self._check_exit_code())
        results.append(await self._check_invalid_config())
        return results
```

---

## 4. Test Layers and Patterns

### 4.1 Unit Tests (No I/O, No DB)

**Target**: Pure logic -- protocol serialization, schema validation, diff computation, model construction.

**Pattern**: Direct function calls, no fixtures beyond basic data.

```python
# test_plugin_protocol.py

class TestHermesMessage:
    def test_roundtrip_serialization(self):
        msg = HermesMessage.output({"key": "value"})
        json_str = msg.to_json()
        restored = HermesMessage.from_json(json_str)
        assert restored.type == MessageType.OUTPUT
        assert restored.data["data"] == {"key": "value"}

    def test_rejects_empty_line(self):
        with pytest.raises(ValueError, match="Empty message"):
            HermesMessage.from_json("")

    def test_rejects_missing_type(self):
        with pytest.raises(ValueError, match="missing required 'type'"):
            HermesMessage.from_json('{"data": "no type"}')

    def test_rejects_unknown_type(self):
        with pytest.raises(ValueError, match="Unknown message type"):
            HermesMessage.from_json('{"type": "INVALID"}')

    def test_status_clamps_progress(self):
        msg = HermesMessage.status(1.5)
        assert msg.data["progress"] == 1.0
        msg2 = HermesMessage.status(-0.5)
        assert msg2.data["progress"] == 0.0


# test_plugin_registry.py

class TestPluginManifest:
    def test_from_dict_valid(self, tmp_path):
        data = make_plugin_manifest()
        manifest = PluginManifest.from_dict(data, tmp_path)
        assert manifest.name == "test-plugin"
        assert manifest.type == PluginType.ALGORITHM

    def test_from_dict_missing_field(self, tmp_path):
        data = {"name": "incomplete"}
        with pytest.raises(ValueError, match="missing required fields"):
            PluginManifest.from_dict(data, tmp_path)

    def test_from_dict_invalid_type(self, tmp_path):
        data = make_plugin_manifest(plugin_type="INVALID")
        with pytest.raises(ValueError, match="Invalid plugin type"):
            PluginManifest.from_dict(data, tmp_path)


class TestPluginRegistry:
    def test_discover_plugins(self, plugin_registry):
        assert plugin_registry.count >= 1

    def test_get_plugin_by_type_and_name(self, plugin_registry):
        plugin = plugin_registry.get_plugin("ALGORITHM", "passthrough")
        assert plugin is not None

    def test_list_filtered_by_type(self, plugin_registry):
        collectors = plugin_registry.list_plugins("COLLECTOR")
        assert all(p.type == PluginType.COLLECTOR for p in collectors)

    def test_unregister_plugin(self, plugin_registry):
        initial = plugin_registry.count
        removed = plugin_registry.unregister_plugin("ALGORITHM", "passthrough")
        assert removed is True
        assert plugin_registry.count == initial - 1

    def test_duplicate_registration_warns(self, plugin_registry, caplog):
        manifest = plugin_registry.get_plugin("ALGORITHM", "passthrough")
        plugin_registry.register_plugin(manifest)
        assert "Replacing" in caplog.text


# test_config_validation.py

class TestConfigValidation:
    def test_valid_config(self):
        engine = RecipeEngine.__new__(RecipeEngine)  # no DB needed
        schema = {
            "type": "object",
            "required": ["url"],
            "properties": {"url": {"type": "string", "format": "uri"}}
        }
        result = engine.validate_config({"url": "https://example.com"}, schema)
        assert result.valid is True

    def test_invalid_config_missing_required(self):
        engine = RecipeEngine.__new__(RecipeEngine)
        schema = {"type": "object", "required": ["url"],
                  "properties": {"url": {"type": "string"}}}
        result = engine.validate_config({}, schema)
        assert result.valid is False
        assert any("url" in e for e in result.errors)

    def test_empty_schema_always_valid(self):
        engine = RecipeEngine.__new__(RecipeEngine)
        result = engine.validate_config({"anything": True}, {})
        assert result.valid is True


# test_recipe_diff.py

class TestRecipeDiff:
    def test_diff_added_keys(self):
        # Pure data test -- no DB
        cfg1 = {"url": "https://a.com"}
        cfg2 = {"url": "https://a.com", "interval": 300}
        added = {k: cfg2[k] for k in cfg2 if k not in cfg1}
        assert added == {"interval": 300}

    def test_diff_removed_keys(self):
        cfg1 = {"url": "https://a.com", "interval": 300}
        cfg2 = {"url": "https://a.com"}
        removed = {k: cfg1[k] for k in cfg1 if k not in cfg2}
        assert removed == {"interval": 300}

    def test_diff_changed_keys(self):
        cfg1 = {"url": "https://a.com", "interval": 300}
        cfg2 = {"url": "https://b.com", "interval": 300}
        changed = {k: {"from": cfg1[k], "to": cfg2[k]}
                   for k in cfg1 if k in cfg2 and cfg1[k] != cfg2[k]}
        assert changed == {"url": {"from": "https://a.com", "to": "https://b.com"}}
```

### 4.2 Service Tests (Async + DB Session)

**Target**: Domain services with injected AsyncSession. Tests run against a real database (SQLite for local, PostgreSQL for CI).

**Pattern (inspired by Prefect)**: Each test gets a session wrapped in a transaction that is rolled back after the test.

```python
# test_recipe_engine.py

class TestRecipeEngine:
    async def test_create_first_recipe(self, db, seed_collector_instance):
        """First recipe gets version_no=1."""
        engine = RecipeEngine(db)
        config = make_recipe_config()
        version = await engine.create_recipe(
            "COLLECTOR", seed_collector_instance.id, config,
            change_note="Initial config"
        )
        assert version.version_no == 1
        assert version.config_json == config

    async def test_create_increments_version(self, db, seed_collector_instance):
        engine = RecipeEngine(db)
        v1 = await engine.create_recipe("COLLECTOR", seed_collector_instance.id, {"url": "a"})
        v2 = await engine.create_recipe("COLLECTOR", seed_collector_instance.id, {"url": "b"})
        assert v2.version_no == v1.version_no + 1

    async def test_publish_sets_current(self, db, seed_collector_instance):
        engine = RecipeEngine(db)
        await engine.create_recipe("COLLECTOR", seed_collector_instance.id, {"url": "a"})
        await engine.create_recipe("COLLECTOR", seed_collector_instance.id, {"url": "b"})
        published = await engine.publish_recipe("COLLECTOR", seed_collector_instance.id, 2)
        assert published.is_current is True
        current = await engine.get_current_recipe("COLLECTOR", seed_collector_instance.id)
        assert current.version_no == 2

    async def test_publish_unpublishes_previous(self, db, seed_collector_instance):
        engine = RecipeEngine(db)
        await engine.create_recipe("COLLECTOR", seed_collector_instance.id, {"url": "a"})
        await engine.publish_recipe("COLLECTOR", seed_collector_instance.id, 1)
        await engine.create_recipe("COLLECTOR", seed_collector_instance.id, {"url": "b"})
        await engine.publish_recipe("COLLECTOR", seed_collector_instance.id, 2)
        v1 = await engine.get_recipe_by_version("COLLECTOR", seed_collector_instance.id, 1)
        assert v1.is_current is False

    async def test_rollback_to_previous_version(self, db, seed_collector_instance):
        """Rollback = publish an older version."""
        engine = RecipeEngine(db)
        await engine.create_recipe("COLLECTOR", seed_collector_instance.id, {"url": "a"})
        await engine.create_recipe("COLLECTOR", seed_collector_instance.id, {"url": "b"})
        await engine.publish_recipe("COLLECTOR", seed_collector_instance.id, 2)
        # Rollback
        await engine.publish_recipe("COLLECTOR", seed_collector_instance.id, 1)
        current = await engine.get_current_recipe("COLLECTOR", seed_collector_instance.id)
        assert current.version_no == 1

    async def test_compare_recipes(self, db, seed_collector_instance):
        engine = RecipeEngine(db)
        await engine.create_recipe("COLLECTOR", seed_collector_instance.id,
                                   {"url": "a", "interval": 300})
        await engine.create_recipe("COLLECTOR", seed_collector_instance.id,
                                   {"url": "b", "interval": 300, "timeout": 60})
        diff = await engine.compare_recipes("COLLECTOR", seed_collector_instance.id, 1, 2)
        assert diff.changed == {"url": {"from": "a", "to": "b"}}
        assert diff.added == {"timeout": 60}
        assert diff.removed == {}

    async def test_get_recipe_history(self, db, seed_collector_instance):
        engine = RecipeEngine(db)
        for i in range(5):
            await engine.create_recipe("COLLECTOR", seed_collector_instance.id, {"v": i})
        history = await engine.get_recipe_history("COLLECTOR", seed_collector_instance.id)
        assert len(history) == 5
        assert history[0].version_no == 5  # Descending order

    async def test_unknown_instance_type_raises(self, db):
        engine = RecipeEngine(db)
        with pytest.raises(ValueError, match="Unknown instance_type"):
            await engine.create_recipe("INVALID", uuid.uuid4(), {})


# test_pipeline_manager.py

class TestPipelineManager:
    async def test_create_pipeline(self, db):
        mgr = PipelineManager(db)
        pipeline = await mgr.create_pipeline("Test Pipeline", "API_POLL")
        assert pipeline.status == "DRAFT"
        assert pipeline.name == "Test Pipeline"

    async def test_add_step_auto_order(self, db, seed_instances):
        mgr = PipelineManager(db)
        pipeline = await mgr.create_pipeline("P", "API_POLL")
        s1 = await mgr.add_step(pipeline.id, "COLLECT", "COLLECTOR", seed_instances["collector"].id)
        s2 = await mgr.add_step(pipeline.id, "ALGORITHM", "ALGORITHM", seed_instances["algorithm"].id)
        assert s1.stage_order == 1
        assert s2.stage_order == 2

    async def test_reorder_steps(self, db, seed_instances):
        mgr = PipelineManager(db)
        pipeline = await mgr.create_pipeline("P", "API_POLL")
        s1 = await mgr.add_step(pipeline.id, "COLLECT", "COLLECTOR", seed_instances["collector"].id)
        s2 = await mgr.add_step(pipeline.id, "ALGORITHM", "ALGORITHM", seed_instances["algorithm"].id)
        reordered = await mgr.reorder_steps(pipeline.id, [s2.id, s1.id])
        assert reordered[0].id == s2.id
        assert reordered[0].stage_order == 1

    async def test_validate_empty_pipeline(self, db):
        mgr = PipelineManager(db)
        pipeline = await mgr.create_pipeline("Empty", "API_POLL")
        result = await mgr.validate_pipeline(pipeline.id)
        assert result.valid is False
        assert any("no steps" in i.message for i in result.issues)

    async def test_validate_missing_instance(self, db):
        mgr = PipelineManager(db)
        pipeline = await mgr.create_pipeline("Bad Ref", "API_POLL")
        await mgr.add_step(pipeline.id, "COLLECT", "COLLECTOR", uuid.uuid4())
        result = await mgr.validate_pipeline(pipeline.id)
        assert result.valid is False
        assert any("not found" in i.message for i in result.issues)

    async def test_activate_validates_first(self, db):
        mgr = PipelineManager(db)
        pipeline = await mgr.create_pipeline("No Steps", "API_POLL")
        with pytest.raises(ValueError, match="validation failed"):
            await mgr.activate_pipeline(pipeline.id)

    async def test_activate_deactivate_lifecycle(self, db, seed_valid_pipeline):
        mgr = PipelineManager(db)
        activation = await mgr.activate_pipeline(seed_valid_pipeline.id)
        assert activation.status == "STARTING"
        status = await mgr.get_pipeline_status(seed_valid_pipeline.id)
        assert status.status == "ACTIVE"
        await mgr.deactivate_pipeline(seed_valid_pipeline.id)
        status2 = await mgr.get_pipeline_status(seed_valid_pipeline.id)
        assert status2.status == "PAUSED"


# test_job_lifecycle.py

class TestJobLifecycle:
    """Tests that Job status transitions follow the state machine:
    DETECTED -> QUEUED -> PROCESSING -> COMPLETED | FAILED
    """
    async def test_initial_status_is_detected(self, db, seed_activation):
        item = Job(**make_job(
            pipeline_instance_id=seed_activation.pipeline_instance_id,
            pipeline_activation_id=seed_activation.id,
        ))
        db.add(item)
        await db.flush()
        assert item.status == "DETECTED"

    async def test_execution_creates_step_executions(self, db, seed_job):
        # Verify step execution records are created per pipeline step
        ...

    async def test_completed_item_has_duration(self, db, seed_completed_item):
        assert seed_completed_item.last_completed_at is not None
        exec = seed_completed_item.executions[0]
        assert exec.duration_ms > 0

    async def test_failed_item_has_error(self, db, seed_failed_item):
        exec = seed_failed_item.executions[0]
        step_exec = exec.step_executions[0]
        assert step_exec.error_code is not None
        assert step_exec.error_message is not None
```

### 4.3 Integration Tests

**Target**: Real subprocess execution, file system interaction, HTTP mocking.

```python
# test_plugin_executor.py

class TestPluginExecutor:
    """Integration tests for PluginExecutor using real subprocess calls."""

    async def test_echo_plugin(self, plugin_registry):
        """Echo plugin returns input as output."""
        executor = PluginExecutor(timeout=10)
        plugin = plugin_registry.get_plugin("ALGORITHM", "echo")
        result = await executor.execute(
            plugin=plugin,
            config={},
            input_data={"records": [{"id": 1}]},
        )
        assert result.success is True
        assert result.outputs == [{"records": [{"id": 1}]}]

    async def test_timeout_kills_slow_plugin(self, plugin_registry):
        executor = PluginExecutor(timeout=2)
        plugin = plugin_registry.get_plugin("ALGORITHM", "slow")
        result = await executor.execute(plugin=plugin, config={"sleep": 10})
        assert result.success is False
        assert any(e["code"] == "TIMEOUT" for e in result.errors)

    async def test_crash_plugin_reports_error(self, plugin_registry):
        executor = PluginExecutor(timeout=5)
        plugin = plugin_registry.get_plugin("ALGORITHM", "crash")
        result = await executor.execute(plugin=plugin, config={})
        assert result.success is False
        assert result.exit_code != 0

    async def test_error_plugin_captures_error_messages(self, plugin_registry):
        executor = PluginExecutor(timeout=5)
        plugin = plugin_registry.get_plugin("ALGORITHM", "error")
        result = await executor.execute(plugin=plugin, config={})
        assert result.success is False
        assert len(result.errors) >= 1

    async def test_progress_callback(self, plugin_registry):
        progress_values = []
        async def on_progress(p):
            progress_values.append(p)
        executor = PluginExecutor(timeout=10, on_progress=on_progress)
        plugin = plugin_registry.get_plugin("ALGORITHM", "multi-output")
        await executor.execute(plugin=plugin, config={})
        assert len(progress_values) > 0
        assert all(0.0 <= p <= 1.0 for p in progress_values)

    async def test_unsupported_runtime_raises(self):
        from hermes.plugins.registry import PluginManifest
        manifest = PluginManifest(
            name="bad", version="1.0", type=PluginType.ALGORITHM,
            description="", author="", license="", runtime="ruby",
            entrypoint="main.rb", input_schema={},
        )
        executor = PluginExecutor(timeout=5)
        result = await executor.execute(plugin=manifest, config={})
        assert any("RUNTIME_NOT_FOUND" in e.get("code", "") or
                    "Unsupported" in e.get("message", "")
                    for e in result.errors)


# test_plugin_acceptance.py -- Airbyte SAT-inspired

class TestPluginAcceptance:
    """Generic contract tests that every Hermes plugin must pass.

    These tests are parameterized over all discovered plugins.
    Inspired by Airbyte's Standard Acceptance Tests.
    """

    @pytest.fixture(params=["echo", "multi-output", "passthrough"])
    def plugin_under_test(self, request, plugin_registry):
        return plugin_registry.get_plugin("ALGORITHM", request.param)

    async def test_manifest_has_required_fields(self, plugin_under_test):
        assert plugin_under_test.name
        assert plugin_under_test.version
        assert plugin_under_test.entrypoint

    async def test_entrypoint_exists(self, plugin_under_test):
        assert plugin_under_test.entrypoint_path.exists()

    async def test_responds_to_execute(self, plugin_under_test):
        executor = PluginExecutor(timeout=15)
        result = await executor.execute(
            plugin=plugin_under_test,
            config={},
            input_data={"test": True},
        )
        assert result.exit_code == 0

    async def test_produces_done_message(self, plugin_under_test):
        executor = PluginExecutor(timeout=15)
        result = await executor.execute(
            plugin=plugin_under_test,
            config={},
            input_data={"test": True},
        )
        assert result.summary is not None or result.success


# test_nifi_client.py

class TestNiFiClient:
    """NiFi integration via mocked HTTP.

    Uses httpx mock (respx) to simulate NiFi REST API responses.
    """

    async def test_list_process_groups(self, nifi_client, respx_mock):
        respx_mock.get("/nifi-api/flow/process-groups/root").respond(
            json=MOCK_NIFI_PROCESS_GROUPS
        )
        groups = await nifi_client.list_process_groups()
        assert len(groups) >= 1

    async def test_trigger_process_group(self, nifi_client, respx_mock):
        respx_mock.put("/nifi-api/flow/process-groups/pg-1").respond(200)
        await nifi_client.start_process_group("pg-1")

    async def test_get_process_group_status(self, nifi_client, respx_mock):
        respx_mock.get("/nifi-api/flow/process-groups/pg-1/status").respond(
            json=MOCK_NIFI_STATUS
        )
        status = await nifi_client.get_status("pg-1")
        assert status["aggregateSnapshot"]["bytesIn"] >= 0


# test_monitoring_engine.py

class TestFileWatcher:
    """Test file monitoring with real temporary files."""

    async def test_detects_new_file(self, tmp_path):
        watcher = FileWatcher(watch_dir=str(tmp_path), patterns=["*.csv"])
        # Create a file
        (tmp_path / "data.csv").write_text("a,b,c\n1,2,3")
        events = await watcher.poll()
        assert len(events) == 1
        assert events[0].source_key == "data.csv"

    async def test_ignores_non_matching_pattern(self, tmp_path):
        watcher = FileWatcher(watch_dir=str(tmp_path), patterns=["*.csv"])
        (tmp_path / "readme.txt").write_text("ignore me")
        events = await watcher.poll()
        assert len(events) == 0


class TestAPIPoller:
    """Test API polling with mock HTTP server."""

    async def test_polls_endpoint(self, respx_mock):
        respx_mock.get("https://api.example.com/data").respond(
            json={"items": [{"id": 1}, {"id": 2}]}
        )
        poller = APIPoller(url="https://api.example.com/data",
                          response_data_path="items")
        events = await poller.poll()
        assert len(events) == 2
```

### 4.4 End-to-End Scenario Tests

**Target**: Full system scenarios driven through the FastAPI API layer.

```python
# test_full_pipeline_flow.py

class TestFullPipelineFlow:
    """E2E: Create pipeline via API, activate, inject items, verify completion."""

    async def test_item_tracked_through_full_pipeline(self, async_client, seed_definitions):
        """CRITICAL: Hermes's core differentiator -- every item tracked."""
        # 1. Create instances
        collector = await async_client.post("/api/instances/collector", json={...})
        algorithm = await async_client.post("/api/instances/algorithm", json={...})
        transfer = await async_client.post("/api/instances/transfer", json={...})

        # 2. Create pipeline with steps
        pipeline = await async_client.post("/api/pipelines", json={
            "name": "E2E Test Pipeline",
            "monitoring_type": "API_POLL",
            "steps": [
                {"stage_type": "COLLECT", "ref_type": "COLLECTOR",
                 "ref_id": collector.json()["id"]},
                {"stage_type": "ALGORITHM", "ref_type": "ALGORITHM",
                 "ref_id": algorithm.json()["id"]},
                {"stage_type": "TRANSFER", "ref_type": "TRANSFER",
                 "ref_id": transfer.json()["id"]},
            ]
        })
        pipeline_id = pipeline.json()["id"]

        # 3. Activate
        await async_client.post(f"/api/pipelines/{pipeline_id}/activate")

        # 4. Inject/detect a work item
        # (simulate monitoring engine detecting a new item)

        # 5. Verify Job transitions: DETECTED -> PROCESSING -> COMPLETED
        # 6. Verify step executions created for each step
        # 7. Verify execution snapshot captured
        # 8. Verify event logs recorded

    async def test_dedup_prevents_duplicate(self, async_client, seed_active_pipeline):
        """Same dedup_key should not create a second Job."""
        item1 = await inject_job(seed_active_pipeline, dedup_key="order-123")
        item2 = await inject_job(seed_active_pipeline, dedup_key="order-123")
        # item2 should be rejected or merged
        items = await async_client.get(
            f"/api/pipelines/{seed_active_pipeline.id}/jobs"
        )
        assert len(items.json()) == 1


# test_reprocess_scenario.py

class TestReprocessScenario:
    async def test_reprocess_single_item(self, async_client, seed_completed_item):
        """Reprocess a completed item from the beginning."""
        resp = await async_client.post(
            f"/api/jobs/{seed_completed_item.id}/reprocess",
            json={"requested_by": "operator", "reason": "Config changed"}
        )
        assert resp.status_code == 201
        # Verify new execution created
        item = await async_client.get(f"/api/jobs/{seed_completed_item.id}")
        assert item.json()["execution_count"] == 2

    async def test_reprocess_from_specific_step(self, async_client, seed_completed_item):
        """Reprocess starting from step 2 (skip collector)."""
        resp = await async_client.post(
            f"/api/jobs/{seed_completed_item.id}/reprocess",
            json={"requested_by": "operator", "start_from_step": 2}
        )
        assert resp.status_code == 201
        # Verify step 1 was SKIPPED, step 2+ were RUNNING

    async def test_reprocess_with_latest_recipe(self, async_client, seed_completed_item):
        """Reprocess using the latest recipe version (not the one used originally)."""
        # Update the recipe
        await update_recipe(seed_completed_item.pipeline_id, {"new_param": "value"})
        resp = await async_client.post(
            f"/api/jobs/{seed_completed_item.id}/reprocess",
            json={"requested_by": "operator", "use_latest_recipe": True}
        )
        # Verify new execution snapshot has the updated recipe

    async def test_bulk_reprocess_failed_items(self, async_client, seed_multiple_failed_items):
        """Reprocess all failed items in one batch."""
        resp = await async_client.post(
            f"/api/pipelines/{pipeline_id}/reprocess-failed",
            json={"requested_by": "operator"}
        )
        assert resp.json()["reprocessed_count"] == len(seed_multiple_failed_items)


# test_recipe_versioning.py

class TestRecipeVersioningE2E:
    async def test_version_history_via_api(self, async_client, seed_collector_instance):
        # Create v1
        await async_client.post(f"/api/recipes/COLLECTOR/{inst_id}",
                                json={"config": {"url": "https://a.com"}, "note": "v1"})
        # Create v2
        await async_client.post(f"/api/recipes/COLLECTOR/{inst_id}",
                                json={"config": {"url": "https://b.com"}, "note": "v2"})
        # Get history
        resp = await async_client.get(f"/api/recipes/COLLECTOR/{inst_id}/history")
        assert len(resp.json()) == 2

        # Diff
        diff = await async_client.get(
            f"/api/recipes/COLLECTOR/{inst_id}/diff?v1=1&v2=2"
        )
        assert diff.json()["changed"]["url"]["from"] == "https://a.com"

        # Publish v1 (rollback)
        await async_client.post(
            f"/api/recipes/COLLECTOR/{inst_id}/publish", json={"version_no": 1}
        )
        current = await async_client.get(f"/api/recipes/COLLECTOR/{inst_id}/current")
        assert current.json()["version_no"] == 1


# test_concurrent_pipelines.py

class TestConcurrentPipelines:
    async def test_two_pipelines_process_independently(self, async_client):
        """Two active pipelines should not interfere with each other."""
        p1 = await create_and_activate_pipeline(async_client, "Pipeline A")
        p2 = await create_and_activate_pipeline(async_client, "Pipeline B")

        await inject_job(p1, source_key="file-a.csv")
        await inject_job(p2, source_key="file-b.csv")

        # Verify each pipeline only sees its own items
        items_p1 = await get_jobs(async_client, p1.id)
        items_p2 = await get_jobs(async_client, p2.id)
        assert len(items_p1) == 1
        assert len(items_p2) == 1
        assert items_p1[0]["source_key"] == "file-a.csv"
        assert items_p2[0]["source_key"] == "file-b.csv"


# test_error_recovery.py

class TestErrorRecovery:
    async def test_retry_on_transient_error(self, db, seed_pipeline_with_retry):
        """Step configured with retry_count=3 retries on failure."""
        # First 2 executions fail, third succeeds
        ...

    async def test_on_error_skip_continues(self, db, seed_pipeline_skip_on_error):
        """Step configured with on_error=SKIP marks step SKIPPED and continues."""
        ...

    async def test_on_error_stop_halts(self, db, seed_pipeline_stop_on_error):
        """Step configured with on_error=STOP marks item FAILED immediately."""
        ...


# test_execution_snapshot.py

class TestExecutionSnapshot:
    async def test_snapshot_captures_all_configs(self, db, seed_execution):
        """Snapshot should contain collector, algorithm, and transfer configs."""
        snapshot = seed_execution.snapshot
        assert snapshot.collector_config != {}
        assert snapshot.algorithm_config != {}
        assert snapshot.transfer_config != {}
        assert snapshot.snapshot_hash is not None

    async def test_snapshot_immutable_after_creation(self, db, seed_execution):
        """Changing the recipe should not affect existing snapshot."""
        original_hash = seed_execution.snapshot.snapshot_hash
        # Update recipe
        ...
        # Reload snapshot
        assert seed_execution.snapshot.snapshot_hash == original_hash

    async def test_different_executions_different_snapshots(self, db):
        """Each execution gets its own independent snapshot."""
        ...
```

---

## 5. Test Plugin Fixtures

### 5.1 Echo Plugin (fixtures/plugins/echo-plugin/)

**hermes-plugin.json:**
```json
{
  "name": "echo",
  "version": "1.0.0",
  "type": "ALGORITHM",
  "description": "Echoes input data as output (for testing)",
  "runtime": "python",
  "entrypoint": "main.py",
  "inputSchema": {}
}
```

**main.py:**
```python
"""Echo plugin -- returns input as output."""
import sys, json

for line in sys.stdin:
    msg = json.loads(line.strip())
    if msg["type"] == "CONFIGURE":
        pass
    elif msg["type"] == "EXECUTE":
        out = {"type": "OUTPUT", "data": msg.get("input")}
        print(json.dumps(out), flush=True)
        print(json.dumps({"type": "DONE", "summary": {"echoed": True}}), flush=True)
```

### 5.2 Slow Plugin (timeout testing)

```python
"""Slow plugin -- sleeps for configured duration."""
import sys, json, time

for line in sys.stdin:
    msg = json.loads(line.strip())
    if msg["type"] == "CONFIGURE":
        sleep_seconds = msg.get("config", {}).get("sleep", 60)
    elif msg["type"] == "EXECUTE":
        time.sleep(sleep_seconds)
        print(json.dumps({"type": "DONE", "summary": {}}), flush=True)
```

### 5.3 Error Plugin

```python
"""Error plugin -- always reports an error."""
import sys, json

for line in sys.stdin:
    msg = json.loads(line.strip())
    if msg["type"] == "EXECUTE":
        print(json.dumps({"type": "ERROR", "code": "TEST_ERROR",
                          "message": "Intentional error"}), flush=True)
        print(json.dumps({"type": "DONE", "summary": {"failed": True}}), flush=True)
```

### 5.4 Crash Plugin

```python
"""Crash plugin -- exits with non-zero code."""
import sys
sys.exit(1)
```

### 5.5 Multi-Output Plugin

```python
"""Multi-output plugin -- emits multiple outputs with progress."""
import sys, json

for line in sys.stdin:
    msg = json.loads(line.strip())
    if msg["type"] == "EXECUTE":
        items = msg.get("input", {}).get("records", [{"a": 1}, {"b": 2}, {"c": 3}])
        total = len(items)
        for i, item in enumerate(items):
            print(json.dumps({"type": "STATUS", "progress": (i + 1) / total}), flush=True)
            print(json.dumps({"type": "OUTPUT", "data": item}), flush=True)
        print(json.dumps({"type": "DONE", "summary": {"count": total}}), flush=True)
```

---

## 6. CI/CD Pipeline Configuration

```yaml
# .github/workflows/test.yml

name: Tests
on: [push, pull_request]

env:
  TEST_DATABASE_URL: postgresql+asyncpg://hermes:hermes@localhost:5432/hermes_test

jobs:
  unit:
    name: Unit Tests
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: cd backend && pip install -e ".[dev]"
      - run: cd backend && pytest tests/unit/ -v --tb=short

  service:
    name: Service Tests (PostgreSQL)
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: hermes
          POSTGRES_PASSWORD: hermes
          POSTGRES_DB: hermes_test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: cd backend && pip install -e ".[dev]"
      - run: cd backend && pytest tests/service/ -v --tb=short

  integration:
    name: Integration Tests
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: hermes
          POSTGRES_PASSWORD: hermes
          POSTGRES_DB: hermes_test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: cd backend && pip install -e ".[dev]"
      - run: cd backend && pytest tests/integration/ tests/e2e/ -v --tb=short -x

  lint:
    name: Lint & Type Check
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: cd backend && pip install -e ".[dev]"
      - run: cd backend && ruff check .
      - run: cd backend && mypy hermes/

  coverage:
    name: Coverage Gate
    runs-on: ubuntu-latest
    needs: [unit, service]
    services:
      postgres:
        image: postgres:15
        env:
          POSTGRES_USER: hermes
          POSTGRES_PASSWORD: hermes
          POSTGRES_DB: hermes_test
        ports: ['5432:5432']
        options: >-
          --health-cmd pg_isready
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: '3.12' }
      - run: cd backend && pip install -e ".[dev]" && pip install pytest-cov
      - run: |
          cd backend && pytest tests/unit/ tests/service/ \
            --cov=hermes --cov-report=xml --cov-fail-under=80
      - uses: codecov/codecov-action@v4
        with:
          files: backend/coverage.xml
```

---

## 7. Coverage Requirements

| Category | Minimum Coverage | Notes |
|----------|-----------------|-------|
| `hermes/plugins/protocol.py` | 95% | Core protocol -- correctness critical |
| `hermes/plugins/registry.py` | 90% | Plugin discovery/lookup |
| `hermes/plugins/executor.py` | 85% | Subprocess interaction has inherent edge cases |
| `hermes/domain/services/recipe_engine.py` | 90% | Versioning/rollback must be reliable |
| `hermes/domain/services/pipeline_manager.py` | 90% | Lifecycle management |
| `hermes/domain/models/` | 80% | SQLAlchemy models (constructors, relationships) |
| `hermes/api/` | 80% | API routes |
| **Overall** | **80%** | CI gate blocks merge below this |

---

## 8. Key Test Scenarios for Hermes's Differentiators

### 8.1 Job-Level Tracking

| # | Scenario | Assertion |
|---|----------|-----------|
| 1 | Item detected by FileWatcher | Job created with status=DETECTED, source_type=FILE |
| 2 | Item transitions through pipeline | Status: DETECTED -> QUEUED -> PROCESSING -> COMPLETED |
| 3 | Each step creates StepExecution | JobStepExecution count == pipeline step count |
| 4 | Event log records every state change | ExecutionEventLog entries for each transition |
| 5 | Item query by source_key | GET /jobs?source_key=file.csv returns correct item |
| 6 | Item detail shows full provenance | Execution history, step results, event timeline |

### 8.2 Recipe Versioning + Rollback + Diff

| # | Scenario | Assertion |
|---|----------|-----------|
| 7 | Create recipe v1 | version_no=1 |
| 8 | Create recipe v2 | version_no=2 |
| 9 | Publish v2 | v2.is_current=True, v1.is_current=False |
| 10 | Rollback to v1 | v1.is_current=True, v2.is_current=False |
| 11 | Diff v1 vs v2 | Shows added/removed/changed keys correctly |
| 12 | Recipe history | Returns all versions in descending order |
| 13 | Publish non-existent version | Raises ValueError |

### 8.3 Reprocessing

| # | Scenario | Assertion |
|---|----------|-----------|
| 14 | Reprocess completed item | New execution with trigger_type=REPROCESS |
| 15 | Reprocess from step N | Steps before N get status=SKIPPED |
| 16 | Reprocess with latest recipe | New snapshot differs from original |
| 17 | Reprocess with original recipe | New snapshot matches original |
| 18 | Bulk reprocess all FAILED items | All failed items get new execution |
| 19 | Reprocess request approval flow | Status: PENDING -> APPROVED -> EXECUTING -> DONE |

### 8.4 Plugin Protocol Communication

| # | Scenario | Assertion |
|---|----------|-----------|
| 20 | CONFIGURE message sent correctly | Plugin receives valid JSON with config+context |
| 21 | EXECUTE message sent correctly | Plugin receives input data |
| 22 | Plugin returns OUTPUT | Core captures output data |
| 23 | Plugin returns multiple OUTPUTs | All outputs collected in order |
| 24 | Plugin returns LOG | Core captures log with level |
| 25 | Plugin returns ERROR | Core captures error with code+message |
| 26 | Plugin returns STATUS | Core updates progress (0.0-1.0) |
| 27 | Plugin returns DONE | Core marks execution complete |
| 28 | Plugin sends invalid JSON | Core logs warning, does not crash |
| 29 | Plugin exits with code 2 | Core records CONFIG_ERROR |
| 30 | Plugin exceeds timeout | Core kills process, records TIMEOUT |

### 8.5 NiFi Integration

| # | Scenario | Assertion |
|---|----------|-----------|
| 31 | List NiFi process groups | Returns groups from mocked API |
| 32 | Trigger NiFi process group | Sends correct PUT request |
| 33 | NiFi connection failure | Returns error, does not crash |
| 34 | NiFi flow execution status | Polls status until complete |

### 8.6 Monitoring Engine

| # | Scenario | Assertion |
|---|----------|-----------|
| 35 | FileWatcher detects new file | Creates Job with correct metadata |
| 36 | FileWatcher respects patterns | Ignores non-matching files |
| 37 | APIPoller fetches data | Creates Jobs from response |
| 38 | APIPoller handles HTTP error | Records error, does not crash |
| 39 | APIPoller pagination | Fetches multiple pages |

### 8.7 Execution Snapshot

| # | Scenario | Assertion |
|---|----------|-----------|
| 40 | Snapshot captured at execution time | Contains all step configs |
| 41 | Snapshot has hash | Deterministic hash from config content |
| 42 | Snapshot immutable | Config changes do not affect existing snapshot |
| 43 | Snapshot used in reprocess audit | Can compare original vs reprocess configs |

### 8.8 Dedup Prevention

| # | Scenario | Assertion |
|---|----------|-----------|
| 44 | Same dedup_key rejected | Second item with same key is deduplicated |
| 45 | Different dedup_keys accepted | Two items created |
| 46 | NULL dedup_key always accepted | Multiple items with no dedup_key created |
| 47 | Dedup scoped to pipeline | Same key in different pipelines = 2 items |

### 8.9 Error Handling + Retry

| # | Scenario | Assertion |
|---|----------|-----------|
| 48 | on_error=STOP halts pipeline | Job status=FAILED, subsequent steps not run |
| 49 | on_error=SKIP continues | Failed step status=SKIPPED, next step runs |
| 50 | retry_count=3 retries | Up to 3 retry attempts recorded |
| 51 | retry_delay_seconds respected | Delay between retries |
| 52 | All retries fail | Final status=FAILED after 3 attempts |
| 53 | Retry succeeds on attempt 2 | Final status=COMPLETED, retry_attempt=1 |

### 8.10 Concurrent Pipeline Execution

| # | Scenario | Assertion |
|---|----------|-----------|
| 54 | Two pipelines run simultaneously | Each processes its own items independently |
| 55 | Same definition used by two pipelines | No shared state corruption |
| 56 | Pipeline deactivation while items in flight | Graceful drain or clear error |

---

## 9. Test Execution Guide

```bash
# All unit tests (no DB required, fast)
cd backend && pytest tests/unit/ -v

# Service tests (requires PostgreSQL or falls back to SQLite)
cd backend && pytest tests/service/ -v

# Integration tests (requires PostgreSQL, may spawn subprocesses)
cd backend && pytest tests/integration/ -v

# E2E tests (full stack)
cd backend && pytest tests/e2e/ -v

# All tests with coverage
cd backend && pytest tests/ --cov=hermes --cov-report=term-missing --cov-fail-under=80

# Run only fast tests (< 5s each)
cd backend && pytest tests/unit/ tests/service/ -v

# Run a specific test scenario
cd backend && pytest tests/e2e/test_reprocess_scenario.py::TestReprocessScenario::test_reprocess_single_item -v

# Run with PostgreSQL (CI mode)
TEST_DATABASE_URL="postgresql+asyncpg://hermes:hermes@localhost:5432/hermes_test" \
  pytest tests/ -v
```

---

## 10. Recommended Additional Dependencies

Add to `pyproject.toml` `[project.optional-dependencies] dev`:

```toml
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "pytest-timeout>=2.3.0",       # Per-test timeouts
    "aiosqlite>=0.20.0",           # SQLite async for fast local tests
    "respx>=0.21.0",               # httpx mocking (for NiFi, API poller)
    "factory-boy>=3.3.0",          # Optional: ORM factories
    "ruff>=0.7.0",
    "mypy>=1.13.0",
]
```

---

## 11. Implementation Priority

| Phase | Tests to Build | Effort | Why First |
|-------|---------------|--------|-----------|
| **Phase 1** | Unit: protocol, registry, config validation, diff | 1 day | Foundation, fast feedback, no infra needed |
| **Phase 2** | Service: recipe_engine, pipeline_manager | 2 days | Core business logic, needs DB fixture |
| **Phase 3** | Integration: plugin_executor, acceptance tests | 1 day | Validates plugin contract |
| **Phase 4** | E2E: full pipeline flow, reprocess, dedup | 2 days | Validates differentiators end-to-end |
| **Phase 5** | Monitoring, NiFi, concurrent, error recovery | 2 days | Edge cases and robustness |
| **Phase 6** | CI pipeline, coverage gates | 0.5 days | Automation |

**Total estimated effort: ~8.5 days for comprehensive test suite.**

---

## 12. Build Smoke And Provider Matrix

Build smoke is the shallowest safety net for the new `.NET` path.

It verifies:

- solution restore succeeds
- solution build succeeds
- minimum public API endpoints respond with the expected contract

Current smoke commands:

```bash
dotnet build engine/Hermes.sln
dotnet test engine/tests/Hermes.Api.Tests/Hermes.Api.Tests.csproj
```

Current `.NET API` contract coverage includes:

- `/`
- `/health/live`
- `/health/ready`
- `/api/v1/system/info`
- `/api/v1/definitions/{kind}`
- `/api/v1/definitions/{kind}/{id}`
- `/api/v1/definitions/{kind}/{id}/versions`
- `/api/v1/pipelines`
- `/api/v1/pipelines/{id}`
- `/api/v1/pipelines/{id}/stages`
- `/api/v1/jobs`
- `/api/v1/jobs/{id}`
- `/api/v1/monitor/stats`
- `/api/v1/monitor/activations`
- `/api/v1/monitor/recent-jobs`

Hermes should eventually validate both supported providers and both operating modes:

| Provider | Mode | Purpose |
|---|---|---|
| PostgreSQL | Docker | default local/CI bootstrap |
| PostgreSQL | Existing instance | user-managed database connectivity |
| SQL Server | Existing instance | provider parity for enterprise installs |

Provider-aware tests should cover:

- schema bootstrap
- migrations
- index/constraint compatibility
- configurable schema namespace (default `hermes`)
