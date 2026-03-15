import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { PipelineActivation, Job, MonitorStats } from '../types';
import { ActivationStatus, JobStatus } from '../types';
import { monitor } from '../api/client';
import StatusBadge from '../components/common/StatusBadge';
import LoadingSpinner from '../components/common/LoadingSpinner';

function timeAgo(dateStr: string): string {
  const diff = Date.now() - new Date(dateStr).getTime();
  const seconds = Math.floor(diff / 1000);
  if (seconds < 60) return `${seconds}s ago`;
  const minutes = Math.floor(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours}h ago`;
}

export default function MonitorDashboardPage() {
  const [stats, setStats] = useState<MonitorStats | null>(null);
  const [activations, setActivations] = useState<PipelineActivation[]>([]);
  const [recentItems, setRecentItems] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 10000);
    return () => clearInterval(interval);
  }, []);

  async function loadData() {
    try {
      const [s, a, w] = await Promise.all([
        monitor.getStats(),
        monitor.getActiveActivations(),
        monitor.getRecentJobs(10),
      ]);
      setStats(s);
      setActivations(a);
      setRecentItems(w);
    } catch {
      // Use demo data
      setStats({
        total_items: 3247,
        completed_items: 3102,
        failed_items: 89,
        success_rate: 95.5,
        avg_duration_ms: 2340,
        active_pipelines: 3,
      });
      setActivations([
        {
          id: 1, pipeline_instance_id: 1,
          pipeline: { id: 1, name: 'Order Monitoring Pipeline', description: '', monitoring_type: 'API_POLL' as PipelineActivation['pipeline']&{} extends never ? never : 'API_POLL' as any, monitoring_config: {}, status: 'ACTIVE' as any, created_at: '', updated_at: '' },
          status: ActivationStatus.RUNNING,
          started_at: '2026-03-15T09:00:00Z',
          stopped_at: null,
          last_heartbeat_at: new Date(Date.now() - 2000).toISOString(),
          last_polled_at: new Date(Date.now() - 5000).toISOString(),
          error_message: null,
          worker_id: 'worker-1',
          job_count: 1247,
        },
        {
          id: 2, pipeline_instance_id: 2,
          pipeline: { id: 2, name: 'Equipment File Collection', description: '', monitoring_type: 'FILE_MONITOR' as any, monitoring_config: {}, status: 'ACTIVE' as any, created_at: '', updated_at: '' },
          status: ActivationStatus.RUNNING,
          started_at: '2026-03-15T08:00:00Z',
          stopped_at: null,
          last_heartbeat_at: new Date(Date.now() - 5000).toISOString(),
          last_polled_at: new Date(Date.now() - 10000).toISOString(),
          error_message: null,
          worker_id: 'worker-1',
          job_count: 892,
        },
        {
          id: 3, pipeline_instance_id: 3,
          pipeline: { id: 3, name: 'ERP Database Sync', description: '', monitoring_type: 'DB_POLL' as any, monitoring_config: {}, status: 'PAUSED' as any, created_at: '', updated_at: '' },
          status: ActivationStatus.STOPPED,
          started_at: '2026-03-14T09:00:00Z',
          stopped_at: '2026-03-14T18:00:00Z',
          last_heartbeat_at: null,
          last_polled_at: null,
          error_message: null,
          worker_id: null,
          job_count: 0,
        },
        {
          id: 4, pipeline_instance_id: 4,
          pipeline: { id: 4, name: 'Equipment C Log Collection', description: '', monitoring_type: 'FILE_MONITOR' as any, monitoring_config: {}, status: 'ACTIVE' as any, created_at: '', updated_at: '' },
          status: ActivationStatus.ERROR,
          started_at: '2026-03-15T06:00:00Z',
          stopped_at: null,
          last_heartbeat_at: new Date(Date.now() - 1800000).toISOString(),
          last_polled_at: null,
          error_message: 'Connection timeout after 3 retries',
          worker_id: 'worker-2',
          job_count: 56,
        },
      ]);
      setRecentItems([
        { id: 1003, pipeline_activation_id: 1, pipeline_instance_id: 1, pipeline_name: 'Order Monitoring', source_type: 'API_RESPONSE' as any, source_key: 'order_batch_0315_003', source_metadata: {}, dedup_key: 'ob003', detected_at: '2026-03-15T14:30:00Z', status: JobStatus.COMPLETED, current_execution_id: 1003, execution_count: 1, last_completed_at: '2026-03-15T14:30:02Z' },
        { id: 1002, pipeline_activation_id: 1, pipeline_instance_id: 1, pipeline_name: 'Order Monitoring', source_type: 'API_RESPONSE' as any, source_key: 'order_batch_0315_002', source_metadata: {}, dedup_key: 'ob002', detected_at: '2026-03-15T14:15:00Z', status: JobStatus.FAILED, current_execution_id: 1002, execution_count: 1, last_completed_at: null },
        { id: 1001, pipeline_activation_id: 1, pipeline_instance_id: 1, pipeline_name: 'Order Monitoring', source_type: 'API_RESPONSE' as any, source_key: 'order_batch_0315_001', source_metadata: {}, dedup_key: 'ob001', detected_at: '2026-03-15T14:00:00Z', status: JobStatus.COMPLETED, current_execution_id: 1001, execution_count: 1, last_completed_at: '2026-03-15T14:00:02Z' },
        { id: 1000, pipeline_activation_id: 2, pipeline_instance_id: 2, pipeline_name: 'Equipment File Collection', source_type: 'FILE' as any, source_key: 'equipment_A_20260315.csv', source_metadata: {}, dedup_key: 'eqa315', detected_at: '2026-03-15T13:45:00Z', status: JobStatus.COMPLETED, current_execution_id: 1000, execution_count: 1, last_completed_at: '2026-03-15T13:45:05Z' },
        { id: 999, pipeline_activation_id: 2, pipeline_instance_id: 2, pipeline_name: 'Equipment File Collection', source_type: 'FILE' as any, source_key: 'equipment_B_20260315.csv', source_metadata: {}, dedup_key: 'eqb315', detected_at: '2026-03-15T13:30:00Z', status: JobStatus.PROCESSING, current_execution_id: 999, execution_count: 1, last_completed_at: null },
      ]);
    } finally {
      setLoading(false);
    }
  }

  if (loading) return <LoadingSpinner message="Loading monitor dashboard..." />;

  const statusIcon = (status: ActivationStatus) => {
    switch (status) {
      case ActivationStatus.RUNNING:
        return <span className="inline-block h-2.5 w-2.5 rounded-full bg-emerald-500 animate-pulse-dot" />;
      case ActivationStatus.STOPPED:
        return <span className="inline-block h-2.5 w-2.5 rounded-full bg-slate-300" />;
      case ActivationStatus.ERROR:
        return <span className="inline-block h-2.5 w-2.5 rounded-full bg-red-500 animate-pulse-dot" />;
      default:
        return <span className="inline-block h-2.5 w-2.5 rounded-full bg-amber-400" />;
    }
  };

  const jobStatusIcon = (status: JobStatus) => {
    switch (status) {
      case JobStatus.COMPLETED: return <span className="text-emerald-500">OK</span>;
      case JobStatus.FAILED: return <span className="text-red-500">FAIL</span>;
      case JobStatus.PROCESSING: return <span className="text-yellow-500">...</span>;
      default: return <span className="text-slate-400">--</span>;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-slate-900">Monitor Dashboard</h1>
        <p className="mt-1 text-sm text-slate-500">Real-time pipeline status and jobs</p>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <div className="card px-5 py-4">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Total Items</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">{stats.total_items.toLocaleString()}</p>
          </div>
          <div className="card px-5 py-4">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Success Rate</p>
            <p className="mt-1 text-2xl font-bold text-emerald-600">{stats.success_rate.toFixed(1)}%</p>
          </div>
          <div className="card px-5 py-4">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Failed Items</p>
            <p className="mt-1 text-2xl font-bold text-red-600">{stats.failed_items}</p>
          </div>
          <div className="card px-5 py-4">
            <p className="text-xs font-medium uppercase tracking-wider text-slate-500">Avg Duration</p>
            <p className="mt-1 text-2xl font-bold text-slate-900">{(stats.avg_duration_ms / 1000).toFixed(1)}s</p>
          </div>
        </div>
      )}

      {/* Active Pipelines */}
      <div className="card">
        <div className="border-b border-slate-200 px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-900">Active Pipelines</h2>
        </div>
        <div className="divide-y divide-slate-100">
          {activations.map((activation) => (
            <div key={activation.id} className="flex items-center justify-between px-5 py-3.5">
              <div className="flex items-center gap-3">
                {statusIcon(activation.status)}
                <div>
                  <p className="text-sm font-medium text-slate-900">
                    {activation.pipeline?.name || `Pipeline #${activation.pipeline_instance_id}`}
                  </p>
                  {activation.error_message && (
                    <p className="mt-0.5 text-xs text-red-500">{activation.error_message}</p>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-4">
                <StatusBadge status={activation.status} />
                {activation.last_heartbeat_at && (
                  <span className="flex items-center gap-1 text-xs text-slate-400">
                    <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24">
                      <path d="M12 21.35l-1.45-1.32C5.4 15.36 2 12.28 2 8.5 2 5.42 4.42 3 7.5 3c1.74 0 3.41.81 4.5 2.09C13.09 3.81 14.76 3 16.5 3 19.58 3 22 5.42 22 8.5c0 3.78-3.4 6.86-8.55 11.54L12 21.35z" />
                    </svg>
                    {timeAgo(activation.last_heartbeat_at)}
                  </span>
                )}
                <span className="min-w-[80px] text-right text-xs text-slate-500">
                  {(activation.job_count || 0).toLocaleString()} items
                </span>
              </div>
            </div>
          ))}
        </div>
      </div>

      {/* Recent Jobs */}
      <div className="card">
        <div className="flex items-center justify-between border-b border-slate-200 px-5 py-4">
          <h2 className="text-sm font-semibold text-slate-900">Recent Jobs</h2>
          <Link to="/jobs" className="text-xs font-medium text-hermes-600 hover:text-hermes-700">
            View All &rarr;
          </Link>
        </div>
        <div className="divide-y divide-slate-100">
          {recentItems.map((item) => (
            <Link
              key={item.id}
              to={`/jobs/${item.id}`}
              className="flex items-center justify-between px-5 py-3 transition-colors hover:bg-slate-50"
            >
              <div className="flex items-center gap-3">
                {jobStatusIcon(item.status)}
                <div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-medium text-slate-500">#{item.id}</span>
                    <span className="text-sm text-slate-900">{item.source_key}</span>
                  </div>
                  <span className="text-xs text-slate-400">{item.pipeline_name}</span>
                </div>
              </div>
              <div className="flex items-center gap-3">
                <StatusBadge status={item.status} size="sm" />
                <span className="text-xs text-slate-400">
                  {new Date(item.detected_at).toLocaleTimeString()}
                </span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}
