-- ============================================================================
-- Hermes Data Processing Platform - PostgreSQL Schema
-- Version: 1.0.0
-- ============================================================================
-- Layers:
--   1. Definition Layer  - What CAN exist (plugin catalog)
--   2. Instance Layer    - What IS configured (recipes)
--   3. Monitoring Layer  - What IS running (activations)
--   4. Execution Layer   - What HAS happened (work items, logs)
-- ============================================================================

BEGIN;

-- Enable UUID generation
CREATE EXTENSION IF NOT EXISTS "pgcrypto";

-- ============================================================================
-- ENUM TYPES
-- ============================================================================

CREATE TYPE definition_status AS ENUM ('DRAFT', 'ACTIVE', 'DEPRECATED', 'ARCHIVED');
CREATE TYPE execution_type AS ENUM ('PLUGIN', 'SCRIPT', 'HTTP', 'DOCKER', 'NIFI_FLOW');
CREATE TYPE instance_status AS ENUM ('DRAFT', 'ACTIVE', 'DISABLED', 'ARCHIVED');
CREATE TYPE pipeline_status AS ENUM ('DRAFT', 'ACTIVE', 'PAUSED', 'ARCHIVED');
CREATE TYPE monitoring_type AS ENUM ('FILE_MONITOR', 'API_POLL', 'DB_POLL', 'EVENT_STREAM');
CREATE TYPE step_type AS ENUM ('COLLECT', 'ALGORITHM', 'TRANSFER');
CREATE TYPE ref_type AS ENUM ('COLLECTOR', 'ALGORITHM', 'TRANSFER');
CREATE TYPE on_error_action AS ENUM ('STOP', 'SKIP', 'RETRY');
CREATE TYPE activation_status AS ENUM ('STARTING', 'RUNNING', 'STOPPING', 'STOPPED', 'ERROR');
CREATE TYPE source_type AS ENUM ('FILE', 'API_RESPONSE', 'DB_CHANGE', 'EVENT');
CREATE TYPE work_item_status AS ENUM ('DETECTED', 'QUEUED', 'PROCESSING', 'COMPLETED', 'FAILED');
CREATE TYPE trigger_type AS ENUM ('INITIAL', 'RETRY', 'REPROCESS');
CREATE TYPE execution_status AS ENUM ('RUNNING', 'COMPLETED', 'FAILED', 'CANCELLED');
CREATE TYPE step_execution_status AS ENUM ('PENDING', 'RUNNING', 'COMPLETED', 'FAILED', 'SKIPPED');
CREATE TYPE reprocess_status AS ENUM ('PENDING', 'APPROVED', 'EXECUTING', 'DONE', 'REJECTED');
CREATE TYPE event_level AS ENUM ('DEBUG', 'INFO', 'WARN', 'ERROR');
CREATE TYPE plugin_status AS ENUM ('INSTALLED', 'ACTIVE', 'DISABLED', 'UNINSTALLED');

-- ============================================================================
-- LAYER 1: DEFINITION LAYER - "What CAN exist"
-- ============================================================================

-- --------------------------------------------------------------------------
-- Collector Definitions
-- --------------------------------------------------------------------------

CREATE TABLE collector_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR(128) NOT NULL UNIQUE,
    name            VARCHAR(256) NOT NULL,
    description     TEXT,
    category        VARCHAR(128),
    icon_url        VARCHAR(512),
    status          definition_status NOT NULL DEFAULT 'DRAFT',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE collector_definitions IS
    'Catalog of collector plugin types (e.g. REST API, File Watcher). Registered by developers/admins.';

CREATE INDEX idx_collector_definitions_status ON collector_definitions (status);
CREATE INDEX idx_collector_definitions_category ON collector_definitions (category);

