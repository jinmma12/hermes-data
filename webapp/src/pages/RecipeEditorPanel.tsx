import { useEffect, useMemo, useState } from 'react';
import type { RJSFSchema, UiSchema } from '@rjsf/utils';
import type { ObjectFieldTemplateProps } from '@rjsf/utils';
import Form from '@rjsf/core';
import validator from '@rjsf/validator-ajv8';

import { StageType } from '../types';
import type { Recipe } from '../types';
import RecipeDiffViewer from '../components/recipe/RecipeDiffViewer';

// ============================================================
// Types
// ============================================================

type OnErrorAction = 'STOP' | 'SKIP' | 'RETRY';
type BulletinLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
type TabId = 'SETTINGS' | 'RECIPE' | 'HISTORY';

interface ProcessSettings {
  name: string;
  is_enabled: boolean;
  on_error: OnErrorAction;
  retry_count: number;
  retry_delay_seconds: number;
  penalty_duration: string;
  yield_duration: string;
  bulletin_level: BulletinLevel;
}

interface ProcessorConfigProps {
  stageId: number;
  refId: number;
  stageType: StageType;
  processorName?: string;
  processSettings?: ProcessSettings;
  onClose: () => void;
  onSaveSettings?: (settings: ProcessSettings) => void;
  onSaveRecipe?: (config: unknown, changeNote: string) => void;
}

// Backward compat: old prop shape still works
interface RecipeEditorPanelProps extends ProcessorConfigProps {}

// ============================================================
// Constants
// ============================================================

const DEFAULT_SETTINGS: ProcessSettings = {
  name: 'Unnamed Processor',
  is_enabled: true,
  on_error: 'STOP',
  retry_count: 3,
  retry_delay_seconds: 10,
  penalty_duration: '30s',
  yield_duration: '1s',
  bulletin_level: 'WARN',
};

const TAB_CONFIG: Record<TabId, { label: string; headerClass: string; borderClass: string }> = {
  SETTINGS: { label: 'Settings', headerClass: 'bg-slate-600', borderClass: 'border-slate-500' },
  RECIPE: { label: 'Recipe', headerClass: 'bg-blue-600', borderClass: 'border-blue-500' },
  HISTORY: { label: 'History', headerClass: 'bg-purple-600', borderClass: 'border-purple-500' },
};

const STAGE_META: Record<StageType, { label: string; color: string }> = {
  [StageType.COLLECT]: { label: 'Collector', color: 'blue' },
  [StageType.ALGORITHM]: { label: 'Algorithm', color: 'purple' },
  [StageType.TRANSFER]: { label: 'Transfer', color: 'emerald' },
};

// ============================================================
// Demo data (same schemas, used when no live API)
// ============================================================

