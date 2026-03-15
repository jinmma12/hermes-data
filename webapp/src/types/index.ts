// ============================================================
// Enums
// ============================================================

export enum StageType {
  COLLECT = 'COLLECT',
  ALGORITHM = 'ALGORITHM',
  TRANSFER = 'TRANSFER',
}

export enum ExecutionType {
  PLUGIN = 'PLUGIN',
  SCRIPT = 'SCRIPT',
  HTTP = 'HTTP',
  DOCKER = 'DOCKER',
  NIFI_FLOW = 'NIFI_FLOW',
  INTERNAL = 'INTERNAL',
}

export enum MonitoringType {
  FILE_MONITOR = 'FILE_MONITOR',
  API_POLL = 'API_POLL',
  DB_POLL = 'DB_POLL',
  EVENT_STREAM = 'EVENT_STREAM',
}

export enum DefinitionStatus {
  ACTIVE = 'ACTIVE',
  DEPRECATED = 'DEPRECATED',
  DRAFT = 'DRAFT',
}

export enum PipelineStatus {
  DRAFT = 'DRAFT',
  ACTIVE = 'ACTIVE',
  PAUSED = 'PAUSED',
  ARCHIVED = 'ARCHIVED',
}

export enum ActivationStatus {
  STARTING = 'STARTING',
  RUNNING = 'RUNNING',
  STOPPING = 'STOPPING',
  STOPPED = 'STOPPED',
  ERROR = 'ERROR',
}

export enum JobStatus {
  DETECTED = 'DETECTED',
  QUEUED = 'QUEUED',
  PROCESSING = 'PROCESSING',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
}

export enum ExecutionStatus {
  RUNNING = 'RUNNING',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
  CANCELLED = 'CANCELLED',
}

export enum StageExecutionStatus {
  RUNNING = 'RUNNING',
  COMPLETED = 'COMPLETED',
  FAILED = 'FAILED',
  SKIPPED = 'SKIPPED',
}

export enum TriggerType {
  INITIAL = 'INITIAL',
  RETRY = 'RETRY',
  REPROCESS = 'REPROCESS',
}

export enum OnErrorAction {
  STOP = 'STOP',
  SKIP = 'SKIP',
  RETRY = 'RETRY',
}

export enum ReprocessStatus {
  PENDING = 'PENDING',
  APPROVED = 'APPROVED',
  EXECUTING = 'EXECUTING',
  DONE = 'DONE',
  REJECTED = 'REJECTED',
}

export enum EventType {
  INFO = 'INFO',
  WARN = 'WARN',
  ERROR = 'ERROR',
  DEBUG = 'DEBUG',
}

export enum SourceType {
  FILE = 'FILE',
  API_RESPONSE = 'API_RESPONSE',
  DB_CHANGE = 'DB_CHANGE',
  EVENT = 'EVENT',
}

// ============================================================
// Definition Layer
// ============================================================

export interface CollectorDefinition {
  id: number;
  code: string;
  name: string;
  description: string;
  category: string;
  icon_url: string | null;
  status: DefinitionStatus;
  created_at: string;
  versions?: DefinitionVersion[];
}

export interface AlgorithmDefinition {
  id: number;
  code: string;
  name: string;
  description: string;
  category: string;
  icon_url: string | null;
  status: DefinitionStatus;
  created_at: string;
  versions?: DefinitionVersion[];
}

export interface TransferDefinition {
  id: number;
  code: string;
  name: string;
  description: string;
  category: string;
  icon_url: string | null;
  status: DefinitionStatus;
  created_at: string;
  versions?: DefinitionVersion[];
}

export interface DefinitionVersion {
  id: number;
  definition_id: number;
  version_no: number;
  input_schema: Record<string, unknown>;
  ui_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  default_config: Record<string, unknown>;
  execution_type: ExecutionType;
  execution_ref: string;
  is_published: boolean;
  created_at: string;
}

// ============================================================
// Instance Layer
// ============================================================

export interface CollectorInstance {
  id: number;
  definition_id: number;
  definition?: CollectorDefinition;
  name: string;
  description: string;
  status: DefinitionStatus;
  created_at: string;
  current_version?: InstanceVersion;
}

export interface AlgorithmInstance {
  id: number;
  definition_id: number;
  definition?: AlgorithmDefinition;
  name: string;
  description: string;
  status: DefinitionStatus;
  created_at: string;
  current_version?: InstanceVersion;
}

export interface TransferInstance {
  id: number;
  definition_id: number;
  definition?: TransferDefinition;
  name: string;
  description: string;
  status: DefinitionStatus;
  created_at: string;
  current_version?: InstanceVersion;
}