CREATE TABLE collector_definition_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_id   UUID NOT NULL REFERENCES collector_definitions (id) ON DELETE CASCADE,
    version_no      INTEGER NOT NULL,
    input_schema    JSONB NOT NULL DEFAULT '{}',
    ui_schema       JSONB NOT NULL DEFAULT '{}',
    output_schema   JSONB NOT NULL DEFAULT '{}',
    default_config  JSONB NOT NULL DEFAULT '{}',
    execution_type  execution_type NOT NULL,
    execution_ref   VARCHAR(512),
    is_published    BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_collector_def_version UNIQUE (definition_id, version_no),
    CONSTRAINT ck_collector_def_version_no CHECK (version_no > 0)
);
COMMENT ON TABLE collector_definition_versions IS
    'Versioned schemas and execution config for a collector definition. Each version captures input/ui/output JSON Schemas.';

CREATE INDEX idx_collector_def_versions_def ON collector_definition_versions (definition_id);

-- --------------------------------------------------------------------------
-- Algorithm Definitions
-- --------------------------------------------------------------------------

CREATE TABLE algorithm_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR(128) NOT NULL UNIQUE,
    name            VARCHAR(256) NOT NULL,
    description     TEXT,
    category        VARCHAR(128),
    icon_url        VARCHAR(512),
    status          definition_status NOT NULL DEFAULT 'DRAFT',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE algorithm_definitions IS
    'Catalog of algorithm/processing plugin types (e.g. anomaly detection, data transformation).';

CREATE INDEX idx_algorithm_definitions_status ON algorithm_definitions (status);
CREATE INDEX idx_algorithm_definitions_category ON algorithm_definitions (category);

CREATE TABLE algorithm_definition_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_id   UUID NOT NULL REFERENCES algorithm_definitions (id) ON DELETE CASCADE,
    version_no      INTEGER NOT NULL,
    input_schema    JSONB NOT NULL DEFAULT '{}',
    ui_schema       JSONB NOT NULL DEFAULT '{}',
    output_schema   JSONB NOT NULL DEFAULT '{}',
    default_config  JSONB NOT NULL DEFAULT '{}',
    execution_type  execution_type NOT NULL,
    execution_ref   VARCHAR(512),
    is_published    BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_algorithm_def_version UNIQUE (definition_id, version_no),
    CONSTRAINT ck_algorithm_def_version_no CHECK (version_no > 0)
);
COMMENT ON TABLE algorithm_definition_versions IS
    'Versioned schemas and execution config for an algorithm definition.';

CREATE INDEX idx_algorithm_def_versions_def ON algorithm_definition_versions (definition_id);

-- --------------------------------------------------------------------------
-- Transfer Definitions
-- --------------------------------------------------------------------------

CREATE TABLE transfer_definitions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    code            VARCHAR(128) NOT NULL UNIQUE,
    name            VARCHAR(256) NOT NULL,
    description     TEXT,
    category        VARCHAR(128),
    icon_url        VARCHAR(512),
    status          definition_status NOT NULL DEFAULT 'DRAFT',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE transfer_definitions IS
    'Catalog of transfer/output plugin types (e.g. S3 upload, database writer, webhook sender).';

CREATE INDEX idx_transfer_definitions_status ON transfer_definitions (status);
CREATE INDEX idx_transfer_definitions_category ON transfer_definitions (category);

CREATE TABLE transfer_definition_versions (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_id   UUID NOT NULL REFERENCES transfer_definitions (id) ON DELETE CASCADE,
    version_no      INTEGER NOT NULL,
    input_schema    JSONB NOT NULL DEFAULT '{}',
    ui_schema       JSONB NOT NULL DEFAULT '{}',
    output_schema   JSONB NOT NULL DEFAULT '{}',
    default_config  JSONB NOT NULL DEFAULT '{}',
    execution_type  execution_type NOT NULL,
    execution_ref   VARCHAR(512),
    is_published    BOOLEAN NOT NULL DEFAULT false,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_transfer_def_version UNIQUE (definition_id, version_no),
    CONSTRAINT ck_transfer_def_version_no CHECK (version_no > 0)
);
COMMENT ON TABLE transfer_definition_versions IS
    'Versioned schemas and execution config for a transfer definition.';

