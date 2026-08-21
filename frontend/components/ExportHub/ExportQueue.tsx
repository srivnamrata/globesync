'use client';

import React from 'react';
import { useExportStore } from '../../store/exportStore';
import { apiClient } from '../../services/apiClient';

export const ExportQueue: React.FC = () => {
  const { jobs, updateJobProgress } = useExportStore();

  const handleCancelExport = async (jobId: string) => {
    try {
      await apiClient.post(`/export/job/${jobId}/cancel`, {});
      updateJobProgress(jobId, 0, 'failed');
    } catch (err) {
      console.error('Failed to cancel active export:', err);
    }
  };

  const activeJobs = jobs.filter((j) => j.status === 'queued' || j.status === 'processing');

  if (activeJobs.length === 0) return null;

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 select-none shadow-xl">
      <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400 pb-2 border-b border-slate-800">Active Export Queue</h4>
      
      <div className="space-y-3">
        {activeJobs.map((job) => (
          <div key={job.id} className="flex justify-between items-center bg-slate-950/40 p-3 rounded-lg border border-slate-850">
            <div>
              <h5 className="text-xs font-bold text-white uppercase">Render Job: {job.id.substring(0, 8)}</h5>
              <p className="text-[10px] text-slate-500 mt-0.5">Language: {job.targetLanguage} • State: {job.status}</p>
            </div>

            <button
              onClick={() => handleCancelExport(job.id)}
              className="bg-red-950 hover:bg-red-900 text-red-400 border border-red-900 px-2.5 py-1 rounded text-[10px] transition"
            >
              Cancel
            </button>
          </div>
        ))}
      </div>
    </div>
  );
};
export default ExportQueue;
