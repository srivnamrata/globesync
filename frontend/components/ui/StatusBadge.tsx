import type { ReactNode } from 'react';

type StatusTone = 'neutral' | 'info' | 'processing' | 'success' | 'warning' | 'error';

type StatusBadgeProps = {
  children: ReactNode;
  tone?: StatusTone;
  className?: string;
};

const toneClasses: Record<StatusTone, string> = {
  neutral: 'border-slate-600/70 bg-slate-800/80 text-slate-200',
  info: 'border-sky-400/30 bg-sky-400/10 text-sky-200',
  processing: 'border-amber-400/30 bg-amber-400/10 text-amber-100',
  success: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-100',
  warning: 'border-orange-400/30 bg-orange-400/10 text-orange-100',
  error: 'border-rose-400/30 bg-rose-400/10 text-rose-100',
};

export function StatusBadge({ children, className = '', tone = 'neutral' }: StatusBadgeProps) {
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-semibold ${toneClasses[tone]} ${className}`}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {children}
    </span>
  );
}