CREATE INDEX idx_transfer_def_versions_def ON transfer_definition_versions (definition_id);

-- ============================================================================
-- LAYER 2: INSTANCE LAYER - "What IS configured"
-- ============================================================================

-- --------------------------------------------------------------------------
-- Collector Instances (operator-configured)
-- --------------------------------------------------------------------------

CREATE TABLE collector_instances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_id   UUID NOT NULL REFERENCES collector_definitions (id) ON DELETE RESTRICT,
    name            VARCHAR(256) NOT NULL,
    description     TEXT,
    status          instance_status NOT NULL DEFAULT 'DRAFT',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE collector_instances IS
    'Operator-configured collector instances. Each references a definition and holds versioned recipe config.';

CREATE INDEX idx_collector_instances_def ON collector_instances (definition_id);
CREATE INDEX idx_collector_instances_status ON collector_instances (status);

CREATE TABLE collector_instance_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id         UUID NOT NULL REFERENCES collector_instances (id) ON DELETE CASCADE,
    def_version_id      UUID NOT NULL REFERENCES collector_definition_versions (id) ON DELETE RESTRICT,
    version_no          INTEGER NOT NULL,
    config_json         JSONB NOT NULL DEFAULT '{}',
    secret_binding_json JSONB NOT NULL DEFAULT '{}',
    is_current          BOOLEAN NOT NULL DEFAULT false,
    created_by          VARCHAR(256),
    change_note         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_collector_inst_version UNIQUE (instance_id, version_no),
    CONSTRAINT ck_collector_inst_version_no CHECK (version_no > 0)
);
COMMENT ON TABLE collector_instance_versions IS
    'Versioned recipe configs for a collector instance. The is_current flag marks the active version.';

CREATE INDEX idx_collector_inst_versions_inst ON collector_instance_versions (instance_id);
CREATE INDEX idx_collector_inst_versions_current ON collector_instance_versions (instance_id) WHERE is_current = true;

-- --------------------------------------------------------------------------
-- Algorithm Instances
-- --------------------------------------------------------------------------

CREATE TABLE algorithm_instances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_id   UUID NOT NULL REFERENCES algorithm_definitions (id) ON DELETE RESTRICT,
    name            VARCHAR(256) NOT NULL,
    description     TEXT,
    status          instance_status NOT NULL DEFAULT 'DRAFT',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE algorithm_instances IS
    'Operator-configured algorithm instances with versioned recipe config.';

CREATE INDEX idx_algorithm_instances_def ON algorithm_instances (definition_id);
CREATE INDEX idx_algorithm_instances_status ON algorithm_instances (status);

CREATE TABLE algorithm_instance_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id         UUID NOT NULL REFERENCES algorithm_instances (id) ON DELETE CASCADE,
    def_version_id      UUID NOT NULL REFERENCES algorithm_definition_versions (id) ON DELETE RESTRICT,
    version_no          INTEGER NOT NULL,
    config_json         JSONB NOT NULL DEFAULT '{}',
    secret_binding_json JSONB NOT NULL DEFAULT '{}',
    is_current          BOOLEAN NOT NULL DEFAULT false,
    created_by          VARCHAR(256),
    change_note         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_algorithm_inst_version UNIQUE (instance_id, version_no),
    CONSTRAINT ck_algorithm_inst_version_no CHECK (version_no > 0)
);
COMMENT ON TABLE algorithm_instance_versions IS
    'Versioned recipe configs for an algorithm instance.';

CREATE INDEX idx_algorithm_inst_versions_inst ON algorithm_instance_versions (instance_id);
CREATE INDEX idx_algorithm_inst_versions_current ON algorithm_instance_versions (instance_id) WHERE is_current = true;

-- --------------------------------------------------------------------------
-- Transfer Instances
-- --------------------------------------------------------------------------

