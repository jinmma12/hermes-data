import { useCallback, useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { PipelineInstance } from '../types';
import { PipelineStatus } from '../types';
import { pipelines } from '../api/client';
import StatusBadge from '../components/common/StatusBadge';
import LoadingSpinner from '../components/common/LoadingSpinner';
import EmptyState from '../components/common/EmptyState';
import ContextMenu from '../components/designer/ContextMenu';
import { menuIcons } from '../components/designer/ContextMenu';

// Status filter order
const STATUS_FILTERS = ['ALL', PipelineStatus.ACTIVE, PipelineStatus.PAUSED, PipelineStatus.DRAFT, PipelineStatus.ARCHIVED] as const;
type StatusFilter = typeof STATUS_FILTERS[number];

// Group display order (ALL excluded)
const GROUP_ORDER = [PipelineStatus.ACTIVE, PipelineStatus.PAUSED, PipelineStatus.DRAFT, PipelineStatus.ARCHIVED];

export default function PipelineListPage() {
  const [pipelineList, setPipelineList] = useState<PipelineInstance[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState('');
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('ALL');
  const [contextMenu, setContextMenu] = useState<{ x: number; y: number; pipeline: PipelineInstance } | null>(null);
  const [deleteModal, setDeleteModal] = useState<PipelineInstance | null>(null);
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
      setPipelineList([
        {
          id: 1,
          name: 'Vendor-A 주문 수집',
          description: 'REST API → Anomaly Detector → S3 Upload',
          monitoring_type: 'API_POLL' as PipelineInstance['monitoring_type'],
          monitoring_config: { interval: '5m' },
          status: PipelineStatus.ACTIVE,
          created_at: '2026-03-01T09:00:00Z',
          updated_at: '2026-03-15T14:30:00Z',
        },
        {
          id: 2,
          name: '장비 데이터 수집',
          description: 'FTP/SFTP → Data Transformer → DB Writer',
          monitoring_type: 'FILE_MONITOR' as PipelineInstance['monitoring_type'],
          monitoring_config: { path: '/data/equipment', pattern: '*.csv' },
          status: PipelineStatus.ACTIVE,
          created_at: '2026-03-05T10:00:00Z',
          updated_at: '2026-03-15T14:25:00Z',
        },
        {
          id: 3,
          name: 'ERP DB 동기화',
          description: 'Database CDC → Transform → DB Writer',
          monitoring_type: 'DB_POLL' as PipelineInstance['monitoring_type'],
          monitoring_config: { table: 'orders', poll_interval: '1m' },
          status: PipelineStatus.PAUSED,
          created_at: '2026-03-10T08:00:00Z',
          updated_at: '2026-03-14T16:00:00Z',
        },
        {
          id: 4,
          name: '센서 데이터 분석',
          description: 'Kafka Consumer → Anomaly Detector → S3 Upload',
          monitoring_type: 'EVENT_STREAM' as PipelineInstance['monitoring_type'],
          monitoring_config: { topics: 'sensor-data' },
          status: PipelineStatus.ACTIVE,
          created_at: '2026-03-08T09:00:00Z',
          updated_at: '2026-03-15T14:00:00Z',
        },
        {
          id: 5,
          name: '실시간 이상탐지',
          description: 'Kafka Consumer → Anomaly Detector → Webhook',
          monitoring_type: 'EVENT_STREAM' as PipelineInstance['monitoring_type'],
          monitoring_config: { topics: 'equipment-events' },
          status: PipelineStatus.ACTIVE,
          created_at: '2026-03-12T10:00:00Z',
          updated_at: '2026-03-16T09:00:00Z',
        },
        {
          id: 6,
          name: '로그 수집 파이프라인',
          description: 'File Watcher → CSV-JSON Converter → Elasticsearch',
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

  // ---- Computed: filter → group ----

  const statusCounts = useMemo(() => {
    const counts: Record<string, number> = { ALL: pipelineList.length };
    for (const s of Object.values(PipelineStatus)) counts[s] = 0;
    for (const p of pipelineList) counts[p.status] = (counts[p.status] || 0) + 1;
    return counts;
  }, [pipelineList]);

  const filteredPipelines = useMemo(() => {
    let list = pipelineList;
    if (statusFilter !== 'ALL') {
      list = list.filter((p) => p.status === statusFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase();
      list = list.filter(
        (p) =>
          p.name.toLowerCase().includes(q) ||
          (p.description || '').toLowerCase().includes(q)
      );
    }
    return list;
  }, [pipelineList, statusFilter, search]);

  const groupedPipelines = useMemo(() => {
    const groups: Record<string, PipelineInstance[]> = {};
    for (const p of filteredPipelines) {
      if (!groups[p.status]) groups[p.status] = [];
      groups[p.status].push(p);
    }
    return groups;
  }, [filteredPipelines]);

  // ---- Actions ----

  function handleCreatePipeline() {
    navigate('/pipelines/new/designer');
  }

  const handleArchive = useCallback(async (p: PipelineInstance) => {
    try {
      await pipelines.archive(p.id);
    } catch {
      // demo mode: local state update
    }
    setPipelineList((list) =>
      list.map((item) =>
        item.id === p.id ? { ...item, status: PipelineStatus.ARCHIVED } : item
      )
    );
  }, []);

  const handleDelete = useCallback(async (p: PipelineInstance) => {
    try {
      await pipelines.delete(p.id);
    } catch {
      // demo mode: local state update
    }
    setPipelineList((list) => list.filter((item) => item.id !== p.id));
    setDeleteModal(null);
  }, []);

  const handleDuplicate = useCallback(async (p: PipelineInstance) => {
    try {
      const dup = await pipelines.duplicate(p.id);
      setPipelineList((list) => [...list, dup]);
    } catch {
      // demo mode: create local copy
      const maxId = pipelineList.reduce((max, item) => Math.max(max, item.id), 0);
      const dup: PipelineInstance = {
        ...p,
        id: maxId + 1,
        name: p.name + ' (Copy)',
        status: PipelineStatus.DRAFT,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      setPipelineList((list) => [...list, dup]);
    }
  }, [pipelineList]);

  const confirmDeleteOrArchive = useCallback((p: PipelineInstance) => {
    if (p.status === PipelineStatus.DRAFT) {
      setDeleteModal(p);
    } else {
      handleArchive(p);
    }
  }, [handleArchive]);

  // ---- Context menu ----

  const openMenu = useCallback((e: React.MouseEvent, p: PipelineInstance) => {
    e.preventDefault();
    e.stopPropagation();
    setContextMenu({ x: e.clientX, y: e.clientY, pipeline: p });
  }, []);

  const menuItems = useMemo(() => {
    if (!contextMenu) return [];
    const p = contextMenu.pipeline;
    return [
      {
        label: 'Open Designer',
        icon: 'M13.5 6H5.25A2.25 2.25 0 003 8.25v10.5A2.25 2.25 0 005.25 21h10.5A2.25 2.25 0 0018 18.75V10.5m-10.5 6L21 3m0 0h-5.25M21 3v5.25',
        onClick: () => navigate(`/pipelines/${p.id}/designer`),
      },
      {
        label: 'Duplicate',
        icon: menuIcons.copy,
        onClick: () => handleDuplicate(p),
      },
      { label: '', onClick: () => {}, divider: true },
      ...(p.status !== PipelineStatus.ARCHIVED && p.status !== PipelineStatus.DRAFT
        ? [{
            label: 'Archive',
            icon: 'M20.25 7.5l-.625 10.632a2.25 2.25 0 01-2.247 2.118H6.622a2.25 2.25 0 01-2.247-2.118L3.75 7.5m8.25 3v6.75m0 0l-3-3m3 3l3-3M3.375 7.5h17.25c.621 0 1.125-.504 1.125-1.125v-1.5c0-.621-.504-1.125-1.125-1.125H3.375c-.621 0-1.125.504-1.125 1.125v1.5c0 .621.504 1.125 1.125 1.125z',
            onClick: () => handleArchive(p),
          }]
        : []),
      {
        label: p.status === PipelineStatus.DRAFT ? 'Delete' : 'Delete (Archive)',
        icon: menuIcons.delete,
        onClick: () => confirmDeleteOrArchive(p),
        danger: true,
        disabled: p.status === PipelineStatus.ACTIVE,
      },
    ];
  }, [contextMenu, navigate, handleDuplicate, handleArchive, confirmDeleteOrArchive]);

  // ---- Render ----

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

      {/* Search + Status Filter Pills */}
      <div className="space-y-3">
        <div className="relative">
          <svg className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
          </svg>
          <input
            type="text"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search pipelines by name or description..."
            className="w-full rounded-lg border border-slate-200 bg-white py-2 pl-10 pr-4 text-sm text-slate-900 placeholder:text-slate-400 focus:border-vessel-400 focus:outline-none focus:ring-2 focus:ring-vessel-100"
          />
          {search && (
            <button
              onClick={() => setSearch('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 rounded p-0.5 text-slate-400 hover:text-slate-600"
            >
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>

        <div className="flex gap-2">
          {STATUS_FILTERS.map((s) => {
            const isActive = statusFilter === s;
            const count = statusCounts[s] || 0;
            const label = s === 'ALL' ? 'All' : s.charAt(0) + s.slice(1).toLowerCase();
            return (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1.5 text-xs font-medium transition-colors ${
                  isActive
                    ? 'bg-vessel-600 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {label}
                <span className={`rounded-full px-1.5 py-0.5 text-[10px] font-bold ${
                  isActive ? 'bg-white/20 text-white' : 'bg-slate-200 text-slate-500'
                }`}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Pipeline Groups */}
      {filteredPipelines.length === 0 ? (
        search || statusFilter !== 'ALL' ? (
          <div className="rounded-xl border-2 border-dashed border-slate-200 py-12 text-center">
            <svg className="mx-auto h-10 w-10 text-slate-300" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
            </svg>
            <p className="mt-2 text-sm font-medium text-slate-500">No pipelines match your filters</p>
            <button
              onClick={() => { setSearch(''); setStatusFilter('ALL'); }}
              className="mt-2 text-xs font-medium text-vessel-600 hover:text-vessel-700"
            >
              Clear filters
            </button>
          </div>
        ) : (
          <EmptyState
            title="No pipelines yet"
            description="Create your first pipeline to start processing data."
            action={{ label: 'Create Pipeline', onClick: handleCreatePipeline }}
          />
        )
      ) : (
        <div className="space-y-6">
          {(statusFilter === 'ALL' ? GROUP_ORDER : [statusFilter as PipelineStatus]).map((status) => {
            const group = groupedPipelines[status];
            if (!group || group.length === 0) return null;
            return (
              <div key={status}>
                {statusFilter === 'ALL' && (
                  <div className="mb-3 flex items-center gap-2">
                    <h2 className="text-sm font-semibold text-slate-700">
                      {status.charAt(0) + status.slice(1).toLowerCase()}
                    </h2>
                    <span className="rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-bold text-slate-500">
                      {group.length}
                    </span>
                  </div>
                )}
                <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                  {group.map((pipeline) => (
                    <div
                      key={pipeline.id}
                      className="card group relative p-5 transition-shadow hover:shadow-md"
                      onContextMenu={(e) => openMenu(e, pipeline)}
                    >
                      <Link
                        to={`/pipelines/${pipeline.id}/designer`}
                        className="absolute inset-0 z-0 rounded-xl"
                      />
                      <div className="relative z-10 flex items-start justify-between">
                        <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-vessel-50">
                          <svg className="h-5 w-5 text-vessel-600" fill="none" viewBox="0 0 24 24" strokeWidth={1.5} stroke="currentColor">
                            <path strokeLinecap="round" strokeLinejoin="round" d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25H12" />
                          </svg>
                        </div>
                        <div className="flex items-center gap-2">
                          <StatusBadge status={pipeline.status} />
                          <button
                            onClick={(e) => openMenu(e, pipeline)}
                            className="rounded p-1 text-slate-400 opacity-0 transition-opacity hover:bg-slate-100 hover:text-slate-600 group-hover:opacity-100"
                          >
                            <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                              <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 12.75a.75.75 0 110-1.5.75.75 0 010 1.5zM12 18.75a.75.75 0 110-1.5.75.75 0 010 1.5z" />
                            </svg>
                          </button>
                        </div>
                      </div>

                      <h3 className="relative z-10 mt-3 text-sm font-semibold text-slate-900 group-hover:text-vessel-700">
                        {pipeline.name}
                      </h3>
                      <p className="relative z-10 mt-1 line-clamp-2 text-xs text-slate-500">
                        {pipeline.description}
                      </p>

                      <div className="relative z-10 mt-4 flex items-center gap-3 border-t border-slate-100 pt-3">
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
                    </div>
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Context Menu */}
      {contextMenu && (
        <ContextMenu
          x={contextMenu.x}
          y={contextMenu.y}
          items={menuItems}
          onClose={() => setContextMenu(null)}
        />
      )}

      {/* Delete Confirmation Modal */}
      {deleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50">
          <div className="mx-4 w-full max-w-md rounded-xl bg-white p-6 shadow-2xl">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 items-center justify-center rounded-full bg-red-100">
                <svg className="h-5 w-5 text-red-600" fill="none" viewBox="0 0 24 24" strokeWidth={2} stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-slate-900">Delete pipeline</h3>
                <p className="mt-1 text-sm text-slate-500">
                  Delete pipeline &ldquo;{deleteModal.name}&rdquo;? This cannot be undone.
                </p>
              </div>
            </div>
            <div className="mt-5 flex justify-end gap-2">
              <button
                onClick={() => setDeleteModal(null)}
                className="btn-secondary text-xs"
              >
                Cancel
              </button>
              <button
                onClick={() => handleDelete(deleteModal)}
                className="rounded-lg bg-red-600 px-4 py-2 text-xs font-medium text-white transition-colors hover:bg-red-700"
              >
                Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
