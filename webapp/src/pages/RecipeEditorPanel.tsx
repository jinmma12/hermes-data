import { useEffect, useMemo, useState } from 'react';

import { getConnectorConfig, type ConnectorConfig, type PropertyDef } from '../data/connectorConfigRegistry';
import { StageType } from '../types';

// ============================================================
// Types
// ============================================================

type OnErrorAction = 'STOP' | 'SKIP' | 'RETRY';
type BulletinLevel = 'DEBUG' | 'INFO' | 'WARN' | 'ERROR';
type TabId = 'SETTINGS' | 'PROPERTIES';

export interface ProcessSettings {
  name: string;
  is_enabled: boolean;
  on_error: OnErrorAction;
  retry_count: number;
  retry_delay_seconds: number;
  penalty_duration: string;
  yield_duration: string;
  bulletin_level: BulletinLevel;
}

export interface ConnectorConfigState {
  processSettings: ProcessSettings;
  connectionConfig: Record<string, unknown>;
  runtimePolicy: Record<string, unknown>;
  recipeConfig: Record<string, unknown>;
}

interface ProcessorConfigProps {
  stageId: number;
  refId: number;
  stageType: StageType;
  processorName?: string;
  connectorCode?: string;
  initialTab?: TabId;
  processSettings?: ProcessSettings;
  initialConnectionConfig?: Record<string, unknown>;
  initialRuntimePolicy?: Record<string, unknown>;
  initialRecipeConfig?: Record<string, unknown>;
  onClose: () => void;
  onSaveConfig?: (config: ConnectorConfigState) => void;
}

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
  PROPERTIES: { label: 'Properties', headerClass: 'bg-blue-600', borderClass: 'border-blue-500' },
};

const STAGE_META: Record<StageType, { label: string; color: string }> = {
  [StageType.COLLECT]: { label: 'Collector', color: 'blue' },
  [StageType.PROCESS]: { label: 'Process', color: 'purple' },
  [StageType.EXPORT]: { label: 'Export', color: 'emerald' },
};

// ============================================================
// Helpers
// ============================================================

function deepClone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

function getPath(def: PropertyDef): string {
  return def.path ?? def.key;
}

function parsePrimitive(raw: string, def: PropertyDef): unknown {
  if (def.format === 'line_list') {
    return raw
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
  }
  if (def.type === 'number') {
    return raw === '' ? 0 : Number(raw);
  }
  if (def.type === 'select' && (raw === 'true' || raw === 'false')) {
    return raw === 'true';
  }
  return raw;
}

function normalizeDefault(def: PropertyDef): unknown {
  if (def.format === 'line_list') {
    if (Array.isArray(def.defaultValue)) return def.defaultValue;
    return String(def.defaultValue)
      .split('\n')
      .map((line) => line.trim())
      .filter(Boolean);
  }
  return def.defaultValue;
}

function setByPath(target: Record<string, unknown>, path: string, value: unknown): Record<string, unknown> {
  const parts = path.split('.');
  const next = deepClone(target);
  let current: Record<string, unknown> = next;

  for (let idx = 0; idx < parts.length - 1; idx += 1) {
    const part = parts[idx];
    const existing = current[part];
    if (!existing || Array.isArray(existing) || typeof existing !== 'object') {
      current[part] = {};
    }
    current = current[part] as Record<string, unknown>;
  }

  current[parts[parts.length - 1]] = value;
  return next;
}

function getByPath(source: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((current, part) => {
    if (current && typeof current === 'object' && !Array.isArray(current)) {
      return (current as Record<string, unknown>)[part];
    }
    return undefined;
  }, source);
}

function buildInitialConfig(properties: PropertyDef[], initial?: Record<string, unknown>): Record<string, unknown> {
  let result: Record<string, unknown> = {};

  for (const property of properties) {
    const path = getPath(property);
    const existing = initial ? getByPath(initial, path) : undefined;
    const value = existing === undefined ? normalizeDefault(property) : existing;
    result = setByPath(result, path, value);
  }

  return result;
}

function formatValueForInput(value: unknown, property: PropertyDef): string {
  if (property.format === 'line_list') {
    if (Array.isArray(value)) return value.map((item) => String(item)).join('\n');
    return typeof value === 'string' ? value : '';
  }
  if (typeof value === 'boolean') return value ? 'true' : 'false';
  if (value === null || value === undefined) return '';
  return String(value);
}