// Processor Properties = HOW the processor works (goes into SETTINGS tab)
// These are stable, processor-type-specific configuration
const processorProperties: Record<StageType, { label: string; properties: { key: string; label: string; type: string; value: string; tooltip: string; options?: string[] }[] }> = {
  [StageType.COLLECT]: {
    label: 'Collector Properties',
    properties: [
      { key: 'url', label: 'API URL', type: 'text', value: 'https://vendor-a.com/api/orders', tooltip: 'The REST API endpoint to poll' },
      { key: 'method', label: 'HTTP Method', type: 'select', value: 'GET', tooltip: 'HTTP method for requests', options: ['GET', 'POST', 'PUT'] },
      { key: 'interval', label: 'Poll Interval', type: 'text', value: '5m', tooltip: 'How often to check for new data (e.g. 30s, 5m, 1h)' },
      { key: 'timeout', label: 'Timeout (seconds)', type: 'number', value: '30', tooltip: 'Request timeout in seconds' },
      { key: 'auth_type', label: 'Authentication', type: 'select', value: 'bearer', tooltip: 'Authentication method', options: ['none', 'bearer', 'basic', 'api_key'] },
      { key: 'auth_token', label: 'Auth Token', type: 'password', value: '••••••••', tooltip: 'Authentication token or API key' },
      { key: 'path_filter_regex', label: 'Path Filter (Regex)', type: 'text', value: '', tooltip: 'Regex pattern to filter file paths' },
      { key: 'file_filter_regex', label: 'File Filter (Regex)', type: 'text', value: '.*\\.csv$', tooltip: 'Regex pattern to filter filenames' },
    ],
  },
  [StageType.ALGORITHM]: {
    label: 'Algorithm Properties',
    properties: [
      { key: 'execution_type', label: 'Execution Type', type: 'select', value: 'plugin', tooltip: 'How this algorithm is executed', options: ['plugin', 'script', 'http', 'docker'] },
      { key: 'execution_ref', label: 'Execution Reference', type: 'text', value: 'ALGORITHM:anomaly-detector', tooltip: 'Plugin or script reference' },
      { key: 'max_execution_time', label: 'Max Execution Time', type: 'text', value: '300s', tooltip: 'Maximum time before timeout' },
      { key: 'input_format', label: 'Input Format', type: 'select', value: 'json', tooltip: 'Expected input data format', options: ['json', 'csv', 'raw'] },
    ],
  },
  [StageType.TRANSFER]: {
    label: 'Transfer Properties',
    properties: [
      { key: 'destination_type', label: 'Destination Type', type: 'select', value: 's3', tooltip: 'Where to send processed data', options: ['s3', 'database', 'webhook', 'file', 'elasticsearch'] },
      { key: 'bucket', label: 'S3 Bucket', type: 'text', value: 'my-data-bucket', tooltip: 'Target S3 bucket name' },
      { key: 'prefix', label: 'Key Prefix', type: 'text', value: 'results/', tooltip: 'Prefix for S3 object keys' },
      { key: 'format', label: 'Output Format', type: 'select', value: 'json', tooltip: 'Output data format', options: ['json', 'csv', 'parquet'] },
      { key: 'compression', label: 'Compression', type: 'select', value: 'gzip', tooltip: 'Compression algorithm', options: ['none', 'gzip', 'snappy', 'zstd'] },
      { key: 'connection_string', label: 'Connection String', type: 'password', value: '••••••••', tooltip: 'Database or service connection string' },
    ],
  },
};

// Recipe = WHAT the operator tunes (versioned business parameters)
// These change frequently and need versioning + diff
const demoSchemas: Record<StageType, { schema: RJSFSchema; uiSchema: UiSchema; defaultConfig: Record<string, unknown> }> = {
  [StageType.COLLECT]: {
    schema: {
      type: 'object',
      properties: {
        batch_size: { type: 'integer', title: 'Batch Size', default: 100, minimum: 1, maximum: 10000, description: 'Number of records to collect per batch' },
        date_range_days: { type: 'integer', title: 'Date Range (days)', default: 7, description: 'How many days back to collect data' },
        include_deleted: { type: 'boolean', title: 'Include Deleted Records', default: false },
        custom_query_params: { type: 'string', title: 'Custom Query Parameters', description: 'Additional query string (key=value&key2=value2)' },
      },
    },
    uiSchema: { custom_query_params: { 'ui:placeholder': 'status=active&region=us-west' } },
    defaultConfig: { batch_size: 100, date_range_days: 7, include_deleted: false, custom_query_params: '' },
  },
  [StageType.ALGORITHM]: {
    schema: {
      type: 'object',
      properties: {
        threshold: { type: 'number', title: 'Detection Threshold', minimum: 0, maximum: 10, default: 2.5, description: 'Higher values = more lenient detection' },
        method: { type: 'string', title: 'Analysis Method', enum: ['z-score', 'iqr', 'modified-z-score'], default: 'z-score' },
        window_size: { type: 'integer', title: 'Window Size', default: 100, minimum: 10, maximum: 10000, description: 'Number of data points for rolling analysis' },
        sensitivity: { type: 'string', title: 'Sensitivity', enum: ['low', 'medium', 'high'], default: 'medium' },
        alert_on_anomaly: { type: 'boolean', title: 'Alert on Anomaly', default: true },
        min_samples: { type: 'integer', title: 'Min Samples Required', default: 50, description: 'Minimum data points before analysis starts' },
      },
      required: ['threshold', 'method'],
    },
    uiSchema: { threshold: { 'ui:widget': 'range' } },
    defaultConfig: { threshold: 2.5, method: 'z-score', window_size: 100, sensitivity: 'medium', alert_on_anomaly: true, min_samples: 50 },
  },
  [StageType.TRANSFER]: {
    schema: {
      type: 'object',
      properties: {
        batch_mode: { type: 'boolean', title: 'Batch Mode', default: true, description: 'Combine records into batches before transfer' },
        max_batch_size: { type: 'integer', title: 'Max Batch Size', default: 1000 },
        include_metadata: { type: 'boolean', title: 'Include Metadata', default: true, description: 'Add pipeline/execution metadata to output' },
        partition_by: { type: 'string', title: 'Partition By', enum: ['none', 'date', 'source', 'custom'], default: 'date', description: 'How to partition output data' },
        custom_tags: { type: 'string', title: 'Custom Tags', description: 'Comma-separated tags for output data' },
      },
    },
    uiSchema: {},
    defaultConfig: { batch_mode: true, max_batch_size: 1000, include_metadata: true, partition_by: 'date', custom_tags: '' },
  },
};