export interface InstanceVersion {
  id: number;
  instance_id: number;
  def_version_id: number;
  version_no: number;
  config_json: Record<string, unknown>;
  secret_binding_json: Record<string, unknown>;
  is_current: boolean;
  created_by: string;
  created_at: string;
  change_note: string;
}

// ============================================================
// Pipeline Layer
// ============================================================

export interface PipelineInstance {
  id: number;
  name: string;
  description: string;
  monitoring_type: MonitoringType;
  monitoring_config: Record<string, unknown>;
  status: PipelineStatus;
  created_at: string;
  updated_at: string;
  stages?: PipelineStage[];
  activation?: PipelineActivation | null;
}

export interface PipelineStage {
  id: number;
  pipeline_instance_id: number;
  stage_order: number;
  stage_type: StageType;
  ref_type: string;
  ref_id: number;
  ref_name?: string;
  is_enabled: boolean;
  on_error: OnErrorAction;
  retry_count: number;
  retry_delay_seconds: number;
}

// ============================================================
// Monitoring Layer
// ============================================================

export interface PipelineActivation {
  id: number;
  pipeline_instance_id: number;
  pipeline?: PipelineInstance;
  status: ActivationStatus;
  started_at: string;
  stopped_at: string | null;
  last_heartbeat_at: string | null;
  last_polled_at: string | null;
  error_message: string | null;
  worker_id: string | null;
  job_count?: number;
}

// ============================================================
// Execution Layer
// ============================================================

export interface Job {
  id: number;
  pipeline_activation_id: number;
  pipeline_instance_id: number;
  pipeline_name?: string;
  source_type: SourceType;
  source_key: string;
  source_metadata: Record<string, unknown>;
  dedup_key: string;
  detected_at: string;
  status: JobStatus;
  current_execution_id: number | null;
  execution_count: number;
  last_completed_at: string | null;
}

export interface JobExecution {
  id: number;
  job_id: number;
  execution_no: number;
  trigger_type: TriggerType;
  trigger_source: string;
  status: ExecutionStatus;
  started_at: string;
  ended_at: string | null;
  duration_ms: number | null;
  reprocess_request_id: number | null;
  stages?: JobStageExecution[];
  snapshot?: ExecutionSnapshot;
}

export interface JobStageExecution {
  id: number;
  execution_id: number;
  pipeline_stage_id: number;
  stage_type: StageType;
  stage_order: number;
  status: StageExecutionStatus;
  started_at: string | null;
  ended_at: string | null;
  duration_ms: number | null;
  input_summary: Record<string, unknown> | null;
  output_summary: Record<string, unknown> | null;
  error_code: string | null;
  error_message: string | null;
  retry_attempt: number;
}

export interface ExecutionSnapshot {
  id: number;
  execution_id: number;
  pipeline_config: Record<string, unknown>;
  collector_config: Record<string, unknown>;
  algorithm_config: Record<string, unknown>;
  transfer_config: Record<string, unknown>;
  snapshot_hash: string;
  created_at: string;
}

// ============================================================
// Reprocess
// ============================================================

export interface ReprocessRequest {
  id: number;
  job_id: number;
  requested_by: string;
  requested_at: string;
  reason: string;
  start_from_stage: number | null;
  use_latest_recipe: boolean;
  status: ReprocessStatus;
  approved_by: string | null;
  execution_id: number | null;
}

export interface ReprocessPayload {
  reason: string;
  start_from_stage?: number;
  use_latest_recipe?: boolean;
}

export interface BulkReprocessPayload {
  job_ids: number[];
  reason: string;
}

// ============================================================
// Event Log
// ============================================================

export interface ExecutionEventLog {
  id: number;
  execution_id: number;
  stage_execution_id: number | null;
  event_type: EventType;
  event_code: string;
  message: string;
  detail_json: Record<string, unknown> | null;
  created_at: string;
}

// ============================================================
// Recipe (alias for InstanceVersion config editing)
// ============================================================

export interface Recipe {
  version_no: number;
  config_json: Record<string, unknown>;
  change_note: string;
  is_current: boolean;
  created_by: string;
  created_at: string;
}

// ============================================================
// API Response Wrappers
// ============================================================

export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
}

export interface MonitorStats {
  total_items: number;
  completed_items: number;
  failed_items: number;
  success_rate: number;
  avg_duration_ms: number;
  active_pipelines: number;
}

// ============================================================
// Plugin Marketplace
// ============================================================

export interface PluginInfo {
  name: string;
  version: string;
  type: StageType;
  description: string;
  author: string;
  license: string;
  runtime: string;
  installed: boolean;
  icon_url: string | null;
}
