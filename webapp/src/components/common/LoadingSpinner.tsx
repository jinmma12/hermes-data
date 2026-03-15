interface LoadingSpinnerProps {
  size?: 'sm' | 'md' | 'lg';
  message?: string;
}

export default function LoadingSpinner({ size = 'md', message }: LoadingSpinnerProps) {
  const sizeClasses = {
    sm: 'h-4 w-4 border-2',
    md: 'h-8 w-8 border-2',
    lg: 'h-12 w-12 border-3',
  };

  return (
    <div className="flex flex-col items-center justify-center gap-3 py-12">
      <div
        className={`animate-spin rounded-full border-slate-200 border-t-hermes-600 ${sizeClasses[size]}`}
      />
      {message && <p className="text-sm text-slate-500">{message}</p>}
    </div>
  );
}
