import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import type { Job, JobExecution, JobStageExecution, ExecutionEventLog } from '../types';
import { JobStatus, ExecutionStatus, StageExecutionStatus, StageType, TriggerType, EventType } from '../types';
import { jobs } from '../api/client';
import StatusBadge from '../components/common/StatusBadge';
import LoadingSpinner from '../components/common/LoadingSpinner';

export default function JobDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [item, setItem] = useState<Job | null>(null);
  const [executions, setExecutions] = useState<JobExecution[]>([]);
  const [eventLogs, setEventLogs] = useState<ExecutionEventLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [showReprocessModal, setShowReprocessModal] = useState(false);

  useEffect(() => {
    loadData();
  }, [id]);

  async function loadData() {
    if (!id) return;
    try {
      setLoading(true);
      const itemId = parseInt(id);
      const [itemData, execData] = await Promise.all([
        jobs.get(itemId),
        jobs.getExecutions(itemId),
      ]);
      setItem(itemData);
      setExecutions(execData);
      if (execData.length > 0) {
        const logs = await jobs.getExecutionLogs(itemId, execData[0].id);
        setEventLogs(logs);
      }
    } catch {
      loadDemoData();
    } finally {
      setLoading(false);
    }
  }

  function loadDemoData() {
    setItem({
      id: 1002,
      pipeline_activation_id: 1,
      pipeline_instance_id: 1,
      pipeline_name: 'Order Monitoring Pipeline',
      source_type: 'API_RESPONSE' as Job['source_type'],
      source_key: 'order_batch_20260315_002',
      source_metadata: { record_count: 200 },
      dedup_key: 'ob002',
      detected_at: '2026-03-15T14:15:00Z',
      status: JobStatus.COMPLETED,
      current_execution_id: 2002,
      execution_count: 2,
      last_completed_at: '2026-03-15T14:32:03Z',
    });

    const demoStages1: JobStageExecution[] = [
      { id: 1, execution_id: 2001, pipeline_stage_id: 1, stage_type: StageType.COLLECT, stage_order: 1, status: StageExecutionStatus.COMPLETED, started_at: '2026-03-15T14:15:00Z', ended_at: '2026-03-15T14:15:02Z', duration_ms: 2300, input_summary: null, output_summary: { records: 200 }, error_code: null, error_message: null, retry_attempt: 0 },
      { id: 2, execution_id: 2001, pipeline_stage_id: 2, stage_type: StageType.ALGORITHM, stage_order: 2, status: StageExecutionStatus.FAILED, started_at: '2026-03-15T14:15:02Z', ended_at: '2026-03-15T14:15:03Z', duration_ms: 800, input_summary: { records: 200 }, output_summary: null, error_code: 'THRESHOLD_ERROR', error_message: 'Threshold 2.5 too aggressive for this dataset', retry_attempt: 0 },
      { id: 3, execution_id: 2001, pipeline_stage_id: 3, stage_type: StageType.TRANSFER, stage_order: 3, status: StageExecutionStatus.SKIPPED, started_at: null, ended_at: null, duration_ms: null, input_summary: null, output_summary: null, error_code: null, error_message: null, retry_attempt: 0 },
    ];

    const demoStages2: JobStageExecution[] = [
      { id: 4, execution_id: 2002, pipeline_stage_id: 2, stage_type: StageType.ALGORITHM, stage_order: 2, status: StageExecutionStatus.COMPLETED, started_at: '2026-03-15T14:32:01Z', ended_at: '2026-03-15T14:32:02Z', duration_ms: 1100, input_summary: { records: 200 }, output_summary: { anomalies: 3 }, error_code: null, error_message: null, retry_attempt: 0 },
      { id: 5, execution_id: 2002, pipeline_stage_id: 3, stage_type: StageType.TRANSFER, stage_order: 3, status: StageExecutionStatus.COMPLETED, started_at: '2026-03-15T14:32:02Z', ended_at: '2026-03-15T14:32:03Z', duration_ms: 500, input_summary: { anomalies: 3 }, output_summary: { destination: 's3://bucket/results/1002.json' }, error_code: null, error_message: null, retry_attempt: 0 },
    ];

    setExecutions([
      { id: 2002, job_id: 1002, execution_no: 2, trigger_type: TriggerType.REPROCESS, trigger_source: 'USER:operator_kim', status: ExecutionStatus.COMPLETED, started_at: '2026-03-15T14:32:00Z', ended_at: '2026-03-15T14:32:03Z', duration_ms: 3000, reprocess_request_id: 1, stages: demoStages2 },
      { id: 2001, job_id: 1002, execution_no: 1, trigger_type: TriggerType.INITIAL, trigger_source: 'SYSTEM', status: ExecutionStatus.FAILED, started_at: '2026-03-15T14:15:00Z', ended_at: '2026-03-15T14:15:03Z', duration_ms: 3100, reprocess_request_id: null, stages: demoStages1 },
    ]);

    setEventLogs([
      { id: 1, execution_id: 2001, stage_execution_id: 1, event_type: EventType.INFO, event_code: 'COLLECT_START', message: 'Fetching orders from REST API...', detail_json: null, created_at: '2026-03-15T14:15:00.000Z' },
      { id: 2, execution_id: 2001, stage_execution_id: 1, event_type: EventType.INFO, event_code: 'COLLECT_DONE', message: '200 records fetched successfully', detail_json: { count: 200 }, created_at: '2026-03-15T14:15:02.312Z' },
      { id: 3, execution_id: 2001, stage_execution_id: 2, event_type: EventType.INFO, event_code: 'ALG_START', message: 'Running z-score analysis...', detail_json: null, created_at: '2026-03-15T14:15:02.315Z' },
      { id: 4, execution_id: 2001, stage_execution_id: 2, event_type: EventType.ERROR, event_code: 'ALG_ERROR', message: 'Threshold 2.5 too aggressive for this dataset', detail_json: { threshold: 2.5 }, created_at: '2026-03-15T14:15:03.102Z' },
      { id: 5, execution_id: 2002, stage_execution_id: null, event_type: EventType.INFO, event_code: 'REPROCESS_REQ', message: 'Reprocess requested by operator:kim', detail_json: null, created_at: '2026-03-15T14:32:00.100Z' },
      { id: 6, execution_id: 2002, stage_execution_id: 4, event_type: EventType.INFO, event_code: 'ALG_START', message: 'Running z-score analysis with threshold 3.0...', detail_json: null, created_at: '2026-03-15T14:32:01.200Z' },
      { id: 7, execution_id: 2002, stage_execution_id: 4, event_type: EventType.INFO, event_code: 'ALG_DONE', message: '3 anomalies detected', detail_json: { anomalies: 3 }, created_at: '2026-03-15T14:32:02.350Z' },
      { id: 8, execution_id: 2002, stage_execution_id: 5, event_type: EventType.INFO, event_code: 'TRANSFER_START', message: 'Uploading results to S3...', detail_json: null, created_at: '2026-03-15T14:32:02.355Z' },
      { id: 9, execution_id: 2002, stage_execution_id: 5, event_type: EventType.INFO, event_code: 'TRANSFER_DONE', message: 'Uploaded to s3://bucket/results/1002.json', detail_json: { path: 's3://bucket/results/1002.json' }, created_at: '2026-03-15T14:32:02.890Z' },
    ]);
  }

  async function handleReprocess(startFromStage?: number) {
    if (!item) return;
    const reason = prompt('Enter reason for reprocessing:');
    if (!reason) return;
    try {
      await jobs.reprocess(item.id, {
        reason,
        start_from_stage: startFromStage,
        use_latest_recipe: true,
      });
      alert('Reprocess request submitted!');
      loadData();
    } catch {
      alert('Reprocess request submitted (demo mode)');
    }
    setShowReprocessModal(false);
  }

  const stageStatusIcon = (status: StageExecutionStatus) => {
    switch (status) {
      case StageExecutionStatus.COMPLETED: return <span className="text-lg text-emerald-500">&#10003;</span>;
      case StageExecutionStatus.FAILED: return <span className="text-lg text-red-500">&#10007;</span>;
      case StageExecutionStatus.SKIPPED: return <span className="text-lg text-slate-400">&#9193;</span>;
      case StageExecutionStatus.RUNNING: return <span className="text-lg text-yellow-500">&#8987;</span>;
    }
  };

  const eventTypeColor = (type: EventType) => {
    switch (type) {
      case EventType.ERROR: return 'text-red-600';
      case EventType.WARN: return 'text-amber-600';
      case EventType.DEBUG: return 'text-slate-400';
      default: return 'text-slate-600';
    }
  };

  if (loading) return <LoadingSpinner message="Loading job..." />;
  if (!item) return <div className="py-12 text-center text-slate-500">Job not found</div>;

  return (
    <div className="space-y-6">
      {/* Breadcrumb + Header */}
      <div>
        <div className="flex items-center gap-2 text-sm text-slate-500">
          <Link to="/jobs" className="hover:text-hermes-600">Jobs</Link>
          <span>/</span>
          <span className="text-slate-900">#{item.id}</span>
        </div>
        <div className="mt-2 flex items-center justify-between">
          <div>
            <h1 className="text-2xl font-bold text-slate-900">Job #{item.id}</h1>
            <p className="mt-1 text-sm text-slate-500">{item.source_key}</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowReprocessModal(true)} className="btn-primary">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
              </svg>
              Reprocess
            </button>
          </div>
        </div>
      </div>

      {/* Summary Card */}
      <div className="card grid gap-4 p-5 sm:grid-cols-4">
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Status</p>
          <div className="mt-1"><StatusBadge status={item.status} size="md" /></div>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Pipeline</p>
          <p className="mt-1 text-sm font-medium text-slate-900">{item.pipeline_name}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Detected</p>
          <p className="mt-1 text-sm text-slate-900">{new Date(item.detected_at).toLocaleString()}</p>
        </div>
        <div>
          <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Executions</p>
          <p className="mt-1 text-sm text-slate-900">{item.execution_count}</p>
        </div>
      </div>

      {/* Execution History Timeline */}
      <div className="card">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-900">Execution History</h2>
        </div>
        <div className="divide-y divide-slate-100">
          {executions.map((exec) => (
            <div key={exec.id} className="px-5 py-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`flex h-8 w-8 items-center justify-center rounded-full text-sm font-bold ${
                    exec.status === ExecutionStatus.COMPLETED
                      ? 'bg-emerald-100 text-emerald-700'
                      : exec.status === ExecutionStatus.FAILED
                        ? 'bg-red-100 text-red-700'
                        : 'bg-yellow-100 text-yellow-700'
                  }`}>
                    #{exec.execution_no}
                  </div>
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-semibold text-slate-900">
                        {exec.trigger_type}
                      </span>
                      <StatusBadge status={exec.status} />
                    </div>
                    <p className="text-xs text-slate-500">
                      {exec.trigger_source} &middot; {new Date(exec.started_at).toLocaleString()}
                      {exec.duration_ms != null && ` &middot; ${(exec.duration_ms / 1000).toFixed(1)}s`}
                    </p>
                  </div>
                </div>
              </div>

              {/* Stage Results */}
              {exec.stages && exec.stages.length > 0 && (
                <div className="ml-11 mt-3 space-y-2">
                  {exec.stages.map((stage) => (
                    <div key={stage.id} className="flex items-center gap-3 rounded-lg bg-slate-50 px-3 py-2">
                      {stageStatusIcon(stage.status)}
                      <div className="flex-1">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-semibold uppercase text-slate-600">{stage.stage_type}</span>
                          {stage.duration_ms != null && (
                            <span className="text-[10px] text-slate-400">{(stage.duration_ms / 1000).toFixed(1)}s</span>
                          )}
                        </div>
                        {stage.output_summary && (
                          <p className="text-[11px] text-slate-500">
                            {JSON.stringify(stage.output_summary)}
                          </p>
                        )}
                        {stage.error_message && (
                          <p className="text-[11px] text-red-500">{stage.error_message}</p>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
      </div>

      {/* Event Log */}
      <div className="card">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-900">Event Log</h2>
        </div>
        <div className="max-h-96 overflow-auto">
          <table className="w-full">
            <thead className="sticky top-0 bg-white">
              <tr className="border-b border-slate-200">
                <th className="px-4 py-2 text-left text-[10px] font-semibold uppercase text-slate-500">Time</th>
                <th className="px-4 py-2 text-left text-[10px] font-semibold uppercase text-slate-500">Level</th>
                <th className="px-4 py-2 text-left text-[10px] font-semibold uppercase text-slate-500">Code</th>
                <th className="px-4 py-2 text-left text-[10px] font-semibold uppercase text-slate-500">Message</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-50 font-mono text-xs">
              {eventLogs.map((log) => (
                <tr key={log.id} className="hover:bg-slate-50">
                  <td className="whitespace-nowrap px-4 py-1.5 text-slate-400">
                    {new Date(log.created_at).toLocaleTimeString(undefined, { hour12: false, fractionalSecondDigits: 3 } as Intl.DateTimeFormatOptions)}
                  </td>
                  <td className={`px-4 py-1.5 font-semibold ${eventTypeColor(log.event_type)}`}>
                    {log.event_type}
                  </td>
                  <td className="px-4 py-1.5 text-slate-600">{log.event_code}</td>
                  <td className={`px-4 py-1.5 ${eventTypeColor(log.event_type)}`}>{log.message}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {/* Reprocess Modal */}
      {showReprocessModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
            <h3 className="text-lg font-semibold text-slate-900">Reprocess Job</h3>
            <p className="mt-1 text-sm text-slate-500">Choose how to reprocess #{item.id}</p>

            <div className="mt-4 space-y-3">
              <button
                onClick={() => handleReprocess()}
                className="w-full rounded-lg border border-slate-200 px-4 py-3 text-left transition-colors hover:bg-slate-50"
              >
                <p className="text-sm font-medium text-slate-900">Full Reprocess</p>
                <p className="text-xs text-slate-500">Re-run all stages from the beginning with latest recipe</p>
              </button>
              <button
                onClick={() => handleReprocess(2)}
                className="w-full rounded-lg border border-slate-200 px-4 py-3 text-left transition-colors hover:bg-slate-50"
              >
                <p className="text-sm font-medium text-slate-900">From Algorithm Stage</p>
                <p className="text-xs text-slate-500">Skip collection, re-run algorithm and transfer stages</p>
              </button>
              <button
                onClick={() => handleReprocess(3)}
                className="w-full rounded-lg border border-slate-200 px-4 py-3 text-left transition-colors hover:bg-slate-50"
              >
                <p className="text-sm font-medium text-slate-900">Transfer Only</p>
                <p className="text-xs text-slate-500">Re-run only the transfer stage</p>
              </button>
            </div>

            <div className="mt-4 flex justify-end">
              <button onClick={() => setShowReprocessModal(false)} className="btn-secondary">
                Cancel
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
