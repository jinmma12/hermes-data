interface StatusBadgeProps {
  status: string;
  size?: 'sm' | 'md';
}

const statusStyles: Record<string, string> = {
  // Pipeline statuses
  DRAFT: 'bg-slate-100 text-slate-700',
  ACTIVE: 'bg-emerald-100 text-emerald-700',
  PAUSED: 'bg-amber-100 text-amber-700',
  ARCHIVED: 'bg-slate-100 text-slate-500',

  // Activation statuses
  STARTING: 'bg-blue-100 text-blue-700',
  RUNNING: 'bg-emerald-100 text-emerald-700',
  STOPPING: 'bg-amber-100 text-amber-700',
  STOPPED: 'bg-slate-100 text-slate-600',
  ERROR: 'bg-red-100 text-red-700',

  // Job statuses
  DETECTED: 'bg-blue-100 text-blue-700',
  QUEUED: 'bg-indigo-100 text-indigo-700',
  PROCESSING: 'bg-yellow-100 text-yellow-700',
  COMPLETED: 'bg-emerald-100 text-emerald-700',
  FAILED: 'bg-red-100 text-red-700',

  // Execution statuses
  CANCELLED: 'bg-slate-100 text-slate-600',
  SKIPPED: 'bg-slate-100 text-slate-500',

  // Reprocess statuses
  PENDING: 'bg-amber-100 text-amber-700',
  APPROVED: 'bg-blue-100 text-blue-700',
  EXECUTING: 'bg-yellow-100 text-yellow-700',
  DONE: 'bg-emerald-100 text-emerald-700',
  REJECTED: 'bg-red-100 text-red-700',
};

export default function StatusBadge({ status, size = 'sm' }: StatusBadgeProps) {
  const style = statusStyles[status] || 'bg-slate-100 text-slate-600';
  const sizeClass = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm';

  return (
    <span className={`inline-flex items-center rounded-full font-medium ${style} ${sizeClass}`}>
      {status}
    </span>
  );
}