CREATE TABLE transfer_instances (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    definition_id   UUID NOT NULL REFERENCES transfer_definitions (id) ON DELETE RESTRICT,
    name            VARCHAR(256) NOT NULL,
    description     TEXT,
    status          instance_status NOT NULL DEFAULT 'DRAFT',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE transfer_instances IS
    'Operator-configured transfer instances with versioned recipe config.';

CREATE INDEX idx_transfer_instances_def ON transfer_instances (definition_id);
CREATE INDEX idx_transfer_instances_status ON transfer_instances (status);

CREATE TABLE transfer_instance_versions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    instance_id         UUID NOT NULL REFERENCES transfer_instances (id) ON DELETE CASCADE,
    def_version_id      UUID NOT NULL REFERENCES transfer_definition_versions (id) ON DELETE RESTRICT,
    version_no          INTEGER NOT NULL,
    config_json         JSONB NOT NULL DEFAULT '{}',
    secret_binding_json JSONB NOT NULL DEFAULT '{}',
    is_current          BOOLEAN NOT NULL DEFAULT false,
    created_by          VARCHAR(256),
    change_note         TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_transfer_inst_version UNIQUE (instance_id, version_no),
    CONSTRAINT ck_transfer_inst_version_no CHECK (version_no > 0)
);
COMMENT ON TABLE transfer_instance_versions IS
    'Versioned recipe configs for a transfer instance.';

CREATE INDEX idx_transfer_inst_versions_inst ON transfer_instance_versions (instance_id);
CREATE INDEX idx_transfer_inst_versions_current ON transfer_instance_versions (instance_id) WHERE is_current = true;

-- --------------------------------------------------------------------------
-- Pipeline Instances & Steps
-- --------------------------------------------------------------------------