function groupNames(properties: PropertyDef[]): string[] {
  return [...new Set(properties.map((property) => property.group).filter(Boolean) as string[])];
}

// ============================================================
// Property Table
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

function renderPropertyInput(property: PropertyDef, value: unknown, onChange: (nextValue: unknown) => void) {
  const formattedValue = formatValueForInput(value, property);

  if (property.type === 'select') {
    return (
      <select
        className="rounded border border-slate-300 px-2 py-1 text-xs"
        value={formattedValue}
        onChange={(event) => onChange(parsePrimitive(event.target.value, property))}
      >
        {property.options?.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    );
  }

  if (property.type === 'password') {
    return (
      <input
        type="password"
        className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
        value={formattedValue}
        placeholder={property.placeholder}
        onChange={(event) => onChange(event.target.value)}
      />
    );
  }

  if (property.type === 'number') {
    return (
      <input
        type="number"
        className="w-28 rounded border border-slate-300 px-2 py-1 text-xs"
        value={formattedValue}
        placeholder={property.placeholder}
        onChange={(event) => onChange(parsePrimitive(event.target.value, property))}
      />
    );
  }

  if (property.type === 'textarea') {
    return (
      <textarea
        className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
        value={formattedValue}
        placeholder={property.placeholder}
        rows={Math.max(3, formattedValue.split('\n').length)}
        onChange={(event) => onChange(parsePrimitive(event.target.value, property))}
      />
    );
  }

  return (
    <input
      type="text"
      className="w-full rounded border border-slate-300 px-2 py-1 text-xs"
      value={formattedValue}
      placeholder={property.placeholder}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}

function PropertyGroup({
  title,
  properties,
  color = 'slate',
  values,
  onChange,
}: {
  title: string;
  properties: PropertyDef[];
  color?: string;
  values: Record<string, unknown>;
  onChange: (path: string, value: unknown) => void;
}) {
  const headerBg = color === 'blue' ? 'bg-blue-50' : color === 'amber' ? 'bg-amber-50' : 'bg-slate-50';
  const headerText = color === 'blue' ? 'text-blue-700' : color === 'amber' ? 'text-amber-700' : 'text-slate-600';
  const headerBorder = color === 'blue' ? 'border-blue-200' : color === 'amber' ? 'border-amber-200' : 'border-slate-300';

  return (
    <div className="mb-3 overflow-hidden rounded-lg border border-slate-200">
      <div className={`flex border-b ${headerBorder} ${headerBg}`}>
        <div className={`w-[180px] shrink-0 border-r ${headerBorder} px-3 py-2 text-[10px] font-bold uppercase tracking-wider ${headerText}`}>
          {title}
        </div>
        <div className={`flex-1 px-3 py-2 text-[10px] font-bold uppercase tracking-wider ${headerText}`}>Value</div>
      </div>
      {properties.map((property, index) => {
        const path = getPath(property);
        return (
          <PropertyRow key={path} label={property.label} tooltip={property.tooltip} even={index % 2 === 0}>
            {renderPropertyInput(property, getByPath(values, path), (nextValue) => onChange(path, nextValue))}
          </PropertyRow>
        );
      })}
    </div>
  );
}

function SettingsTabContent({
  settings,
  onChangeSettings,
  connectionConfig,
  onChangeConnectionConfig,
  runtimePolicy,
  onChangeRuntimePolicy,
  connectorConfig,
}: {
  settings: ProcessSettings;
  onChangeSettings: (settings: ProcessSettings) => void;
  connectionConfig: Record<string, unknown>;
  onChangeConnectionConfig: (path: string, value: unknown) => void;
  runtimePolicy: Record<string, unknown>;
  onChangeRuntimePolicy: (path: string, value: unknown) => void;
  connectorConfig: ConnectorConfig;
}) {
  const connGroups = groupNames(connectorConfig.connectionSettings);
  const runtimeGroups = groupNames(connectorConfig.runtimePolicy);

  const update = <K extends keyof ProcessSettings>(key: K, value: ProcessSettings[K]) => {
    onChangeSettings({ ...settings, [key]: value });
  };

  return (
    <div className="flex flex-col gap-3 p-4">
      <div className="overflow-hidden rounded-lg border border-slate-200">
        <div className="flex border-b border-slate-300 bg-slate-100">
          <div className="w-[180px] shrink-0 border-r border-slate-300 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Instance</div>
          <div className="flex-1 px-3 py-2 text-[10px] font-bold uppercase tracking-wider text-slate-500">Value</div>
        </div>
        <PropertyRow label="Name" tooltip="Display name for this processor instance" even={true}>
          <input className="w-full rounded border border-slate-300 px-2 py-1 text-xs" value={settings.name} onChange={(event) => update('name', event.target.value)} />
        </PropertyRow>
        <PropertyRow label="Enabled" tooltip="Whether this processor is active" even={false}>
          <button
            onClick={() => update('is_enabled', !settings.is_enabled)}
            className={`rounded px-3 py-1 text-xs font-medium ${settings.is_enabled ? 'bg-green-100 text-green-700' : 'bg-slate-200 text-slate-500'}`}
          >
            {settings.is_enabled ? 'Enabled' : 'Disabled'}
          </button>
        </PropertyRow>
        <PropertyRow label="On Error" tooltip="STOP, SKIP, or RETRY on failure" even={true}>
          <select className="rounded border border-slate-300 px-2 py-1 text-xs" value={settings.on_error} onChange={(event) => update('on_error', event.target.value as OnErrorAction)}>
            <option value="STOP">STOP</option>
            <option value="SKIP">SKIP</option>
            <option value="RETRY">RETRY</option>
          </select>
        </PropertyRow>
        <PropertyRow label="Retry Count" tooltip="Retry attempts before failure" even={false}>
          <input type="number" min={0} className="w-20 rounded border border-slate-300 px-2 py-1 text-xs" value={settings.retry_count} onChange={(event) => update('retry_count', parseInt(event.target.value, 10) || 0)} />
        </PropertyRow>
      </div>

      {connGroups.length > 0 ? connGroups.map((group) => (
        <PropertyGroup
          key={group}
          title={group}
          properties={connectorConfig.connectionSettings.filter((property) => property.group === group)}
          color="blue"
          values={connectionConfig}
          onChange={onChangeConnectionConfig}
        />
      )) : connectorConfig.connectionSettings.length > 0 ? (
        <PropertyGroup title="Connection" properties={connectorConfig.connectionSettings} color="blue" values={connectionConfig} onChange={onChangeConnectionConfig} />
      ) : null}

      {runtimeGroups.length > 0 ? runtimeGroups.map((group) => (
        <PropertyGroup
          key={group}
          title={group}
          properties={connectorConfig.runtimePolicy.filter((property) => property.group === group)}
          color="amber"
          values={runtimePolicy}
          onChange={onChangeRuntimePolicy}
        />
      )) : connectorConfig.runtimePolicy.length > 0 ? (
        <PropertyGroup title="Runtime Policy" properties={connectorConfig.runtimePolicy} color="amber" values={runtimePolicy} onChange={onChangeRuntimePolicy} />
      ) : null}
    </div>
  );
}

// ============================================================
// JSON Editor
// ============================================================

function JsonPreview({ data }: { data: unknown }) {
  const highlighted = useMemo(() => {
    const raw = JSON.stringify(data, null, 2);
    return raw
      .replace(/("(?:\\.|[^"\\])*")\s*:/g, '<span class="text-purple-400">$1</span>:')
      .replace(/:\s*("(?:\\.|[^"\\])*")/g, ': <span class="text-green-400">$1</span>')
      .replace(/:\s*(\d+\.?\d*)/g, ': <span class="text-blue-400">$1</span>')
      .replace(/:\s*(true|false|null)/g, ': <span class="text-amber-400">$1</span>');
  }, [data]);

  return (
    <pre className="overflow-auto rounded-lg bg-slate-900 p-3 font-mono text-[11px] leading-5 text-slate-300" dangerouslySetInnerHTML={{ __html: highlighted }} />
  );
}

function JsonConfigEditor({
  connectorCode,
  value,
  onChange,
}: {
  connectorCode?: string;
  value: Record<string, unknown>;
  onChange: (nextValue: Record<string, unknown>) => void;
}) {
  const canonicalJson = useMemo(() => JSON.stringify(value, null, 2), [value]);
  const [jsonText, setJsonText] = useState(canonicalJson);
  const [isEditing, setIsEditing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!isEditing) {
      setJsonText(canonicalJson);
    }
  }, [canonicalJson, isEditing]);

  const validate = (text: string) => {
    try {
      JSON.parse(text);
      setError(null);
      return true;
    } catch (issue) {
      setError((issue as Error).message);
      return false;
    }
  };

  const apply = () => {
    if (!validate(jsonText)) return;
    onChange(JSON.parse(jsonText) as Record<string, unknown>);
    setIsEditing(false);
  };

  return (
    <div className="mt-4">
      <div className="mb-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">JSON Config</span>
          {connectorCode && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[9px] font-mono text-slate-500">{connectorCode}</span>}
        </div>
        <div className="flex items-center gap-1">
          {isEditing ? (
            <>
              <button onClick={() => { setJsonText(canonicalJson); setError(null); setIsEditing(false); }} className="rounded border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-500 hover:bg-slate-50">Cancel</button>
              <button onClick={apply} className="rounded border border-blue-200 bg-blue-50 px-2 py-0.5 text-[10px] font-medium text-blue-700 hover:bg-blue-100">Apply</button>
            </>
          ) : (
            <button onClick={() => setIsEditing(true)} className="rounded border border-slate-200 px-2 py-0.5 text-[10px] font-medium text-slate-500 hover:bg-slate-50">Edit JSON</button>
          )}
        </div>
      </div>
      {isEditing ? (
        <div>
          <textarea
            value={jsonText}
            onChange={(event) => { setJsonText(event.target.value); validate(event.target.value); }}
            spellCheck={false}
            className={`w-full rounded-lg border p-3 font-mono text-[11px] leading-5 focus:outline-none focus:ring-1 ${error ? 'border-red-300 bg-red-50 text-red-900 focus:ring-red-400' : 'border-slate-300 bg-slate-900 text-slate-200 focus:ring-blue-400'}`}
            rows={Math.min(24, jsonText.split('\n').length + 2)}
          />
          {error && (
            <div className="mt-1 flex items-center gap-1 text-[10px] text-red-600">
              <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z" /></svg>
              {error}
            </div>
          )}
        </div>
      ) : (
        <JsonPreview data={value} />
      )}
    </div>
  );
}

// ============================================================
// Main Panel Component
// ============================================================

export default function RecipeEditorPanel({
  stageType,
  processorName,
  connectorCode,
  initialTab,
  processSettings: initialProcessSettings,
  initialConnectionConfig,
  initialRuntimePolicy,
  initialRecipeConfig,
  onClose,
  onSaveConfig,
}: RecipeEditorPanelProps) {
  const [activeTab, setActiveTab] = useState<TabId>(initialTab ?? 'SETTINGS');
  const config = getConnectorConfig(connectorCode, stageType);

  const [processSettings, setProcessSettings] = useState<ProcessSettings>(initialProcessSettings ?? DEFAULT_SETTINGS);
  const [connectionConfig, setConnectionConfig] = useState<Record<string, unknown>>(() => buildInitialConfig(config.connectionSettings, initialConnectionConfig));
  const [runtimePolicy, setRuntimePolicy] = useState<Record<string, unknown>>(() => buildInitialConfig(config.runtimePolicy, initialRuntimePolicy));
  const [recipeConfig, setRecipeConfig] = useState<Record<string, unknown>>(() => buildInitialConfig(config.recipeProperties, initialRecipeConfig));
  const [hasChanges, setHasChanges] = useState(false);

  useEffect(() => {
    setActiveTab(initialTab ?? 'SETTINGS');
    setProcessSettings(initialProcessSettings ?? DEFAULT_SETTINGS);
    setConnectionConfig(buildInitialConfig(config.connectionSettings, initialConnectionConfig));
    setRuntimePolicy(buildInitialConfig(config.runtimePolicy, initialRuntimePolicy));
    setRecipeConfig(buildInitialConfig(config.recipeProperties, initialRecipeConfig));
    setHasChanges(false);
  }, [config, initialConnectionConfig, initialProcessSettings, initialRecipeConfig, initialRuntimePolicy, initialTab, stageType]);

  const stageMeta = STAGE_META[stageType];
  const recipeGroups = groupNames(config.recipeProperties);
  const tabStyle = TAB_CONFIG[activeTab];

  const updateProcessSettings = (next: ProcessSettings) => {
    setProcessSettings(next);
    setHasChanges(true);
  };

  const updateConnectionConfig = (path: string, value: unknown) => {
    setConnectionConfig((current) => setByPath(current, path, value));
    setHasChanges(true);
  };

  const updateRuntimePolicy = (path: string, value: unknown) => {
    setRuntimePolicy((current) => setByPath(current, path, value));
    setHasChanges(true);
  };

  const updateRecipePath = (path: string, value: unknown) => {
    setRecipeConfig((current) => setByPath(current, path, value));
    setHasChanges(true);
  };

  const updateRecipeConfig = (next: Record<string, unknown>) => {
    setRecipeConfig(next);
    setHasChanges(true);
  };

  const applyChanges = () => {
    onSaveConfig?.({ processSettings, connectionConfig, runtimePolicy, recipeConfig });
    setHasChanges(false);
  };

  return (
    <div className="flex w-[480px] flex-col border-l border-slate-200 bg-white">
      <div className={`flex items-center justify-between px-4 py-3 text-white ${tabStyle.headerClass}`}>
        <div>
          <div className="flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-white/60" />
            <h3 className="text-sm font-semibold">{processorName ?? stageMeta.label}</h3>
          </div>
          <p className="mt-0.5 text-[11px] text-white/70">{config.label} Configuration</p>
        </div>
        <button onClick={onClose} className="rounded-lg p-1.5 text-white/70 transition-colors hover:bg-white/10 hover:text-white">
          <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <div className="flex border-b border-slate-200 bg-slate-50">
        {(Object.entries(TAB_CONFIG) as [TabId, typeof TAB_CONFIG[TabId]][]).map(([id, cfg]) => (
          <button
            key={id}
            onClick={() => setActiveTab(id)}
            className={`relative flex-1 px-4 py-2.5 text-xs font-semibold uppercase tracking-wider transition-colors ${activeTab === id ? 'bg-white text-slate-800' : 'text-slate-500 hover:text-slate-700'}`}
          >
            {cfg.label}
            {activeTab === id && <span className={`absolute bottom-0 left-0 right-0 h-0.5 ${cfg.headerClass}`} />}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto">
        {activeTab === 'SETTINGS' && (
          <SettingsTabContent
            settings={processSettings}
            onChangeSettings={updateProcessSettings}
            connectionConfig={connectionConfig}
            onChangeConnectionConfig={updateConnectionConfig}
            runtimePolicy={runtimePolicy}
            onChangeRuntimePolicy={updateRuntimePolicy}
            connectorConfig={config}
          />
        )}
        {activeTab === 'PROPERTIES' && (
          <div className="p-4">
            {recipeGroups.length > 0 ? recipeGroups.map((group) => (
              <PropertyGroup
                key={group}
                title={group}
                properties={config.recipeProperties.filter((property) => property.group === group)}
                color="blue"
                values={recipeConfig}
                onChange={updateRecipePath}
              />
            )) : config.recipeProperties.length > 0 ? (
              <PropertyGroup title="Configuration" properties={config.recipeProperties} color="blue" values={recipeConfig} onChange={updateRecipePath} />
            ) : (
              <div className="rounded-lg border-2 border-dashed border-slate-200 py-8 text-center">
                <p className="text-xs text-slate-400">No recipe properties for this connector type</p>
              </div>
            )}
            <JsonConfigEditor connectorCode={connectorCode} value={recipeConfig} onChange={updateRecipeConfig} />
          </div>
        )}
      </div>

      <div className="border-t border-slate-200 bg-slate-50 px-4 py-3">
        <button
          onClick={applyChanges}
          disabled={!hasChanges}
          className={`flex w-full items-center justify-center gap-2 rounded-lg px-4 py-2.5 text-xs font-semibold shadow-sm transition-colors ${hasChanges ? 'bg-blue-600 text-white hover:bg-blue-700' : 'bg-slate-200 text-slate-500 cursor-not-allowed'}`}
        >
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 12.75l6 6 9-13.5" />
          </svg>
          Apply Changes
        </button>
      </div>
    </div>
  );
}
