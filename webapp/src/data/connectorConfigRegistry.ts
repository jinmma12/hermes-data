import { StageType } from '../types';

import csvJsonConverterManifest from '../../../plugins/csv-json-converter/hermes-plugin.json';
import fileOutputManifest from '../../../plugins/file-output/hermes-plugin.json';
import fileWatcherManifest from '../../../plugins/file-watcher/hermes-plugin.json';
import jsonTransformManifest from '../../../plugins/json-transform/hermes-plugin.json';
import mergeContentManifest from '../../../plugins/merge-content/hermes-plugin.json';
import passthroughManifest from '../../../plugins/passthrough/hermes-plugin.json';
import restApiCollectorManifest from '../../../plugins/rest-api-collector/hermes-plugin.json';
import splitRecordsManifest from '../../../plugins/split-records/hermes-plugin.json';
import ftpSftpCollectorManifest from '../../../plugins/community-examples/ftp-sftp-collector/hermes-plugin.json';

export type PropertyType = 'text' | 'password' | 'number' | 'select' | 'textarea';
export type PropertyFormat = 'line_list';

export interface PropertyDef {
  key: string;
  path?: string;
  label: string;
  type: PropertyType;
  defaultValue: string | number | boolean;
  tooltip: string;
  options?: string[];
  group?: string;
  placeholder?: string;
  format?: PropertyFormat;
}

export interface ConnectorConfig {
  label: string;
  connectionSettings: PropertyDef[];
  runtimePolicy: PropertyDef[];
  recipeProperties: PropertyDef[];
}

interface JsonSchema {
  type?: string;
  title?: string;
  description?: string;
  default?: unknown;
  enum?: string[];
  properties?: Record<string, JsonSchema>;
  items?: JsonSchema;
}

interface PluginManifest {
  name?: string;
  input_schema?: JsonSchema;
  settings_schema?: JsonSchema;
}

interface ManifestOverrides {
  label?: string;
  connectionKeys?: string[];
  runtimeKeys?: string[];
}

