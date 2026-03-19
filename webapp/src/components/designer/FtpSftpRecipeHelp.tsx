/**
 * FTP/SFTP Recipe Help: presets, selection summary, pattern help, and path preview.
 *
 * Content sourced from:
 *   docs/FTP_SFTP_UI_HELP_CONTENT.md
 *   docs/FTP_SFTP_RECIPE_EXAMPLES.md
 *   docs/FTP_SFTP_OPERATOR_GUIDE.md
 *
 * This component does NOT invent behavior. It reflects the current regex-based
 * FTP/SFTP collector model as documented and tested.
 */

import { useMemo, useState } from 'react';

// ── Types ───────────────────────────────────────────────────

interface Preset {
  name: string;
  description: string;
  recipe: Record<string, unknown>;
}

interface FtpSftpRecipeHelpProps {
  recipeConfig: Record<string, unknown>;
  onApplyPreset: (recipe: Record<string, unknown>) => void;
}

// ── Presets (from FTP_SFTP_RECIPE_EXAMPLES.md) ──────────────

const PRESETS: Preset[] = [
  {
    name: 'Root CSV Pickup',
    description: 'Flat folder, CSV files only, unseen files',
    recipe: {
      remote_path: '/data/incoming',
      recursive: false,
      file_filter: { filename_regex: '.*\\.csv$' },
      discovery_mode: 'ALL_NEW',
    },
  },
  {
    name: 'Recursive CSV Tree',
    description: 'Scan all subdirectories for CSV files',
    recipe: {
      remote_path: '/data',
      recursive: true,
      max_depth: -1,
      file_filter: { filename_regex: '.*\\.csv$' },
      discovery_mode: 'ALL_NEW',
    },
  },
  {
    name: 'Equipment Paths Only',
    description: 'Path regex filters to equipment_* folders',
    recipe: {
      remote_path: '/data',
      recursive: true,
      max_depth: -1,
      file_filter: {
        filename_regex: 'sensor_.*\\.csv$',
        path_regex: '.*/equipment_[A-Z]+/.*',
      },
      discovery_mode: 'ALL_NEW',
    },
  },
  {
    name: 'Recent Date Folders',
    description: 'Date-partitioned folders, last 7 days',
    recipe: {
      remote_path: '/data',
      recursive: true,
      folder_pattern: { enabled: true, format: 'yyyyMMdd', lookback_days: 7, timezone: 'UTC' },
      file_filter: { filename_regex: '.*\\.csv$' },
      discovery_mode: 'ALL_NEW',
    },
  },
  {
    name: 'Marker File Collection',
    description: 'Wait for .done companion file before collecting',
    recipe: {
      remote_path: '/data',
      recursive: true,
      file_filter: { filename_regex: '^[^.]*\\.csv$' },
      completion_check: { strategy: 'MARKER_FILE', marker_suffix: '.done' },
      discovery_mode: 'ALL_NEW',
    },
  },
  {
    name: 'Latest File Only',
    description: 'Pick only the newest matching file each poll',
    recipe: {
      remote_path: '/data',
      recursive: true,
      file_filter: { filename_regex: '.*\\.json$' },
      ordering: 'NEWEST_FIRST',
      discovery_mode: 'LATEST',
    },
  },
  {
    name: 'Batch Collection',
    description: 'Collect up to N files each poll cycle',
    recipe: {
      remote_path: '/data',
      recursive: true,
      file_filter: { filename_regex: '.*\\.json$' },
      ordering: 'OLDEST_FIRST',
      discovery_mode: 'BATCH',
      batch_size: 50,
    },
  },
  {
    name: 'Archive After Collect',
    description: 'Move files to /archive after successful collection',
    recipe: {
      remote_path: '/data',
      recursive: true,
      file_filter: {
        filename_regex: '.*\\.csv$',
        exclude_patterns: ['\\.tmp$', '^\\.', '\\.bak$'],
        exclude_zero_byte: true,
      },
      post_action: { action: 'MOVE', move_target: '/archive', conflict_resolution: 'TIMESTAMP' },
      discovery_mode: 'ALL_NEW',
    },
  },
];