const demoVersionHistory: Recipe[] = [
  { version_no: 3, config_json: { threshold: 3.5, method: 'modified-z-score', window_size: 200, sensitivity: 'high' }, change_note: 'Switch to modified z-score with larger window', is_current: true, created_by: 'operator:alex', created_at: '2026-03-16T10:15:00Z' },
  { version_no: 2, config_json: { threshold: 3.0, method: 'z-score', window_size: 100 }, change_note: 'Increased threshold from 2.5 to 3.0', is_current: false, created_by: 'operator:kim', created_at: '2026-03-15T14:30:00Z' },
  { version_no: 1, config_json: { threshold: 2.5, method: 'z-score', window_size: 100 }, change_note: 'Initial configuration', is_current: false, created_by: 'admin', created_at: '2026-03-01T09:00:00Z' },
];

// ============================================================
// NiFi-style Property Table Row
// ============================================================

interface PropertyRowProps {
  label: string;
  tooltip?: string;
  even: boolean;
  children: React.ReactNode;
}

function PropertyRow({ label, tooltip, even, children }: PropertyRowProps) {
  return (
    <div className={`flex items-center border-b border-slate-200 ${even ? 'bg-slate-50' : 'bg-white'}`}>
      <div className="flex w-[180px] shrink-0 items-center gap-1.5 border-r border-slate-200 px-3 py-2.5">
        {tooltip && (
          <span className="cursor-help text-slate-400" title={tooltip}>
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
            </svg>
          </span>
        )}
        <span className="text-xs font-medium text-slate-700">{label}</span>
      </div>
      <div className="min-w-0 flex-1 px-3 py-2">{children}</div>
    </div>
  );
}

// ============================================================
// RJSF Custom ObjectFieldTemplate (NiFi property-table style)
// ============================================================

