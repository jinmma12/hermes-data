import { useState, useEffect } from 'react';

interface Bulletin {
  id: string;
  level: 'INFO' | 'WARN' | 'ERROR';
  source: string;
  message: string;
  timestamp: string;
}

interface Props {
  pipelineId?: string;
}

export default function BulletinBoard({ pipelineId }: Props) {
  const [bulletins, setBulletins] = useState<Bulletin[]>([]);
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    // Demo bulletins — replace with WebSocket in production
    setBulletins([
      { id: '1', level: 'INFO', source: 'REST API Collector', message: 'Polling active — 12 records/min', timestamp: new Date().toISOString() },
      { id: '2', level: 'WARN', source: 'Anomaly Detector', message: '3 anomalies detected in last batch', timestamp: new Date(Date.now() - 30000).toISOString() },
      { id: '3', level: 'ERROR', source: 'S3 Upload', message: 'Connection timeout — retry 2/3', timestamp: new Date(Date.now() - 60000).toISOString() },
    ]);
  }, [pipelineId]);

  const errorCount = bulletins.filter(b => b.level === 'ERROR').length;
  const warnCount = bulletins.filter(b => b.level === 'WARN').length;

  const levelStyles = {
    INFO: 'border-l-blue-400 bg-blue-50',
    WARN: 'border-l-amber-400 bg-amber-50',
    ERROR: 'border-l-red-400 bg-red-50',
  };

  const levelText = {
    INFO: 'text-blue-700',
    WARN: 'text-amber-700',
    ERROR: 'text-red-700',
  };

  return (
    <div className="absolute bottom-4 right-4 z-20 w-80">
      {/* Collapsed summary */}
      <button
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center justify-between rounded-lg border border-slate-200 bg-white px-3 py-2 shadow-lg transition-all hover:shadow-xl"
      >
        <span className="text-xs font-semibold text-slate-700">Bulletin Board</span>
        <div className="flex items-center gap-2">
          {errorCount > 0 && (
            <span className="flex items-center gap-1 rounded-full bg-red-100 px-2 py-0.5 text-[10px] font-bold text-red-700">
              {errorCount} error{errorCount > 1 ? 's' : ''}
            </span>
          )}
          {warnCount > 0 && (
            <span className="flex items-center gap-1 rounded-full bg-amber-100 px-2 py-0.5 text-[10px] font-bold text-amber-700">
              {warnCount} warn
            </span>
          )}
          <svg className={`h-4 w-4 text-slate-400 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M4.5 15.75l7.5-7.5 7.5 7.5" />
          </svg>
        </div>
      </button>

      {/* Expanded bulletins */}
      {expanded && (
        <div className="mt-1 max-h-64 overflow-auto rounded-lg border border-slate-200 bg-white shadow-lg">
          {bulletins.length === 0 ? (
            <p className="p-3 text-xs text-slate-400">No bulletins</p>
          ) : (
            bulletins.map(b => (
              <div key={b.id} className={`border-b border-l-2 border-slate-100 px-3 py-2 ${levelStyles[b.level]}`}>
                <div className="flex items-center justify-between">
                  <span className={`text-[10px] font-bold ${levelText[b.level]}`}>{b.level}</span>
                  <span className="text-[9px] text-slate-400">
                    {new Date(b.timestamp).toLocaleTimeString()}
                  </span>
                </div>
                <p className="text-[10px] font-medium text-slate-700">{b.source}</p>
                <p className="text-[10px] text-slate-500">{b.message}</p>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