// ── Selection Summary Builder ───────────────────────────────

function buildSummary(config: Record<string, unknown>): string[] {
  const lines: string[] = [];
  const remotePath = config.remote_path || config.remotePath || '/';
  const recursive = config.recursive;
  const maxDepth = config.max_depth ?? config.maxDepth;
  const fileFilter = (config.file_filter || config.fileFilter || {}) as Record<string, unknown>;
  const folderPattern = (config.folder_pattern || config.folderPattern || {}) as Record<string, unknown>;
  const completionCheck = (config.completion_check || config.completionCheck || {}) as Record<string, unknown>;
  const postAction = (config.post_action || config.postAction || {}) as Record<string, unknown>;
  const discoveryMode = config.discovery_mode || config.discoveryMode;
  const batchSize = config.batch_size || config.batchSize;

  lines.push(`Start from ${remotePath}`);

  if (recursive) {
    const depth = maxDepth === -1 || maxDepth === undefined ? 'unlimited' : `${maxDepth} levels`;
    lines.push(`Traverse recursively (depth: ${depth})`);
  } else {
    lines.push('Scan root directory only (not recursive)');
  }

  if (folderPattern && folderPattern.enabled) {
    lines.push(`Date folders: ${folderPattern.format}, last ${folderPattern.lookback_days || folderPattern.lookbackDays} days`);
  }

  if (fileFilter.filename_regex || fileFilter.filenameRegex) {
    lines.push(`Accept filenames matching: ${fileFilter.filename_regex || fileFilter.filenameRegex}`);
  }
  if (fileFilter.path_regex || fileFilter.pathRegex) {
    lines.push(`Accept paths matching: ${fileFilter.path_regex || fileFilter.pathRegex}`);
  }
  if (fileFilter.min_size_bytes || fileFilter.minSizeBytes) {
    lines.push(`Min file size: ${fileFilter.min_size_bytes || fileFilter.minSizeBytes} bytes`);
  }
  if (fileFilter.max_age_hours || fileFilter.maxAgeHours) {
    lines.push(`Max age: ${fileFilter.max_age_hours || fileFilter.maxAgeHours} hours`);
  }

  const excludes = (fileFilter.exclude_patterns || fileFilter.excludePatterns || []) as string[];
  if (excludes.length > 0) {
    lines.push(`Exclude patterns: ${excludes.join(', ')}`);
  }
  if (fileFilter.exclude_zero_byte || fileFilter.excludeZeroByte) {
    lines.push('Exclude zero-byte files');
  }

  if (completionCheck.strategy && completionCheck.strategy !== 'NONE') {
    if (completionCheck.strategy === 'MARKER_FILE') {
      lines.push(`Require marker file: ${completionCheck.marker_suffix || completionCheck.markerSuffix || '.done'}`);
    } else if (completionCheck.strategy === 'SIZE_STABLE') {
      lines.push(`Wait for size stability: ${completionCheck.stable_seconds || completionCheck.stableSeconds || 10}s`);
    }
  }

  if (postAction.action && postAction.action !== 'KEEP') {
    if (postAction.action === 'MOVE') lines.push(`After collect: move to ${postAction.move_target || postAction.moveTarget}`);
    else if (postAction.action === 'DELETE') lines.push('After collect: delete file');
    else if (postAction.action === 'RENAME') lines.push(`After collect: rename with ${postAction.rename_suffix || postAction.renameSuffix}`);
  }

  if (discoveryMode) {
    const modeDesc: Record<string, string> = {
      ALL: 'Select all matching files every poll',
      LATEST: 'Select only the newest file',
      BATCH: `Select up to ${batchSize || 'N'} files per poll`,
      ALL_NEW: 'Select only not-yet-seen files',
    };
    lines.push(modeDesc[discoveryMode as string] || `Discovery: ${discoveryMode}`);
  }

  return lines;
}

