'use client';

import React from 'react';
import { useProcessingStatus } from '../../hooks/useProcessingStatus';

interface ExportProgressProps {
  jobId: string | undefined;
}

export const ExportProgress: React.FC<ExportProgressProps> = ({ jobId }) => {
  const { status, error } = useProcessingStatus(jobId, 'lipsync'); // Maps progress socket streams

  if (!jobId || !status) return null;

  const percent = status.progress_percent || 0;
  const isFailed = status.status === 'failed';

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 shadow-xl select-none">
      <div className="flex justify-between items-center">
        <div>
          <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Render Progress Status</h4>
          <p className="text-[10px] text-slate-500 mt-0.5">Stage: {status.message || 'Queued in worker pool'}</p>
        </div>
        {status.eta_seconds !== undefined && status.eta_seconds > 0 && (
          <span className="text-xs text-indigo-400 font-mono">
            ETA: {Math.ceil(status.eta_seconds)}s
          </span>
        )}
      </div>

      <div className="space-y-1.5">
        <div className="flex justify-between text-xs font-semibold">
          <span className="text-slate-400">Encoding & Muxing streams</span>
          <span className={isFailed ? 'text-red-400' : 'text-indigo-400'}>{percent}%</span>
        </div>
        <div className="w-full h-2 bg-slate-950 rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${isFailed ? 'bg-red-500' : 'bg-indigo-500'}`}
            style={{ width: `${percent}%` }}
          />
        </div>
      </div>

      {error && (
        <div className="text-[10px] bg-red-950/40 border border-red-900 text-red-400 px-3 py-1.5 rounded-md">
          {error}
        </div>
      )}
    </div>
  );
};
export default ExportProgress;
