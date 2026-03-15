import { useState } from 'react';

interface ProvenanceEvent {
  id: string;
  eventType: string;
  timestamp: string;
  componentName: string;
  componentType: 'COLLECT' | 'ALGORITHM' | 'TRANSFER';
  duration: string;
  inputSize: string;
  outputSize: string;
  details: string;
  status: 'SUCCESS' | 'FAILURE';
}

export default function ProvenancePage() {
  const [searchKey, setSearchKey] = useState('');
  const [events, setEvents] = useState<ProvenanceEvent[]>([]);
  const [loading, setLoading] = useState(false);

  function handleSearch() {
    setLoading(true);
    // Demo provenance data
    setTimeout(() => {
      setEvents([
        { id: 'prov-1', eventType: 'RECEIVE', timestamp: '2026-03-15T10:00:00.123Z', componentName: 'REST API Collector', componentType: 'COLLECT', duration: '523ms', inputSize: '-', outputSize: '24.5 KB', details: 'Received 150 records from https://api.vendor.com/orders', status: 'SUCCESS' },
        { id: 'prov-2', eventType: 'CONTENT_MODIFIED', timestamp: '2026-03-15T10:00:00.650Z', componentName: 'REST API Collector', componentType: 'COLLECT', duration: '12ms', inputSize: '24.5 KB', outputSize: '24.5 KB', details: 'Content stored: claim SHA-256 a1b2c3d4...', status: 'SUCCESS' },
        { id: 'prov-3', eventType: 'ROUTE', timestamp: '2026-03-15T10:00:01.100Z', componentName: 'Anomaly Detector', componentType: 'ALGORITHM', duration: '1,247ms', inputSize: '24.5 KB', outputSize: '18.2 KB', details: 'Processed 150 records: 147 normal, 3 anomalies (z-score > 2.5)', status: 'SUCCESS' },
        { id: 'prov-4', eventType: 'ATTRIBUTES_MODIFIED', timestamp: '2026-03-15T10:00:02.350Z', componentName: 'Anomaly Detector', componentType: 'ALGORITHM', duration: '3ms', inputSize: '-', outputSize: '-', details: 'Added attributes: anomaly_count=3, severity=HIGH', status: 'SUCCESS' },
        { id: 'prov-5', eventType: 'SEND', timestamp: '2026-03-15T10:00:02.400Z', componentName: 'S3 Upload', componentType: 'TRANSFER', duration: '2,341ms', inputSize: '18.2 KB', outputSize: '-', details: 'Uploaded to s3://hermes-output/2026/03/15/batch_001.json', status: 'SUCCESS' },
        { id: 'prov-6', eventType: 'DROP', timestamp: '2026-03-15T10:00:04.750Z', componentName: 'S3 Upload', componentType: 'TRANSFER', duration: '1ms', inputSize: '-', outputSize: '-', details: 'Content claim released after successful transfer', status: 'SUCCESS' },
      ]);
      setLoading(false);
    }, 500);
  }

  const typeColors: Record<string, string> = {
    COLLECT: 'bg-blue-500',
    ALGORITHM: 'bg-purple-500',
    TRANSFER: 'bg-emerald-500',
  };

  const eventIcons: Record<string, string> = {
    RECEIVE: 'M3 16.5v2.25A2.25 2.25 0 005.25 21h13.5A2.25 2.25 0 0021 18.75V16.5M16.5 12L12 16.5m0 0L7.5 12m4.5 4.5V3',
    CONTENT_MODIFIED: 'M16.862 4.487l1.687-1.688a1.875 1.875 0 112.652 2.652L10.582 16.07a4.5 4.5 0 01-1.897 1.13L6 18l.8-2.685a4.5 4.5 0 011.13-1.897l8.932-8.931zm0 0L19.5 7.125',
    ROUTE: 'M7.5 21L3 16.5m0 0L7.5 12M3 16.5h13.5m0-13.5L21 7.5m0 0L16.5 12M21 7.5H7.5',
    ATTRIBUTES_MODIFIED: 'M9.568 3H5.25A2.25 2.25 0 003 5.25v4.318c0 .597.237 1.17.659 1.591l9.581 9.581c.699.699 1.78.872 2.607.33a18.095 18.095 0 005.223-5.223c.542-.827.369-1.908-.33-2.607L11.16 3.66A2.25 2.25 0 009.568 3z',
    SEND: 'M6 12L3.269 3.126A59.768 59.768 0 0121.485 12 59.77 59.77 0 013.27 20.876L5.999 12zm0 0h7.5',
    DROP: 'M14.74 9l-.346 9m-4.788 0L9.26 9m9.968-3.21c.342.052.682.107 1.022.166m-1.022-.165L18.16 19.673a2.25 2.25 0 01-2.244 2.077H8.084a2.25 2.25 0 01-2.244-2.077L4.772 5.79m14.456 0a48.108 48.108 0 00-3.478-.397m-12 .562c.34-.059.68-.114 1.022-.165m0 0a48.11 48.11 0 013.478-.397m7.5 0v-.916c0-1.18-.91-2.164-2.09-2.201a51.964 51.964 0 00-3.32 0c-1.18.037-2.09 1.022-2.09 2.201v.916m7.5 0a48.667 48.667 0 00-7.5 0',
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Data Provenance</h1>
        <p className="mt-1 text-sm text-slate-500">
          Track the complete lineage of any data item through the pipeline
        </p>
      </div>

      {/* Search */}
      <div className="flex gap-3">
        <input
          type="text"
          placeholder="Search by source key, job ID, or dedup key..."
          value={searchKey}
          onChange={e => setSearchKey(e.target.value)}
          className="flex-1 rounded-lg border border-slate-200 px-4 py-2 text-sm focus:border-vessel-500 focus:outline-none"
        />
        <button
          onClick={handleSearch}
          className="btn-primary"
        >
          {loading ? 'Searching...' : 'Search Provenance'}
        </button>
      </div>

      {/* Timeline */}
      {events.length > 0 && (
        <div className="relative">
          {/* Vertical line */}
          <div className="absolute left-6 top-0 bottom-0 w-0.5 bg-slate-200" />

          {events.map((evt, idx) => (
            <div key={evt.id} className="relative mb-4 ml-14">
              {/* Timeline dot */}
              <div className={`absolute -left-[3.25rem] flex h-7 w-7 items-center justify-center rounded-full ${typeColors[evt.componentType]} text-white shadow-md`}>
                <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d={eventIcons[evt.eventType] || eventIcons.ROUTE} />
                </svg>
              </div>

              {/* Event card */}
              <div className={`rounded-lg border bg-white p-4 shadow-sm transition-all hover:shadow-md ${
                evt.status === 'FAILURE' ? 'border-red-200' : 'border-slate-200'
              }`}>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-mono font-bold text-slate-600">
                      {evt.eventType}
                    </span>
                    <span className="text-xs font-semibold text-slate-800">{evt.componentName}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[10px] text-slate-400">{evt.duration}</span>
                    <span className="font-mono text-[10px] text-slate-400">
                      {new Date(evt.timestamp).toLocaleTimeString('en-US', { hour12: false, fractionalSecondDigits: 3 } as any)}
                    </span>
                  </div>
                </div>
                <p className="mt-1.5 text-xs text-slate-600">{evt.details}</p>
                {(evt.inputSize !== '-' || evt.outputSize !== '-') && (
                  <div className="mt-2 flex gap-4 text-[10px] text-slate-400">
                    {evt.inputSize !== '-' && <span>In: {evt.inputSize}</span>}
                    {evt.outputSize !== '-' && <span>Out: {evt.outputSize}</span>}
                  </div>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {events.length === 0 && !loading && (
        <div className="flex flex-col items-center justify-center py-20 text-slate-400">
          <svg className="h-12 w-12 mb-3" fill="none" viewBox="0 0 24 24" strokeWidth={1} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M19.5 14.25v-2.625a3.375 3.375 0 00-3.375-3.375h-1.5A1.125 1.125 0 0113.5 7.125v-1.5a3.375 3.375 0 00-3.375-3.375H8.25m5.231 13.481L15 17.25m-4.5-15H5.625c-.621 0-1.125.504-1.125 1.125v16.5c0 .621.504 1.125 1.125 1.125h12.75c.621 0 1.125-.504 1.125-1.125V11.25a9 9 0 00-9-9zm3.75 11.625a2.625 2.625 0 11-5.25 0 2.625 2.625 0 015.25 0z" />
          </svg>
          <p className="text-sm">Search for a data item to view its provenance</p>
          <p className="text-xs mt-1">Enter a source key, job ID, or dedup key</p>
        </div>
      )}
    </div>
  );
}
