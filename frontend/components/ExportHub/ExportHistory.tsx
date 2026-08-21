'use client';

import React, { useEffect, useState } from 'react';
import { apiClient } from '../../services/apiClient';

interface ExportHistoryItem {
  id: string;
  format: string;
  resolution: string;
  target_language: string;
  status: string;
  output_video_url?: string;
  filesize_bytes?: number;
  created_at: string;
}

export const ExportHistory: React.FC = () => {
  const [history, setHistory] = useState<ExportHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    async function loadHistory() {
      setLoading(true);
      try {
        const res = await apiClient.get<ExportHistoryItem[]>('/export/history');
        setHistory(res);
      } catch (err) {
        console.error('Failed to load export history logs:', err);
      } finally {
        setLoading(false);
      }
    }
    loadHistory();
  }, []);

  const formatSize = (bytes?: number) => {
    if (!bytes) return '0 B';
    const mb = bytes / (1024 * 1024);
    return `${mb.toFixed(1)} MB`;
  };

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl p-5 space-y-4 select-none">
      <div className="flex justify-between items-center pb-2 border-b border-slate-800">
        <h4 className="text-xs font-bold uppercase tracking-wider text-slate-400">Past Exports History</h4>
        <span className="text-[10px] text-slate-500">Download links expire in 7 days</span>
      </div>

      {loading && history.length === 0 ? (
        <div className="text-center text-slate-600 text-xs py-8">Loading history logs...</div>
      ) : history.length === 0 ? (
        <div className="text-center text-slate-600 text-xs py-8">No completed exports found.</div>
      ) : (
        <div className="space-y-3 max-h-60 overflow-y-auto pr-2">
          {history.map((item) => (
            <div key={item.id} className="flex justify-between items-center bg-slate-950/40 p-3 rounded-lg border border-slate-850">
              <div>
                <h5 className="text-xs font-bold text-white uppercase">{item.format} • {item.resolution} ({item.target_language})</h5>
                <p className="text-[10px] text-slate-500 mt-0.5">Size: {formatSize(item.filesize_bytes)} • Date: {new Date(item.created_at).toLocaleDateString()}</p>
              </div>

              {item.output_video_url ? (
                <a
                  href={item.output_video_url}
                  download
                  className="bg-indigo-600 hover:bg-indigo-700 text-white font-semibold py-1 px-3 rounded text-[10px] transition"
                >
                  Download
                </a>
              ) : (
                <span className="text-[10px] bg-red-950 text-red-400 px-2 py-0.5 rounded border border-red-900 uppercase">
                  {item.status}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
export default ExportHistory;