function titleFromKey(key: string): string {
  return key
    .split(/[_.-]/g)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function defaultValueForSchema(schema: JsonSchema): string | number | boolean {
  if (schema.default !== undefined && typeof schema.default !== 'object') {
    return schema.default as string | number | boolean;
  }
  if (schema.enum?.length) return schema.enum[0];
  if (schema.type === 'boolean') return false;
  if (schema.type === 'integer' || schema.type === 'number') return 0;
  return '';
}

function propertyTypeFromSchema(path: string, schema: JsonSchema): PropertyType {
  if (schema.enum?.length || schema.type === 'boolean') return 'select';
  if (schema.type === 'integer' || schema.type === 'number') return 'number';
  if (schema.type === 'array' && schema.items?.type === 'string') return 'textarea';
  if (/(password|token|secret|passphrase|connection_string)/i.test(path)) return 'password';
  return 'text';
}

function buildSchemaProperties(
  schema: JsonSchema | undefined,
  options: { prefix?: string; group?: string; fallbackGroup: string },
): PropertyDef[] {
  if (!schema?.properties) return [];

  return Object.entries(schema.properties).flatMap(([key, property]) => {
    const path = options.prefix ? `${options.prefix}.${key}` : key;
    const group = property.title && property.type === 'object'
      ? property.title
      : options.group ?? schema.title ?? options.fallbackGroup;

    if (property.type === 'object' && property.properties) {
      return buildSchemaProperties(property, {
        prefix: path,
        group: property.title ?? group,
        fallbackGroup: property.title ?? group,
      });
    }

    return [{
      key: path,
      path,
      label: property.title ?? titleFromKey(key),
      type: propertyTypeFromSchema(path, property),
      defaultValue: defaultValueForSchema(property),
      tooltip: property.description ?? '',
      options: property.type === 'boolean' ? ['true', 'false'] : property.enum,
      group,
      format: property.type === 'array' && property.items?.type === 'string' ? 'line_list' : undefined,
    } satisfies PropertyDef];
  });
}

function fromManifest(manifest: PluginManifest, overrides: ManifestOverrides = {}): ConnectorConfig {
  const label = overrides.label ?? manifest.name ?? 'Connector';
  const settingsProps = buildSchemaProperties(manifest.settings_schema, { fallbackGroup: 'Connection' });
  const recipeProps = buildSchemaProperties(manifest.input_schema, { fallbackGroup: 'Configuration' });
  const connectionKeys = new Set(overrides.connectionKeys ?? []);
  const runtimeKeys = new Set(overrides.runtimeKeys ?? []);

  let connectionSettings = settingsProps;
  let runtimePolicy: PropertyDef[] = [];

  if (connectionKeys.size > 0 || runtimeKeys.size > 0) {
    connectionSettings = settingsProps.filter((property) => !runtimeKeys.has(property.key));
    runtimePolicy = settingsProps.filter((property) => runtimeKeys.has(property.key));

    if (connectionKeys.size > 0) {
      connectionSettings = settingsProps.filter((property) => connectionKeys.has(property.key));
      runtimePolicy = settingsProps.filter((property) => runtimeKeys.has(property.key));
    }
  }

  return {
    label,
    connectionSettings,
    runtimePolicy,
    recipeProperties: recipeProps,
  };
}

const manifestConnectorConfigs: Record<string, ConnectorConfig> = {
  'ftp-sftp-collector': fromManifest(ftpSftpCollectorManifest as PluginManifest, {
    label: 'FTP/SFTP Collector',
    runtimeKeys: [
      'poll_interval',
      'connection_timeout_seconds',
      'data_timeout_seconds',
      'max_concurrent_downloads',
      'retry_max_attempts',
      'retry_base_delay_seconds',
      'retry_max_delay_seconds',
      'circuit_breaker_threshold',
      'circuit_breaker_recovery_seconds',
    ],
  }),
  'file-watcher': fromManifest(fileWatcherManifest as PluginManifest, { label: 'File Watcher' }),
  'rest-api-collector': fromManifest(restApiCollectorManifest as PluginManifest, { label: 'REST API Collector' }),
  'file-output': fromManifest(fileOutputManifest as PluginManifest, { label: 'File Output' }),
  'json-transform': fromManifest(jsonTransformManifest as PluginManifest, { label: 'JSON Transform' }),
  'merge-content': fromManifest(mergeContentManifest as PluginManifest, { label: 'Merge Content' }),
  'split-records': fromManifest(splitRecordsManifest as PluginManifest, { label: 'Split Records' }),
  'csv-json-converter': fromManifest(csvJsonConverterManifest as PluginManifest, { label: 'CSV-JSON Converter' }),
  passthrough: fromManifest(passthroughManifest as PluginManifest, { label: 'Passthrough' }),
};

const fallbackConnectorConfigs: Record<string, ConnectorConfig> = {
  'kafka-consumer': {
    label: 'Kafka Consumer',
    connectionSettings: [
      { key: 'bootstrap_servers', label: 'Bootstrap Servers', type: 'text', defaultValue: 'localhost:9092', tooltip: 'Broker addresses', group: 'Connection' },
      { key: 'group_id', label: 'Consumer Group', type: 'text', defaultValue: 'hermes-collect', tooltip: 'Consumer group ID', group: 'Connection' },
      { key: 'security_protocol', label: 'Security Protocol', type: 'select', defaultValue: 'PLAINTEXT', tooltip: 'Kafka security', options: ['PLAINTEXT', 'SSL', 'SASL_PLAINTEXT', 'SASL_SSL'], group: 'Connection' },
    ],
    runtimePolicy: [
      { key: 'poll_timeout_ms', label: 'Poll Timeout (ms)', type: 'number', defaultValue: 1000, tooltip: 'Max wait per poll', group: 'Scheduling' },
      { key: 'max_poll_records', label: 'Max Poll Records', type: 'number', defaultValue: 500, tooltip: 'Records per poll', group: 'Scheduling' },
    ],
    recipeProperties: [
      { key: 'topics', label: 'Topics', type: 'text', defaultValue: 'equipment-data', tooltip: 'Comma-separated topic names', group: 'Subscription' },
      { key: 'auto_offset_reset', label: 'Auto Offset Reset', type: 'select', defaultValue: 'latest', tooltip: 'Start position if no committed offset exists', options: ['earliest', 'latest'], group: 'Subscription' },
    ],
  },
  'database-poller': {
    label: 'Database CDC',
    connectionSettings: [
      { key: 'connection_string', label: 'Connection String', type: 'password', defaultValue: '', tooltip: 'DB connection string', group: 'Connection' },
    ],
    runtimePolicy: [
      { key: 'poll_interval', label: 'Poll Interval', type: 'text', defaultValue: '1m', tooltip: 'Change detection frequency', group: 'Scheduling' },
    ],
    recipeProperties: [
      { key: 'table_name', label: 'Table Name', type: 'text', defaultValue: 'orders', tooltip: 'Table to poll', group: 'Query' },
      { key: 'cursor_column', label: 'Cursor Column', type: 'text', defaultValue: 'updated_at', tooltip: 'Change tracking column', group: 'Query' },
      { key: 'batch_size', label: 'Batch Size', type: 'number', defaultValue: 100, tooltip: 'Max rows per poll', group: 'Query' },
    ],
  },
  'kafka-producer': {
    label: 'Kafka Producer',
    connectionSettings: [
      { key: 'bootstrap_servers', label: 'Bootstrap Servers', type: 'text', defaultValue: 'localhost:9092', tooltip: 'Broker addresses', group: 'Connection' },
    ],
    runtimePolicy: [],
    recipeProperties: [
      { key: 'topic', label: 'Topic', type: 'text', defaultValue: 'output-events', tooltip: 'Target topic', group: 'Publishing' },
      { key: 'key_field', label: 'Key Field', type: 'text', defaultValue: '', tooltip: 'Message key field', group: 'Publishing' },
      { key: 'acks', label: 'Acks', type: 'select', defaultValue: 'all', tooltip: 'Ack level', options: ['0', '1', 'all'], group: 'Publishing' },
      { key: 'compression', label: 'Compression', type: 'select', defaultValue: 'none', tooltip: 'Compression', options: ['none', 'gzip', 'snappy', 'lz4', 'zstd'], group: 'Publishing' },
      { key: 'enable_idempotence', label: 'Idempotent', type: 'select', defaultValue: true, tooltip: 'Exactly-once semantics', options: ['true', 'false'], group: 'Publishing' },
    ],
  },
  'db-writer': {
    label: 'Database Writer',
    connectionSettings: [
      { key: 'connection_string', label: 'Connection String', type: 'password', defaultValue: '', tooltip: 'DB connection string', group: 'Connection' },
      { key: 'provider', label: 'Provider', type: 'select', defaultValue: 'PostgreSQL', tooltip: 'Database type', options: ['PostgreSQL', 'SqlServer'], group: 'Connection' },
    ],
    runtimePolicy: [
      { key: 'timeout_seconds', label: 'Timeout (sec)', type: 'number', defaultValue: 30, tooltip: 'Query timeout', group: 'Delivery' },
    ],
    recipeProperties: [
      { key: 'table_name', label: 'Table Name', type: 'text', defaultValue: 'output_data', tooltip: 'Target table', group: 'Write' },
      { key: 'write_mode', label: 'Write Mode', type: 'select', defaultValue: 'INSERT', tooltip: 'INSERT, UPSERT, or MERGE', options: ['INSERT', 'UPSERT', 'MERGE'], group: 'Write' },
      { key: 'conflict_key', label: 'Conflict Key', type: 'text', defaultValue: 'id', tooltip: 'UPSERT conflict column', group: 'Write' },
      { key: 'batch_size', label: 'Batch Size', type: 'number', defaultValue: 1000, tooltip: 'Records per batch', group: 'Write' },
    ],
  },
  'webhook-sender': {
    label: 'Webhook Sender',
    connectionSettings: [
      { key: 'auth_type', label: 'Authentication', type: 'select', defaultValue: 'none', tooltip: 'Auth method', options: ['none', 'bearer', 'basic', 'api_key'], group: 'Connection' },
      { key: 'auth_token', label: 'Auth Token', type: 'password', defaultValue: '', tooltip: 'Token or key', group: 'Connection' },
    ],
    runtimePolicy: [
      { key: 'timeout_seconds', label: 'Timeout (sec)', type: 'number', defaultValue: 30, tooltip: 'Request timeout', group: 'Delivery' },
      { key: 'max_retries', label: 'Max Retries', type: 'number', defaultValue: 3, tooltip: 'Retry with backoff', group: 'Delivery' },
    ],
    recipeProperties: [
      { key: 'url', label: 'Webhook URL', type: 'text', defaultValue: 'https://api.partner.com/webhook', tooltip: 'Target endpoint', group: 'Endpoint' },
      { key: 'method', label: 'Method', type: 'select', defaultValue: 'POST', tooltip: 'HTTP method', options: ['POST', 'PUT', 'PATCH'], group: 'Endpoint' },
      { key: 'batch_mode', label: 'Batch Mode', type: 'select', defaultValue: false, tooltip: 'Send all records in one request', options: ['true', 'false'], group: 'Endpoint' },
    ],
  },
};

export const connectorConfigs: Record<string, ConnectorConfig> = {
  ...fallbackConnectorConfigs,
  ...manifestConnectorConfigs,
};

export const genericConfigs: Record<StageType, ConnectorConfig> = {
  [StageType.COLLECT]: {
    label: 'Collector',
    connectionSettings: [],
    runtimePolicy: [],
    recipeProperties: [
      { key: 'execution_type', label: 'Execution Type', type: 'select', defaultValue: 'plugin', tooltip: 'How to execute', options: ['plugin', 'script', 'http'], group: 'Execution' },
      { key: 'execution_ref', label: 'Execution Ref', type: 'text', defaultValue: '', tooltip: 'Plugin or script reference', group: 'Execution' },
    ],
  },
  [StageType.PROCESS]: {
    label: 'Process',
    connectionSettings: [],
    runtimePolicy: [],
    recipeProperties: [
      { key: 'execution_type', label: 'Execution Type', type: 'select', defaultValue: 'plugin', tooltip: 'How to execute', options: ['plugin', 'script', 'http', 'docker'], group: 'Execution' },
      { key: 'execution_ref', label: 'Execution Ref', type: 'text', defaultValue: 'PROCESS:anomaly-detector', tooltip: 'Plugin or script reference', group: 'Execution' },
      { key: 'max_execution_time', label: 'Max Execution Time', type: 'text', defaultValue: '300s', tooltip: 'Timeout', group: 'Execution' },
      { key: 'input_format', label: 'Input Format', type: 'select', defaultValue: 'json', tooltip: 'Expected format', options: ['json', 'csv', 'raw'], group: 'Execution' },
    ],
  },
  [StageType.EXPORT]: {
    label: 'Export',
    connectionSettings: [],
    runtimePolicy: [],
    recipeProperties: [
      { key: 'destination_type', label: 'Destination', type: 'select', defaultValue: 's3', tooltip: 'Export target', options: ['s3', 'database', 'webhook', 'file'], group: 'Destination' },
      { key: 'format', label: 'Output Format', type: 'select', defaultValue: 'json', tooltip: 'Data format', options: ['json', 'csv', 'parquet'], group: 'Destination' },
      { key: 'compression', label: 'Compression', type: 'select', defaultValue: 'gzip', tooltip: 'Compression', options: ['none', 'gzip', 'snappy', 'zstd'], group: 'Destination' },
    ],
  },
};

export function getConnectorConfig(connectorCode: string | undefined, stageType: StageType): ConnectorConfig {
  if (connectorCode && connectorConfigs[connectorCode]) {
    return connectorConfigs[connectorCode];
  }
  return genericConfigs[stageType];
}