CREATE TABLE pipeline_instances (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                VARCHAR(256) NOT NULL,
    description         TEXT,
    monitoring_type     monitoring_type,
    monitoring_config   JSONB NOT NULL DEFAULT '{}',
    status              pipeline_status NOT NULL DEFAULT 'DRAFT',
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE pipeline_instances IS
    'A configured data pipeline composed of ordered steps (collect, algorithm, transfer). Operators build these via the visual designer.';

CREATE INDEX idx_pipeline_instances_status ON pipeline_instances (status);

CREATE TABLE pipeline_steps (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_instance_id    UUID NOT NULL REFERENCES pipeline_instances (id) ON DELETE CASCADE,
    step_order              INTEGER NOT NULL,
    step_type               step_type NOT NULL,
    ref_type                ref_type NOT NULL,
    ref_id                  UUID NOT NULL,
    is_enabled              BOOLEAN NOT NULL DEFAULT true,
    on_error                on_error_action NOT NULL DEFAULT 'STOP',
    retry_count             INTEGER NOT NULL DEFAULT 0,
    retry_delay_seconds     INTEGER NOT NULL DEFAULT 0,

    CONSTRAINT uq_pipeline_step_order UNIQUE (pipeline_instance_id, step_order),
    CONSTRAINT ck_step_order_positive CHECK (step_order > 0),
    CONSTRAINT ck_retry_count_non_negative CHECK (retry_count >= 0),
    CONSTRAINT ck_retry_delay_non_negative CHECK (retry_delay_seconds >= 0)
);
COMMENT ON TABLE pipeline_steps IS
    'Ordered steps within a pipeline. Each step references a collector, algorithm, or transfer instance.';

CREATE INDEX idx_pipeline_steps_pipeline ON pipeline_steps (pipeline_instance_id);

-- ============================================================================
-- LAYER 3: MONITORING LAYER - "What IS running"
-- ============================================================================

CREATE TABLE pipeline_activations (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_instance_id    UUID NOT NULL REFERENCES pipeline_instances (id) ON DELETE RESTRICT,
    status                  activation_status NOT NULL DEFAULT 'STARTING',
    started_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    stopped_at              TIMESTAMPTZ,
    last_heartbeat_at       TIMESTAMPTZ,
    last_polled_at          TIMESTAMPTZ,
    error_message           TEXT,
    worker_id               VARCHAR(256),
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE pipeline_activations IS
    'Active running sessions of a pipeline. Tracks heartbeat, polling status, and the worker executing it.';

CREATE INDEX idx_pipeline_activations_pipeline ON pipeline_activations (pipeline_instance_id);
CREATE INDEX idx_pipeline_activations_status ON pipeline_activations (status);
CREATE INDEX idx_pipeline_activations_worker ON pipeline_activations (worker_id);

-- ============================================================================
-- LAYER 4: EXECUTION LAYER - "What HAS happened"
-- ============================================================================

-- --------------------------------------------------------------------------
-- Work Items
-- --------------------------------------------------------------------------

CREATE TABLE work_items (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    pipeline_activation_id  UUID NOT NULL REFERENCES pipeline_activations (id) ON DELETE RESTRICT,
    pipeline_instance_id    UUID NOT NULL REFERENCES pipeline_instances (id) ON DELETE RESTRICT,
    source_type             source_type NOT NULL,
    source_key              VARCHAR(1024) NOT NULL,
    source_metadata         JSONB NOT NULL DEFAULT '{}',
    dedup_key               VARCHAR(512),
    detected_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    status                  work_item_status NOT NULL DEFAULT 'DETECTED',
    current_execution_id    UUID,
    execution_count         INTEGER NOT NULL DEFAULT 0,
    last_completed_at       TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE work_items IS
    'Individual data items detected by monitoring. Every item is tracked through its full lifecycle (detected -> completed/failed).';

CREATE INDEX idx_work_items_pipeline_instance ON work_items (pipeline_instance_id);
CREATE INDEX idx_work_items_activation ON work_items (pipeline_activation_id);
CREATE INDEX idx_work_items_status ON work_items (status);
CREATE INDEX idx_work_items_dedup ON work_items (pipeline_instance_id, dedup_key) WHERE dedup_key IS NOT NULL;
CREATE INDEX idx_work_items_detected_at ON work_items (detected_at);
CREATE INDEX idx_work_items_source_key ON work_items (source_key);

-- --------------------------------------------------------------------------
-- Work Item Executions
-- --------------------------------------------------------------------------

CREATE TABLE work_item_executions (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    work_item_id            UUID NOT NULL REFERENCES work_items (id) ON DELETE CASCADE,
    execution_no            INTEGER NOT NULL,
    trigger_type            trigger_type NOT NULL DEFAULT 'INITIAL',
    trigger_source          VARCHAR(256),
    status                  execution_status NOT NULL DEFAULT 'RUNNING',
    started_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    ended_at                TIMESTAMPTZ,
    duration_ms             BIGINT,
    reprocess_request_id    UUID,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT uq_work_item_execution_no UNIQUE (work_item_id, execution_no),
    CONSTRAINT ck_execution_no_positive CHECK (execution_no > 0),
    CONSTRAINT ck_duration_non_negative CHECK (duration_ms IS NULL OR duration_ms >= 0)
);
COMMENT ON TABLE work_item_executions IS
    'Each attempt to process a work item. Multiple executions occur on retry or reprocessing.';

CREATE INDEX idx_work_item_executions_item ON work_item_executions (work_item_id);
CREATE INDEX idx_work_item_executions_status ON work_item_executions (status);
CREATE INDEX idx_work_item_executions_started ON work_item_executions (started_at);

-- Add the FK from work_items.current_execution_id now that work_item_executions exists
ALTER TABLE work_items
    ADD CONSTRAINT fk_work_items_current_execution
    FOREIGN KEY (current_execution_id) REFERENCES work_item_executions (id)
    ON DELETE SET NULL;

-- --------------------------------------------------------------------------
-- Work Item Step Executions
-- --------------------------------------------------------------------------

CREATE TABLE work_item_step_executions (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID NOT NULL REFERENCES work_item_executions (id) ON DELETE CASCADE,
    pipeline_step_id    UUID NOT NULL REFERENCES pipeline_steps (id) ON DELETE RESTRICT,
    step_type           step_type NOT NULL,
    step_order          INTEGER NOT NULL,
    status              step_execution_status NOT NULL DEFAULT 'PENDING',
    started_at          TIMESTAMPTZ,
    ended_at            TIMESTAMPTZ,
    duration_ms         BIGINT,
    input_summary       JSONB,
    output_summary      JSONB,
    error_code          VARCHAR(128),
    error_message       TEXT,
    retry_attempt       INTEGER NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ck_step_exec_duration_non_negative CHECK (duration_ms IS NULL OR duration_ms >= 0),
    CONSTRAINT ck_step_exec_retry_non_negative CHECK (retry_attempt >= 0)
);
COMMENT ON TABLE work_item_step_executions IS
    'Per-step execution record within a work item execution. Tracks status, timing, input/output summaries, and errors for each pipeline step.';

CREATE INDEX idx_step_executions_execution ON work_item_step_executions (execution_id);
CREATE INDEX idx_step_executions_step ON work_item_step_executions (pipeline_step_id);
CREATE INDEX idx_step_executions_status ON work_item_step_executions (status);

-- --------------------------------------------------------------------------
-- Execution Snapshots
-- --------------------------------------------------------------------------

CREATE TABLE execution_snapshots (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID NOT NULL UNIQUE REFERENCES work_item_executions (id) ON DELETE CASCADE,
    pipeline_config     JSONB NOT NULL DEFAULT '{}',
    collector_config    JSONB NOT NULL DEFAULT '{}',
    algorithm_config    JSONB NOT NULL DEFAULT '{}',
    transfer_config     JSONB NOT NULL DEFAULT '{}',
    snapshot_hash       VARCHAR(128),
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE execution_snapshots IS
    'Immutable snapshot of all recipe configs at execution time. Enables auditing what exact configuration was used for each run.';

CREATE INDEX idx_execution_snapshots_hash ON execution_snapshots (snapshot_hash);

-- --------------------------------------------------------------------------
-- Reprocess Requests
-- --------------------------------------------------------------------------

CREATE TABLE reprocess_requests (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    work_item_id        UUID NOT NULL REFERENCES work_items (id) ON DELETE CASCADE,
    requested_by        VARCHAR(256) NOT NULL,
    requested_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason              TEXT,
    start_from_step     INTEGER,
    use_latest_recipe   BOOLEAN NOT NULL DEFAULT true,
    status              reprocess_status NOT NULL DEFAULT 'PENDING',
    approved_by         VARCHAR(256),
    execution_id        UUID REFERENCES work_item_executions (id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE reprocess_requests IS
    'Operator requests to reprocess a work item, optionally from a specific step with latest or original recipe configs.';

CREATE INDEX idx_reprocess_requests_item ON reprocess_requests (work_item_id);
CREATE INDEX idx_reprocess_requests_status ON reprocess_requests (status);

-- Add the FK from work_item_executions.reprocess_request_id now that reprocess_requests exists
ALTER TABLE work_item_executions
    ADD CONSTRAINT fk_executions_reprocess_request
    FOREIGN KEY (reprocess_request_id) REFERENCES reprocess_requests (id)
    ON DELETE SET NULL;

-- --------------------------------------------------------------------------
-- Execution Event Logs
-- --------------------------------------------------------------------------

CREATE TABLE execution_event_logs (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    execution_id        UUID NOT NULL REFERENCES work_item_executions (id) ON DELETE CASCADE,
    step_execution_id   UUID REFERENCES work_item_step_executions (id) ON DELETE CASCADE,
    event_type          event_level NOT NULL DEFAULT 'INFO',
    event_code          VARCHAR(128) NOT NULL,
    message             TEXT,
    detail_json         JSONB,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE execution_event_logs IS
    'Append-only event log for execution tracing. Records every significant event (start, done, error) for full audit history.';

CREATE INDEX idx_event_logs_execution ON execution_event_logs (execution_id);
CREATE INDEX idx_event_logs_step_execution ON execution_event_logs (step_execution_id) WHERE step_execution_id IS NOT NULL;
CREATE INDEX idx_event_logs_event_code ON execution_event_logs (event_code);
CREATE INDEX idx_event_logs_created_at ON execution_event_logs (created_at);

-- ============================================================================
-- PLUGIN REGISTRY
-- ============================================================================

CREATE TABLE plugin_registry (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plugin_code     VARCHAR(128) NOT NULL UNIQUE,
    plugin_name     VARCHAR(256) NOT NULL,
    plugin_type     ref_type NOT NULL,
    version         VARCHAR(64) NOT NULL,
    description     TEXT,
    author          VARCHAR(256),
    homepage_url    VARCHAR(512),
    repository_url  VARCHAR(512),
    icon_url        VARCHAR(512),
    status          plugin_status NOT NULL DEFAULT 'INSTALLED',
    install_path    VARCHAR(1024),
    manifest_json   JSONB NOT NULL DEFAULT '{}',
    installed_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE plugin_registry IS
    'Registry of installed plugins. Tracks plugin metadata, installation path, and manifest for the Plugin Marketplace.';

CREATE INDEX idx_plugin_registry_type ON plugin_registry (plugin_type);
CREATE INDEX idx_plugin_registry_status ON plugin_registry (status);

-- ============================================================================
-- updated_at TRIGGER FUNCTION
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply updated_at triggers to tables that have the column
CREATE TRIGGER trg_collector_definitions_updated_at
    BEFORE UPDATE ON collector_definitions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_algorithm_definitions_updated_at
    BEFORE UPDATE ON algorithm_definitions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_transfer_definitions_updated_at
    BEFORE UPDATE ON transfer_definitions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_collector_instances_updated_at
    BEFORE UPDATE ON collector_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_algorithm_instances_updated_at
    BEFORE UPDATE ON algorithm_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_transfer_instances_updated_at
    BEFORE UPDATE ON transfer_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_pipeline_instances_updated_at
    BEFORE UPDATE ON pipeline_instances
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_work_items_updated_at
    BEFORE UPDATE ON work_items
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_reprocess_requests_updated_at
    BEFORE UPDATE ON reprocess_requests
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER trg_plugin_registry_updated_at
    BEFORE UPDATE ON plugin_registry
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- ============================================================================
-- SEED DATA: Demo REST API Collector Definition
-- ============================================================================

INSERT INTO collector_definitions (id, code, name, description, category, status)
VALUES (
    'a0000000-0000-0000-0000-000000000001',
    'rest-api-collector',
    'REST API Collector',
    'Collects data from any REST API endpoint. Supports GET/POST methods, authentication (Bearer, API Key, Basic), pagination, and configurable polling intervals.',
    'Data Collection',
    'ACTIVE'
);

INSERT INTO collector_definition_versions (
    id, definition_id, version_no,
    input_schema, ui_schema, output_schema,
    default_config, execution_type, execution_ref, is_published
) VALUES (
    'b0000000-0000-0000-0000-000000000001',
    'a0000000-0000-0000-0000-000000000001',
    1,
    -- input_schema: JSON Schema defining what parameters this collector accepts
    '{
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "title": "REST API Collector Configuration",
        "required": ["url", "method", "interval_seconds"],
        "properties": {
            "url": {
                "type": "string",
                "format": "uri",
                "title": "API Endpoint URL",
                "description": "The full URL of the REST API endpoint to poll"
            },
            "method": {
                "type": "string",
                "enum": ["GET", "POST"],
                "default": "GET",
                "title": "HTTP Method"
            },
            "headers": {
                "type": "object",
                "title": "Request Headers",
                "description": "Additional HTTP headers to include",
                "additionalProperties": { "type": "string" }
            },
            "request_body": {
                "type": "object",
                "title": "Request Body",
                "description": "JSON body for POST requests"
            },
            "auth_type": {
                "type": "string",
                "enum": ["NONE", "BEARER_TOKEN", "API_KEY", "BASIC"],
                "default": "NONE",
                "title": "Authentication Type"
            },
            "auth_config": {
                "type": "object",
                "title": "Authentication Configuration",
                "properties": {
                    "token": { "type": "string", "title": "Bearer Token or API Key" },
                    "username": { "type": "string", "title": "Username (Basic Auth)" },
                    "password": { "type": "string", "title": "Password (Basic Auth)" },
                    "api_key_header": { "type": "string", "title": "API Key Header Name", "default": "X-API-Key" }
                }
            },
            "interval_seconds": {
                "type": "integer",
                "minimum": 10,
                "maximum": 86400,
                "default": 300,
                "title": "Polling Interval (seconds)",
                "description": "How often to poll the API endpoint"
            },
            "timeout_seconds": {
                "type": "integer",
                "minimum": 1,
                "maximum": 300,
                "default": 30,
                "title": "Request Timeout (seconds)"
            },
            "pagination": {
                "type": "object",
                "title": "Pagination Settings",
                "properties": {
                    "enabled": { "type": "boolean", "default": false },
                    "type": { "type": "string", "enum": ["OFFSET", "CURSOR", "PAGE_NUMBER"] },
                    "page_size": { "type": "integer", "minimum": 1, "maximum": 10000, "default": 100 },
                    "max_pages": { "type": "integer", "minimum": 1, "default": 10 }
                }
            },
            "response_data_path": {
                "type": "string",
                "title": "Response Data Path",
                "description": "JSONPath expression to extract data array from response (e.g. $.data.items)"
            }
        }
    }'::jsonb,
    -- ui_schema: hints for the Web UI form renderer
    '{
        "ui:order": ["url", "method", "auth_type", "auth_config", "interval_seconds", "timeout_seconds", "headers", "request_body", "pagination", "response_data_path"],
        "url": {
            "ui:placeholder": "https://api.example.com/v1/data",
            "ui:help": "Enter the full URL including query parameters if needed"
        },
        "method": {
            "ui:widget": "radio"
        },
        "auth_type": {
            "ui:widget": "select"
        },
        "auth_config": {
            "token": { "ui:widget": "password" },
            "password": { "ui:widget": "password" }
        },
        "interval_seconds": {
            "ui:widget": "range",
            "ui:options": { "min": 10, "max": 86400, "step": 10 }
        },
        "timeout_seconds": {
            "ui:widget": "updown"
        },
        "headers": {
            "ui:options": { "orderable": false }
        },
        "request_body": {
            "ui:widget": "textarea",
            "ui:options": { "rows": 5 }
        }
    }'::jsonb,
    -- output_schema: what this collector produces
    '{
        "$schema": "http://json-schema.org/draft-07/schema#",
        "type": "object",
        "properties": {
            "status_code": {
                "type": "integer",
                "description": "HTTP response status code"
            },
            "response_headers": {
                "type": "object",
                "description": "HTTP response headers"
            },
            "data": {
                "type": ["array", "object"],
                "description": "Extracted response data (after applying response_data_path)"
            },
            "record_count": {
                "type": "integer",
                "description": "Number of records/items collected"
            },
            "fetched_at": {
                "type": "string",
                "format": "date-time",
                "description": "Timestamp when the data was fetched"
            },
            "pagination_info": {
                "type": "object",
                "properties": {
                    "total_pages_fetched": { "type": "integer" },
                    "has_more": { "type": "boolean" }
                }
            }
        }
    }'::jsonb,
    -- default_config
    '{
        "method": "GET",
        "auth_type": "NONE",
        "interval_seconds": 300,
        "timeout_seconds": 30,
        "pagination": { "enabled": false }
    }'::jsonb,
    'PLUGIN',
    'vessel.plugins.collectors.rest_api',
    true
);

COMMIT;