// ── Folder Pattern Date Matching ─────────────────────────────

/** Supported date formats: yyyyMMdd, yyyy/MM/dd, yyyy-MM-dd */
function generateDateStrings(format: string, lookbackDays: number, tz?: string): string[] {
  const dates: string[] = [];
  const now = new Date();
  // Simple timezone offset: if tz contains 'Seoul' or 'KST', add 9h
  if (tz && /(Seoul|KST|Asia\/Seoul)/i.test(tz)) {
    now.setHours(now.getHours() + 9);
  }
  for (let d = 0; d < lookbackDays; d++) {
    const dt = new Date(now);
    dt.setDate(dt.getDate() - d);
    const yyyy = dt.getFullYear().toString();
    const mm = (dt.getMonth() + 1).toString().padStart(2, '0');
    const dd = dt.getDate().toString().padStart(2, '0');
    if (format === 'yyyyMMdd') dates.push(`${yyyy}${mm}${dd}`);
    else if (format === 'yyyy/MM/dd') dates.push(`${yyyy}/${mm}/${dd}`);
    else if (format === 'yyyy-MM-dd') dates.push(`${yyyy}-${mm}-${dd}`);
    else dates.push(`${yyyy}${mm}${dd}`); // fallback
  }
  return dates;
}

function matchesFolderPattern(path: string, folderPattern: Record<string, unknown>): { pass: boolean; reason: string } {
  if (!folderPattern.enabled) return { pass: true, reason: '' };
  const format = (folderPattern.format as string) || 'yyyyMMdd';
  const lookback = (folderPattern.lookback_days ?? folderPattern.lookbackDays ?? 7) as number;
  const tz = (folderPattern.timezone as string) || 'UTC';
  const dateStrings = generateDateStrings(format, lookback, tz);

  const matched = dateStrings.some((ds) => path.includes(ds));
  if (matched) {
    return { pass: true, reason: `Folder date matches (format: ${format}, lookback: ${lookback}d)` };
  }
  return { pass: false, reason: `No date match in path for ${format} within last ${lookback} days` };
}

// ── Path Preview Tester ─────────────────────────────────────

function testPath(path: string, config: Record<string, unknown>): { match: boolean; reasons: string[] } {
  const reasons: string[] = [];
  const fileFilter = (config.file_filter || config.fileFilter || {}) as Record<string, unknown>;
  const folderPattern = (config.folder_pattern || config.folderPattern || {}) as Record<string, unknown>;
  const filename = path.split('/').pop() || '';

  // folder_pattern check (date-based folder filtering)
  if (folderPattern && folderPattern.enabled) {
    const fpResult = matchesFolderPattern(path, folderPattern);
    if (!fpResult.pass) {
      return { match: false, reasons: [fpResult.reason] };
    }
    reasons.push(fpResult.reason);
  }

  // filename regex
  const filenameRegex = (fileFilter.filename_regex || fileFilter.filenameRegex) as string | undefined;
  if (filenameRegex) {
    try {
      const re = new RegExp(filenameRegex);
      if (re.test(filename)) {
        reasons.push(`Filename matches: ${filenameRegex}`);
      } else {
        return { match: false, reasons: [...reasons, `Filename "${filename}" does not match: ${filenameRegex}`] };
      }
    } catch {
      reasons.push(`Invalid regex: ${filenameRegex}`);
    }
  }

  // path regex
  const pathRegex = (fileFilter.path_regex || fileFilter.pathRegex) as string | undefined;
  if (pathRegex) {
    try {
      const re = new RegExp(pathRegex);
      if (re.test(path)) {
        reasons.push(`Path matches: ${pathRegex}`);
      } else {
        return { match: false, reasons: [...reasons, `Path "${path}" does not match: ${pathRegex}`] };
      }
    } catch {
      reasons.push(`Invalid regex: ${pathRegex}`);
    }
  }

  // exclude patterns
  const excludes = (fileFilter.exclude_patterns || fileFilter.excludePatterns || []) as string[];
  for (const pattern of excludes) {
    try {
      if (new RegExp(pattern).test(filename)) {
        return { match: false, reasons: [...reasons, `Excluded by pattern: ${pattern}`] };
      }
    } catch { /* skip invalid */ }
  }

  if (reasons.length === 0) reasons.push('No filters applied — file accepted');
  return { match: true, reasons };
}

