import type { ReactNode } from 'react';

type StatePanelTone = 'info' | 'success' | 'warning' | 'error';

type StatePanelProps = {
  title: string;
  children: ReactNode;
  tone?: StatePanelTone;
  action?: ReactNode;
};

const toneClasses: Record<StatePanelTone, string> = {
  info: 'border-sky-400/30 bg-sky-400/10 text-sky-50',
  success: 'border-emerald-400/30 bg-emerald-400/10 text-emerald-50',
  warning: 'border-amber-400/30 bg-amber-400/10 text-amber-50',
  error: 'border-rose-400/30 bg-rose-400/10 text-rose-50',
};

export function StatePanel({ action, children, title, tone = 'info' }: StatePanelProps) {
  const role = tone === 'error' || tone === 'warning' ? 'alert' : 'status';

  return (
    <section className={`rounded-panel border p-4 ${toneClasses[tone]}`} role={role}>
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 className="text-sm font-semibold">{title}</h2>
          <div className="mt-1 text-sm leading-6 opacity-90">{children}</div>
        </div>
        {action}
      </div>
    </section>
  );
}
