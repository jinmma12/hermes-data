import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { PipelineInstance } from '../types';
import { PipelineStatus } from '../types';
import { pipelines } from '../api/client';
import StatusBadge from '../components/common/StatusBadge';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';

export default function PipelineListPage() {
  const [pipelineList, setPipelineList] = useState<PipelineInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    loadPipelines();
  }, []);

  async function loadPipelines() {
    try {
      setLoading(true);
      const data = await pipelines.list();
      setPipelineList(Array.isArray(data) ? data : []);
    } catch (err) {
      setError('Failed to load pipelines');
      // Use mock data for demo
      setPipelineList([
        {
          id: 1,
          name: 'Order Monitoring Pipeline',
          description: 'Collects orders from REST API, detects anomalies, uploads to S3',
          monitoring_type: 'API_POLL' as PipelineInstance['monitoring_type'],
          monitoring_config: { interval: '5m' },
          status: PipelineStatus.ACTIVE,
          created_at: '2026-03-01T09:00:00Z',
          updated_at: '2026-03-15T14:30:00Z',
        },
        {
          id: 2,
          name: 'Equipment File Collection',
          description: 'Monitors equipment data files, processes CSV, stores results',
          monitoring_type: 'FILE_MONITOR' as PipelineInstance['monitoring_type'],
          monitoring_config: { path: '/data/equipment', pattern: '*.csv' },
          status: PipelineStatus.ACTIVE,
          created_at: '2026-03-05T10:00:00Z',
          updated_at: '2026-03-15T14:25:00Z',
        },
        {
          id: 3,
          name: 'ERP Database Sync',
          description: 'Syncs changes from ERP database to data warehouse',
          monitoring_type: 'DB_POLL' as PipelineInstance['monitoring_type'],
          monitoring_config: { table: 'orders', poll_interval: '1m' },
          status: PipelineStatus.PAUSED,
          created_at: '2026-03-10T08:00:00Z',
          updated_at: '2026-03-14T16:00:00Z',
        },
        {
          id: 4,
          name: 'Log Collection Pipeline',
          description: 'Draft pipeline for collecting application logs',
          monitoring_type: 'FILE_MONITOR' as PipelineInstance['monitoring_type'],
          monitoring_config: {},
          status: PipelineStatus.DRAFT,
          created_at: '2026-03-14T11:00:00Z',
          updated_at: '2026-03-14T11:00:00Z',
        },
      ]);
    } finally {
      setLoading(false);
    }
  }

  function handleCreatePipeline() {
    // In a real app, this would open a create dialog or navigate to a form
    navigate('/pipelines/new/designer');
  }

  if (loading) return <LoadingSpinner message="Loading pipelines..." />;

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Pipelines</h1>
          <p className="mt-1 text-sm text-slate-500">
            Create and manage data processing pipelines
          </p>
        </div>
        <button onClick={handleCreatePipeline} className="btn-primary">
          <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
          </svg>
          New Pipeline
        </button>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800">
          {error} -- showing demo data
        </div>
      )}

      {/* Pipeline Grid */}
      {pipelineList.length === 0 ? (
        <EmptyState
          title="No pipelines yet"
          description="Create your first pipeline to start processing data."
          action={{ label: 'Create Pipeline', onClick: handleCreatePipeline }}
        />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {pipelineList.map((pipeline) => (
            <Link
              key={pipeline.id}
              to={`/pipelines/${pipeline.id}/designer`}
              className="card group p-5 transition-shadow hover:shadow-md"
            >
              <div className="flex items-start justify-between">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-vessel-50">
                  <svg className="h-5 w-5 text-vessel-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" />
                  </svg>
                </div>
                <StatusBadge status={pipeline.status} />
              </div>

              <h3 className="mt-3 text-sm font-semibold text-slate-900 group-hover:text-vessel-700">
                {pipeline.name}
              </h3>
              <p className="mt-1 line-clamp-2 text-xs text-slate-500">
                {pipeline.description}
              </p>

              <div className="mt-4 flex items-center gap-3 border-t border-slate-100 pt-3">
                <span className="inline-flex items-center gap-1 text-xs text-slate-400">
                  <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6v6h4.5m4.5 0a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  {new Date(pipeline.updated_at).toLocaleDateString()}
                </span>
                <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-medium text-slate-500">
                  {pipeline.monitoring_type.replace('_', ' ')}
                </span>
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