// ── Main Component ──────────────────────────────────────────

export default function FtpSftpRecipeHelp({ recipeConfig, onApplyPreset }: FtpSftpRecipeHelpProps) {
  const [activeSection, setActiveSection] = useState<'presets' | 'help' | 'preview'>('presets');
  const [testPaths, setTestPaths] = useState('/data/equipment_A/sensor_01.csv\n/data/logs/debug.tmp\n/data/20260319/report.csv');

  const summary = useMemo(() => buildSummary(recipeConfig), [recipeConfig]);

  const pathResults = useMemo(() => {
    return testPaths
      .split('\n')
      .map((p) => p.trim())
      .filter(Boolean)
      .map((path) => ({ path, ...testPath(path, recipeConfig) }));
  }, [testPaths, recipeConfig]);

  return (
    <div className="space-y-3">
      {/* Selection Summary */}
      <div className="rounded-lg border border-slate-200 bg-slate-50 p-3">
        <div className="mb-1.5 flex items-center gap-1.5">
          <svg className="h-3.5 w-3.5 text-slate-500" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" />
          </svg>
          <span className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Selection Summary</span>
        </div>
        {summary.length > 0 ? (
          <ul className="space-y-0.5">
            {summary.map((line, i) => (
              <li key={i} className="flex items-start gap-1.5 text-[11px] text-slate-700">
                <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-slate-400" />
                <span className="font-mono">{line}</span>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-[11px] text-slate-400">Configure recipe fields to see a summary</p>
        )}
      </div>

      {/* Section Tabs */}
      <div className="flex gap-1 rounded-lg bg-slate-100 p-0.5">
        {(['presets', 'help', 'preview'] as const).map((s) => (
          <button
            key={s}
            onClick={() => setActiveSection(s)}
            className={`flex-1 rounded-md px-2 py-1.5 text-[10px] font-semibold uppercase tracking-wider transition-colors ${
              activeSection === s ? 'bg-white text-slate-800 shadow-sm' : 'text-slate-500 hover:text-slate-700'
            }`}
          >
            {s === 'presets' ? 'Presets' : s === 'help' ? 'Help' : 'Path Test'}
          </button>
        ))}
      </div>

      {/* Presets Section */}
      {activeSection === 'presets' && (
        <div className="space-y-1.5">
          {PRESETS.map((preset) => (
            <button
              key={preset.name}
              onClick={() => onApplyPreset(preset.recipe)}
              className="flex w-full items-start gap-3 rounded-lg border border-slate-200 bg-white p-2.5 text-left transition-colors hover:border-blue-300 hover:bg-blue-50"
            >
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded bg-blue-100 text-blue-600">
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m2.25 0H5.625c-.621 0-1.125.504-1.125 1.125v17.25c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9z" />
                </svg>
              </div>
              <div className="min-w-0">
                <p className="text-xs font-semibold text-slate-800">{preset.name}</p>
                <p className="text-[10px] text-slate-500">{preset.description}</p>
              </div>
            </button>
          ))}
        </div>
      )}

      {/* Help Section */}
      {activeSection === 'help' && (
        <div className="space-y-3 text-[11px] text-slate-700">
          {/* Pattern Help */}
          <div className="rounded-lg border border-amber-200 bg-amber-50 p-3">
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-amber-700">Regex-Based Selection</p>
            <p className="text-amber-800">FTP/SFTP collection in Hermes uses <strong>regex</strong>, not shell glob patterns.</p>
            <ul className="mt-2 space-y-1">
              <li><code className="rounded bg-amber-100 px-1 text-[10px]">filename_regex</code> — matches file names only</li>
              <li><code className="rounded bg-amber-100 px-1 text-[10px]">path_regex</code> — matches the full remote path</li>
              <li><code className="rounded bg-amber-100 px-1 text-[10px]">folder_pattern</code> — date-based folders only</li>
              <li><code className="rounded bg-amber-100 px-1 text-[10px]">recursive + max_depth</code> — tree traversal control</li>
              <li><code className="rounded bg-amber-100 px-1 text-[10px]">completion_check</code> — prevents partial file pickup</li>
            </ul>
          </div>

          {/* Field Guidance */}
          <div className="space-y-2">
            <div>
              <p className="font-semibold text-slate-800">filename_regex vs path_regex</p>
              <p className="text-slate-600"><code className="bg-slate-100 px-1 text-[10px]">filename_regex</code> checks only the file name (e.g. <code>sensor_01.csv</code>). Use when folder structure doesn&apos;t matter.</p>
              <p className="mt-0.5 text-slate-600"><code className="bg-slate-100 px-1 text-[10px]">path_regex</code> checks the full path (e.g. <code>/data/equipment_A/sensor_01.csv</code>). Use when you need to filter by folder.</p>
            </div>
            <div>
              <p className="font-semibold text-slate-800">Common Regex Examples</p>
              <div className="mt-1 overflow-hidden rounded border border-slate-200">
                {[
                  ['.*\\.csv$', 'All CSV files'],
                  ['sensor_.*\\.csv$', 'Sensor CSV files'],
                  ['data_\\d{8}\\.json$', 'Date-named JSON (data_20260319.json)'],
                  ['.*\\.(csv|json)$', 'CSV or JSON files'],
                  ['.*/equipment_[A-Z]+/.*', 'Equipment folders (path_regex)'],
                ].map(([regex, desc], i) => (
                  <div key={i} className={`flex items-center gap-3 px-2.5 py-1.5 ${i % 2 === 0 ? 'bg-slate-50' : 'bg-white'}`}>
                    <code className="shrink-0 rounded bg-slate-200 px-1.5 py-0.5 text-[10px] font-mono text-slate-800">{regex}</code>
                    <span className="text-[10px] text-slate-500">{desc}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <p className="font-semibold text-slate-800">Discovery Mode</p>
              <ul className="mt-1 space-y-0.5">
                <li><code className="bg-slate-100 px-1 text-[10px]">ALL_NEW</code> — only not-yet-seen files (recommended default)</li>
                <li><code className="bg-slate-100 px-1 text-[10px]">LATEST</code> — only the newest file each poll</li>
                <li><code className="bg-slate-100 px-1 text-[10px]">BATCH</code> — up to N files per poll</li>
                <li><code className="bg-slate-100 px-1 text-[10px]">ALL</code> — every matching file every poll (caution: may re-collect)</li>
              </ul>
            </div>
            {/* Completion & Post-Action */}
            <div>
              <p className="font-semibold text-slate-800">Completion Check</p>
              <ul className="mt-1 space-y-0.5">
                <li><code className="bg-slate-100 px-1 text-[10px]">NONE</code> — collect immediately (no safety check)</li>
                <li><code className="bg-slate-100 px-1 text-[10px]">MARKER_FILE</code> — requires a companion file (e.g. <code>data.csv.done</code>) to exist before collecting</li>
                <li><code className="bg-slate-100 px-1 text-[10px]">SIZE_STABLE</code> — waits until file size stops changing for the configured duration</li>
              </ul>
              <p className="mt-1 text-[10px] text-slate-500">Completion checks are runtime-only and cannot be fully simulated in the local path preview.</p>
            </div>
            <div>
              <p className="font-semibold text-slate-800">Post-Collection Action</p>
              <p className="text-slate-600">These are actions taken on the <em>remote server</em> after successful collection. They are not file selection rules.</p>
              <ul className="mt-1 space-y-0.5">
                <li><code className="bg-slate-100 px-1 text-[10px]">KEEP</code> — leave file in place</li>
                <li><code className="bg-slate-100 px-1 text-[10px]">MOVE</code> — move to archive directory</li>
                <li><code className="bg-slate-100 px-1 text-[10px]">RENAME</code> — add suffix (e.g. <code>.processed</code>)</li>
                <li><code className="bg-slate-100 px-1 text-[10px]">DELETE</code> — remove after collection</li>
              </ul>
              <p className="mt-1 text-[10px] text-slate-500">Post-collection actions are remote server mutations and are never part of the preview.</p>
            </div>
            {/* Operator Warnings */}
            <div className="rounded-lg border border-red-200 bg-red-50 p-3">
              <p className="mb-1 text-[10px] font-bold uppercase tracking-wider text-red-700">Operator Warnings</p>
              <ul className="space-y-0.5 text-red-800">
                <li>ALL mode may repeatedly pick up the same files</li>
                <li>ALL_NEW depends on collector state — validate in restart scenarios</li>
                <li>Marker-file mode is safer than immediate pickup for slow uploads</li>
                <li>Use path_regex when folder structure matters, filename_regex when only naming matters</li>
              </ul>
            </div>
          </div>
        </div>
      )}

      {/* Path Preview Section */}
      {activeSection === 'preview' && (
        <div className="space-y-2">
          {/* Local Preview Only badge */}
          <div className="flex items-center gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2">
            <svg className="h-4 w-4 shrink-0 text-amber-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
            </svg>
            <div>
              <p className="text-[10px] font-bold text-amber-800">Local Preview Only</p>
              <p className="text-[10px] text-amber-700">This tests your regex and folder pattern rules against sample paths you provide. It does not connect to the actual FTP/SFTP server.</p>
            </div>
          </div>

          <textarea
            value={testPaths}
            onChange={(e) => setTestPaths(e.target.value)}
            placeholder="Paste sample paths, one per line..."
            className="w-full rounded-lg border border-slate-300 bg-white p-2.5 font-mono text-[11px] leading-5 text-slate-800 placeholder:text-slate-400 focus:border-blue-400 focus:outline-none focus:ring-1 focus:ring-blue-400"
            rows={4}
          />
          <div className="space-y-1">
            {pathResults.map(({ path, match, reasons }, i) => (
              <div
                key={i}
                className={`flex items-start gap-2 rounded-lg border p-2 ${
                  match ? 'border-green-200 bg-green-50' : 'border-red-200 bg-red-50'
                }`}
              >
                <span className={`mt-0.5 shrink-0 text-xs font-bold ${match ? 'text-green-600' : 'text-red-500'}`}>
                  {match ? 'MATCH' : 'SKIP'}
                </span>
                <div className="min-w-0">
                  <p className="truncate font-mono text-[10px] text-slate-800">{path}</p>
                  {reasons.map((r, j) => (
                    <p key={j} className="text-[10px] text-slate-500">{r}</p>
                  ))}
                </div>
              </div>
            ))}
          </div>

          {/* Preview Scope */}
          <div className="mt-2 rounded-lg border border-slate-200 bg-slate-50 p-3">
            <p className="mb-1.5 text-[10px] font-bold uppercase tracking-wider text-slate-500">Preview Scope</p>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-[10px]">
              <div>
                <p className="font-semibold text-green-700">Covers</p>
                <ul className="mt-0.5 space-y-0.5 text-slate-600">
                  <li>Filename regex matching</li>
                  <li>Path regex matching</li>
                  <li>Exclude patterns</li>
                  <li>Folder pattern (date matching)</li>
                </ul>
              </div>
              <div>
                <p className="font-semibold text-amber-700">Does Not Cover</p>
                <ul className="mt-0.5 space-y-0.5 text-slate-600">
                  <li>Actual remote file listing</li>
                  <li>Marker file existence</li>
                  <li>Size stability over time</li>
                  <li>Post-collection actions</li>
                  <li>File size/age filtering</li>
                </ul>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
