import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import type { Job } from '../types';
import { JobStatus } from '../types';
import { jobs, type JobFilters } from '../api/client';
import StatusBadge from '../components/common/StatusBadge';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';

export default function JobListPage() {
  const [items, setItems] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [totalCount, setTotalCount] = useState(0);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const [filters, setFilters] = useState<JobFilters>({
    page: 1,
    page_size: 20,
  });

  useEffect(() => {
    loadItems();
  }, [filters]);

  async function loadItems() {
    try {
      setLoading(true);
      const data = await jobs.list(filters);
      setItems(data.items);
      setTotalCount(data.total);
    } catch {
      // Demo data
      const demoItems: Job[] = [
        { id: 1005, pipeline_activation_id: 1, pipeline_instance_id: 1, pipeline_name: 'Order Monitoring', source_type: 'API_RESPONSE' as Job['source_type'], source_key: 'order_batch_0315_005', source_metadata: {}, dedup_key: 'ob005', detected_at: '2026-03-15T15:00:00Z', status: JobStatus.PROCESSING, current_execution_id: 1005, execution_count: 1, last_completed_at: null },
        { id: 1004, pipeline_activation_id: 1, pipeline_instance_id: 1, pipeline_name: 'Order Monitoring', source_type: 'API_RESPONSE' as Job['source_type'], source_key: 'order_batch_0315_004', source_metadata: {}, dedup_key: 'ob004', detected_at: '2026-03-15T14:45:00Z', status: JobStatus.COMPLETED, current_execution_id: 1004, execution_count: 1, last_completed_at: '2026-03-15T14:45:02Z' },
        { id: 1003, pipeline_activation_id: 1, pipeline_instance_id: 1, pipeline_name: 'Order Monitoring', source_type: 'API_RESPONSE' as Job['source_type'], source_key: 'order_batch_0315_003', source_metadata: {}, dedup_key: 'ob003', detected_at: '2026-03-15T14:30:00Z', status: JobStatus.COMPLETED, current_execution_id: 1003, execution_count: 1, last_completed_at: '2026-03-15T14:30:02Z' },
        { id: 1002, pipeline_activation_id: 1, pipeline_instance_id: 1, pipeline_name: 'Order Monitoring', source_type: 'API_RESPONSE' as Job['source_type'], source_key: 'order_batch_0315_002', source_metadata: {}, dedup_key: 'ob002', detected_at: '2026-03-15T14:15:00Z', status: JobStatus.FAILED, current_execution_id: 1002, execution_count: 1, last_completed_at: null },
        { id: 1001, pipeline_activation_id: 1, pipeline_instance_id: 1, pipeline_name: 'Order Monitoring', source_type: 'API_RESPONSE' as Job['source_type'], source_key: 'order_batch_0315_001', source_metadata: {}, dedup_key: 'ob001', detected_at: '2026-03-15T14:00:00Z', status: JobStatus.COMPLETED, current_execution_id: 1001, execution_count: 1, last_completed_at: '2026-03-15T14:00:02Z' },
        { id: 1000, pipeline_activation_id: 2, pipeline_instance_id: 2, pipeline_name: 'Equipment File Collection', source_type: 'FILE' as Job['source_type'], source_key: 'equipment_A_20260315.csv', source_metadata: { size: 1024000 }, dedup_key: 'eqa315', detected_at: '2026-03-15T13:45:00Z', status: JobStatus.COMPLETED, current_execution_id: 1000, execution_count: 1, last_completed_at: '2026-03-15T13:45:05Z' },
        { id: 999, pipeline_activation_id: 2, pipeline_instance_id: 2, pipeline_name: 'Equipment File Collection', source_type: 'FILE' as Job['source_type'], source_key: 'equipment_B_20260315.csv', source_metadata: { size: 2048000 }, dedup_key: 'eqb315', detected_at: '2026-03-15T13:30:00Z', status: JobStatus.FAILED, current_execution_id: 999, execution_count: 2, last_completed_at: null },
        { id: 998, pipeline_activation_id: 2, pipeline_instance_id: 2, pipeline_name: 'Equipment File Collection', source_type: 'FILE' as Job['source_type'], source_key: 'equipment_C_20260314.csv', source_metadata: { size: 512000 }, dedup_key: 'eqc314', detected_at: '2026-03-14T16:00:00Z', status: JobStatus.COMPLETED, current_execution_id: 998, execution_count: 1, last_completed_at: '2026-03-14T16:00:03Z' },
      ];
      setItems(demoItems);
      setTotalCount(demoItems.length);
    } finally {
      setLoading(false);
    }
  }

  function toggleSelect(id: number) {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }

  function toggleSelectAll() {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(items.map((i) => i.id)));
    }
  }

  async function handleBulkReprocess() {
    if (selectedIds.size === 0) return;
    const reason = prompt('Enter reason for reprocessing:');
    if (!reason) return;
    try {
      await jobs.bulkReprocess({
        job_ids: Array.from(selectedIds),
        reason,
      });
      alert(`Reprocess requested for ${selectedIds.size} items`);
      setSelectedIds(new Set());
      loadItems();
    } catch {
      alert(`Reprocess requested for ${selectedIds.size} items (demo mode)`);
    }
  }

  if (loading) return <LoadingSpinner message="Loading jobs..." />;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-slate-900">Jobs</h1>
          <p className="mt-1 text-sm text-slate-500">
            {totalCount.toLocaleString()} total items across all pipelines
          </p>
        </div>
        {selectedIds.size > 0 && (
          <button onClick={handleBulkReprocess} className="btn-primary">
            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182" />
            </svg>
            Reprocess ({selectedIds.size})
          </button>
        )}
      </div>

      {/* Filters */}
      <div className="card flex flex-wrap items-center gap-3 px-5 py-3">
        <select
          value={filters.status || ''}
          onChange={(e) => setFilters({ ...filters, status: e.target.value || undefined, page: 1 })}
          className="input w-40"
        >
          <option value="">All Status</option>
          {Object.values(JobStatus).map((s) => (
            <option key={s} value={s}>{s}</option>
          ))}
        </select>
        <input
          type="date"
          value={filters.date_from || ''}
          onChange={(e) => setFilters({ ...filters, date_from: e.target.value || undefined, page: 1 })}
          className="input w-40"
          placeholder="From date"
        />
        <input
          type="date"
          value={filters.date_to || ''}
          onChange={(e) => setFilters({ ...filters, date_to: e.target.value || undefined, page: 1 })}
          className="input w-40"
          placeholder="To date"
        />
        <button
          onClick={() => setFilters({ page: 1, page_size: 20 })}
          className="text-xs font-medium text-slate-500 hover:text-slate-700"
        >
          Clear filters
        </button>
      </div>

      {/* Table */}
      {items.length === 0 ? (
        <EmptyState title="No jobs found" description="Adjust your filters or wait for new items to be detected." />
      ) : (
        <div className="card overflow-hidden">
          <table className="w-full">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50">
                <th className="px-4 py-3 text-left">
                  <input
                    type="checkbox"
                    checked={selectedIds.size === items.length && items.length > 0}
                    onChange={toggleSelectAll}
                    className="rounded border-slate-300"
                  />
                </th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">ID</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Source</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Pipeline</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Status</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Executions</th>
                <th className="px-4 py-3 text-left text-xs font-semibold uppercase tracking-wider text-slate-500">Detected</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {items.map((item) => (
                <tr key={item.id} className="transition-colors hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <input
                      type="checkbox"
                      checked={selectedIds.has(item.id)}
                      onChange={() => toggleSelect(item.id)}
                      className="rounded border-slate-300"
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Link to={`/jobs/${item.id}`} className="text-sm font-medium text-hermes-600 hover:text-hermes-700">
                      #{item.id}
                    </Link>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm text-slate-900">{item.source_key}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm text-slate-600">{item.pipeline_name}</span>
                  </td>
                  <td className="px-4 py-3">
                    <StatusBadge status={item.status} />
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-sm text-slate-600">{item.execution_count}</span>
                  </td>
                  <td className="px-4 py-3">
                    <span className="text-xs text-slate-500">
                      {new Date(item.detected_at).toLocaleString()}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