function NiFiObjectFieldTemplate(props: ObjectFieldTemplateProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-slate-200">
      <div className="flex border-b border-slate-300 bg-slate-100">
        <div className="w-[180px] shrink-0 border-r border-slate-300 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
          Property
        </div>
        <div className="flex-1 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">
          Value
        </div>
      </div>
      {props.properties.map((prop, idx) => {
        const schema = props.schema.properties?.[prop.name] as Record<string, unknown> | undefined;
        return (
          <div
            key={prop.name}
            className={`flex items-start border-b border-slate-200 last:border-b-0 ${idx % 2 === 0 ? 'bg-white' : 'bg-slate-50'}`}
          >
            <div className="flex w-[180px] shrink-0 items-center gap-1.5 border-r border-slate-200 px-3 py-2.5">
              {typeof schema?.description === 'string' && (
                <span className="cursor-help text-slate-400" title={schema.description}>
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M11.25 11.25l.041-.02a.75.75 0 011.063.852l-.708 2.836a.75.75 0 001.063.853l.041-.021M21 12a9 9 0 11-18 0 9 9 0 0118 0zm-9-3.75h.008v.008H12V8.25z" />
                  </svg>
                </span>
              )}
              <span className="text-xs font-medium text-slate-700">
                {(schema?.title as string) || prop.name}
              </span>
            </div>
            <div className="min-w-0 flex-1 px-3 py-1.5 [&_input]:!border-slate-300 [&_input]:!text-xs [&_select]:!border-slate-300 [&_select]:!text-xs [&_.field-description]:hidden [&_label]:hidden [&_.form-group]:!mb-0">
              {prop.content}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ============================================================
// JSON Syntax Highlighter (lightweight, no deps)
// ============================================================

function JsonPreview({ data }: { data: unknown }) {
  const highlighted = useMemo(() => {
    const raw = JSON.stringify(data, null, 2);
    return raw.replace(
      /("(?:\\.|[^"\\])*")\s*:/g,
      '<span class="text-purple-700">$1</span>:',
    ).replace(
      /:\s*("(?:\\.|[^"\\])*")/g,
      ': <span class="text-green-700">$1</span>',
    ).replace(
      /:\s*(\d+\.?\d*)/g,
      ': <span class="text-blue-700">$1</span>',
    ).replace(
      /:\s*(true|false|null)/g,
      ': <span class="text-amber-700">$1</span>',
    );
  }, [data]);

  return (
    <pre
      className="overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-5 text-slate-300"
      dangerouslySetInnerHTML={{ __html: highlighted }}
    />
  );
}

// ============================================================
// Settings Tab
// ============================================================

function SettingsTab({
  settings,
  onChange,
  onSave,
}: {
  settings: ProcessSettings;
  onChange: (s: ProcessSettings) => void;
  onSave?: (s: ProcessSettings) => void;
}) {
  const update = <K extends keyof ProcessSettings>(key: K, value: ProcessSettings[K]) => {
    onChange({ ...settings, [key]: value });
  };

  const rows: { label: string; tooltip: string; render: () => React.ReactNode }[] = [
    {
      label: 'Name',
      tooltip: 'Display name for this processor instance',
      render: () => (
        <input className="w-full rounded border border-slate-300 px-2 py-1 text-xs" value={settings.name} onChange={(e) => update('name', e.target.value)} />
      ),
    },
    {
      label: 'Enabled',
      tooltip: 'Whether this processor is active in the pipeline',
      render: () => (
        <button
          onClick={() => update('is_enabled', !settings.is_enabled)}
          className={`rounded px-3 py-1 text-xs font-medium ${settings.is_enabled ? 'bg-green-100 text-green-700' : 'bg-slate-200 text-slate-500'}`}
        >
          {settings.is_enabled ? 'Enabled' : 'Disabled'}
        </button>
      ),
    },
    {
      label: 'On Error',
      tooltip: 'Action when processing fails: STOP halts the pipeline, SKIP moves to next item, RETRY attempts again',
      render: () => (
        <select className="rounded border border-slate-300 px-2 py-1 text-xs" value={settings.on_error} onChange={(e) => update('on_error', e.target.value as OnErrorAction)}>
          <option value="STOP">STOP</option>
          <option value="SKIP">SKIP</option>
          <option value="RETRY">RETRY</option>
        </select>
      ),
    },
    {
      label: 'Retry Count',
      tooltip: 'Number of retry attempts before marking as failed',
      render: () => (
        <input type="number" min={0} max={100} className="w-20 rounded border border-slate-300 px-2 py-1 text-xs" value={settings.retry_count} onChange={(e) => update('retry_count', parseInt(e.target.value) || 0)} />
      ),
    },
    {
      label: 'Retry Delay',
      tooltip: 'Seconds to wait between retry attempts',
      render: () => (
        <div className="flex items-center gap-1">
          <input type="number" min={0} className="w-20 rounded border border-slate-300 px-2 py-1 text-xs" value={settings.retry_delay_seconds} onChange={(e) => update('retry_delay_seconds', parseInt(e.target.value) || 0)} />
          <span className="text-[10px] text-slate-400">sec</span>
        </div>
      ),
    },
    {
      label: 'Penalty Duration',
      tooltip: 'Time a processor is penalized after a failure before accepting new work',
      render: () => (
        <input className="w-24 rounded border border-slate-300 px-2 py-1 text-xs" value={settings.penalty_duration} onChange={(e) => update('penalty_duration', e.target.value)} />
      ),
    },
    {
      label: 'Yield Duration',
      tooltip: 'Time the processor yields when it has no work to do',
      render: () => (
        <input className="w-24 rounded border border-slate-300 px-2 py-1 text-xs" value={settings.yield_duration} onChange={(e) => update('yield_duration', e.target.value)} />
      ),
    },
    {
      label: 'Bulletin Level',
      tooltip: 'Minimum severity level for bulletin board messages',
      render: () => (
        <select className="rounded border border-slate-300 px-2 py-1 text-xs" value={settings.bulletin_level} onChange={(e) => update('bulletin_level', e.target.value as BulletinLevel)}>
          <option value="DEBUG">DEBUG</option>
          <option value="INFO">INFO</option>
          <option value="WARN">WARN</option>
          <option value="ERROR">ERROR</option>
        </select>
      ),
    },
  ];

  return (
    <div className="flex flex-col gap-4 p-4">
      <div className="overflow-hidden rounded-lg border border-slate-200">
        <div className="flex border-b border-slate-300 bg-slate-100">
          <div className="w-[180px] shrink-0 border-r border-slate-300 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Property</div>
          <div className="flex-1 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Value</div>
        </div>
        {rows.map((row, idx) => (
          <PropertyRow key={row.label} label={row.label} tooltip={row.tooltip} even={idx % 2 === 0}>
            {row.render()}
          </PropertyRow>
        ))}
      </div>
      {onSave && (
        <button onClick={() => onSave(settings)} className="btn-primary w-full justify-center">
          Apply Settings
        </button>
      )}
    </div>
  );
}

// ============================================================
// Recipe Tab
// ============================================================

function RecipeTab({
  schema,
  uiSchema,
  formData,
  onFormChange,
  changeNote,
  onChangeNoteUpdate,
  onSave,
}: {
  schema: RJSFSchema;
  uiSchema: UiSchema;
  formData: Record<string, unknown>;
  onFormChange: (data: Record<string, unknown>) => void;
  changeNote: string;
  onChangeNoteUpdate: (note: string) => void;
  onSave: () => void;
}) {
  return (
    <div className="flex flex-col gap-4 p-4">
      <Form
        schema={schema}
        uiSchema={uiSchema}
        formData={formData}
        validator={validator}
        onChange={(e) => onFormChange(e.formData)}
        templates={{ ObjectFieldTemplate: NiFiObjectFieldTemplate }}
        liveValidate
      >
        {/* Hide default submit */}
        <div />
      </Form>

      {/* Config preview */}
      <details className="group">
        <summary className="cursor-pointer text-[10px] font-semibold uppercase tracking-wider text-slate-400 group-open:text-slate-600">
          JSON Preview
        </summary>
        <div className="mt-2">
          <JsonPreview data={formData} />
        </div>
      </details>

      {/* Save controls */}
      <div className="space-y-3 border-t border-slate-200 pt-4">
        <div>
          <label className="mb-1 block text-xs font-medium text-slate-700">Change Note</label>
          <input
            type="text"
            value={changeNote}
            onChange={(e) => onChangeNoteUpdate(e.target.value)}
            placeholder="Describe what changed..."
            className="input"
          />
        </div>
        <button onClick={onSave} className="btn-primary w-full justify-center">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          Save as New Version
        </button>
      </div>
    </div>
  );
}

// ============================================================
// History Tab
// ============================================================

function HistoryTab({
  versions,
  stageLabel,
  onRestore,
}: {
  versions: Recipe[];
  stageLabel: string;
  onRestore: (config: Record<string, unknown>) => void;
}) {
  const [selectedVersion, setSelectedVersion] = useState<number | null>(null);
  const [showDiff, setShowDiff] = useState(false);

  if (showDiff && versions.length >= 2) {
    return (
      <div className="p-4">
        <button
          onClick={() => setShowDiff(false)}
          className="mb-3 flex items-center gap-1 text-xs font-medium text-purple-600 hover:text-purple-700"
        >
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M10.5 19.5L3 12m0 0l7.5-7.5M3 12h18" />
          </svg>
          Back to Timeline
        </button>
        <RecipeDiffViewer
          instanceName={stageLabel}
          versions={versions.map((v) => ({
            version: v.version_no,
            config: v.config_json as Record<string, unknown>,
            created_by: v.created_by,
            change_note: v.change_note,
            created_at: v.created_at,
          }))}
        />
      </div>
    );
  }

  const selected = selectedVersion !== null ? versions.find((v) => v.version_no === selectedVersion) : null;

  return (
    <div className="flex h-full">
      {/* Timeline (left) */}
      <div className="w-[140px] shrink-0 overflow-auto border-r border-slate-200 bg-slate-50">
        {/* Compare button */}
        {versions.length >= 2 && (
          <div className="border-b border-slate-200 p-2">
            <button
              onClick={() => setShowDiff(true)}
              className="flex w-full items-center justify-center gap-1 rounded border border-purple-200 bg-purple-50 px-2 py-1.5 text-[10px] font-medium text-purple-700 hover:bg-purple-100"
            >
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5" />
              </svg>
              Compare
            </button>
          </div>
        )}
        {versions.map((v) => (
          <button
            key={v.version_no}
            onClick={() => setSelectedVersion(v.version_no)}
            className={`flex w-full flex-col border-b border-slate-200 px-3 py-2.5 text-left transition-colors ${
              selectedVersion === v.version_no ? 'bg-white shadow-sm' : 'hover:bg-slate-100'
            }`}
          >
            <div className="flex items-center gap-1.5">
              <span className="rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-bold text-slate-700">
                v{v.version_no}
              </span>
              {v.is_current && (
                <span className="rounded-full bg-green-100 px-1.5 py-0.5 text-[9px] font-bold text-green-700">
                  current
                </span>
              )}
            </div>
            <span className="mt-1 text-[10px] text-slate-500 line-clamp-2">{v.change_note}</span>
            <span className="mt-0.5 text-[9px] text-slate-400">{v.created_by}</span>
            <span className="text-[9px] text-slate-400">
              {new Date(v.created_at).toLocaleDateString()}
            </span>
          </button>
        ))}
      </div>

      {/* Detail (right) */}
      <div className="flex-1 overflow-auto p-4">
        {selected ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="rounded bg-slate-700 px-2 py-0.5 text-xs font-bold text-white">
                  v{selected.version_no}
                </span>
                {selected.is_current && (
                  <span className="rounded-full bg-green-100 px-2 py-0.5 text-[10px] font-bold text-green-700">
                    current
                  </span>
                )}
              </div>
            </div>
            <div className="space-y-1 text-xs text-slate-600">
              <p><span className="font-medium text-slate-500">Author:</span> {selected.created_by}</p>
              <p><span className="font-medium text-slate-500">Date:</span> {new Date(selected.created_at).toLocaleString()}</p>
              <p><span className="font-medium text-slate-500">Note:</span> {selected.change_note}</p>
            </div>
            <JsonPreview data={selected.config_json} />
            {!selected.is_current && (
              <button
                onClick={() => onRestore(selected.config_json as Record<string, unknown>)}
                className="flex w-full items-center justify-center gap-1 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs font-medium text-amber-700 hover:bg-amber-100"
              >
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9 15L3 9m0 0l6-6M3 9h12a6 6 0 010 12h-3" />
                </svg>
                Restore this Version
              </button>
            )}
          </div>
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-400">
            Select a version to inspect
          </div>
        )}
      </div>
    </div>
  );
}

// ============================================================
// Main Panel Component
// ============================================================

export default function RecipeEditorPanel({
  stageType,
  processorName,
  processSettings: initialSettings,
  onClose,
  onSaveSettings,
  onSaveRecipe,
}: RecipeEditorPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>('SETTINGS');
  const [settings, setSettings] = useState<ProcessSettings>(initialSettings ?? DEFAULT_SETTINGS);
  const [formData, setFormData] = useState<Record<string, unknown>>({});
  const [changeNote, setChangeNote] = useState('');
  const [versions, setVersions] = useState<Recipe[]>([]);

  const demoData = demoSchemas[stageType];
  const stageMeta = STAGE_META[stageType];

  useEffect(() => {
    setFormData(demoData.defaultConfig);
    setVersions(demoVersionHistory);
    if (initialSettings) setSettings(initialSettings);
  }, [stageType]);

  function handleSaveRecipe() {
    if (!changeNote.trim()) {
      alert('Please enter a change note.');
      return;
    }
    const newVersion: Recipe = {
      version_no: versions.length + 1,
      config_json: formData,
      change_note: changeNote,
      is_current: true,
      created_by: 'operator',
      created_at: new Date().toISOString(),
    };
    setVersions([newVersion, ...versions.map((v) => ({ ...v, is_current: false }))]);
    setChangeNote('');
    onSaveRecipe?.(formData, changeNote);
    alert('Recipe saved as new version!');
  }

  function handleRestore(config: Record<string, unknown>) {
    setFormData(config);
    setActiveTab('RECIPE');
  }

  const tabStyle = TAB_CONFIG[activeTab];

  return (
    <div className="flex w-[480px] flex-col border-l border-slate-200 bg-white">
      {/* Panel Header */}
      <div className={`flex items-center justify-between px-4 py-3 text-white ${tabStyle.headerClass}`}>
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-white/60" />
            <h3 className="text-sm font-semibold">
              {processorName ?? stageMeta.label}
            </h3>
          </div>
          <p className="mt-0.5 text-[11px] text-white/70">
            {stageMeta.label} Processor Configuration
          </p>
        </div>
        <button
          onClick={onClose}
          className="rounded-lg p-1.5 text-white/70 transition-colors hover:bg-white/10 hover:text-white"
        >
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Tab Bar */}
      <div className="flex border-b border-slate-200 bg-slate-50">
        {(Object.entries(TAB_CONFIG) as [TabId, typeof TAB_CONFIG[TabId]][]).map(([id, cfg]) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`relative flex-1 px-4 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors ${
              activeTab === id
                ? 'bg-white text-slate-800'
                : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {cfg.label}
            {id === 'HISTORY' && <span className="ml-1 text-[10px] font-normal text-slate-400">({versions.length})</span>}
            {activeTab === id && (
              <span className={`absolute bottom-0 left-0 right-0 h-0.5 ${cfg.headerClass}`} />
            )}
          </button>
        ))}
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-auto">
        {activeTab === 'SETTINGS' && (
          <>
            <SettingsTab settings={settings} onChange={setSettings} onSave={onSaveSettings} />
            {/* Processor-specific properties */}
            <div className="border-t border-slate-200 p-4">
              <div className="overflow-hidden rounded-lg border border-slate-200">
                <div className="flex border-b border-slate-300 bg-blue-50">
                  <div className="w-[180px] shrink-0 border-r border-blue-200 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-blue-700">
                    {processorProperties[stageType].label}
                  </div>
                  <div className="flex-1 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-blue-700">Value</div>
                </div>
                {processorProperties[stageType].properties.map((prop, idx) => (
                  <PropertyRow key={prop.key} label={prop.label} tooltip={prop.tooltip} even={idx % 2 === 0}>
                    {prop.type === 'select' ? (
                      <select className="rounded border border-slate-300 px-2 py-1 text-xs" defaultValue={prop.value}>
                        {prop.options?.map(o => <option key={o} value={o}>{o}</option>)}
                      </select>
                    ) : prop.type === 'password' ? (
                      <input type="password" className="w-full rounded border border-slate-300 px-2 py-1 text-xs" defaultValue={prop.value} />
                    ) : prop.type === 'number' ? (
                      <input type="number" className="w-20 rounded border border-slate-300 px-2 py-1 text-xs" defaultValue={prop.value} />
                    ) : (
                      <input type="text" className="w-full rounded border border-slate-300 px-2 py-1 text-xs" defaultValue={prop.value} />
                    )}
                  </PropertyRow>
                ))}
              </div>
            </div>
          </>
        )}
        {activeTab === 'RECIPE' && (
          <RecipeTab
            schema={demoData.schema}
            uiSchema={demoData.uiSchema}
            formData={formData}
            onFormChange={setFormData}
            changeNote={changeNote}
            onChangeNoteUpdate={setChangeNote}
            onSave={handleSaveRecipe}
          />
        )}
        {activeTab === 'HISTORY' && (
          <HistoryTab
            versions={versions}
            stageLabel={processorName ?? stageMeta.label}
            onRestore={handleRestore}
          />
        )}
      </div>
    </div>
  );
}
