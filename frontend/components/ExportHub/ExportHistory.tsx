'use client';

import React, { useEffect, useState } from 'react';
import { projectService, type ProjectExportHistoryItem, type ProjectRenderHistoryItem } from '../../services/projectService';
import { StatePanel, StatusBadge } from '../ui';

function formatSize(bytes?: number | null): string {
  if (!bytes) return 'Size unavailable';
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function getStatusTone(status: string): 'processing' | 'success' | 'error' {
  if (status === 'completed') return 'success';
  if (status === 'failed') return 'error';
  return 'processing';
}

export const ExportHistory: React.FC<{ projectId: string }> = ({ projectId }) => {
  const [history, setHistory] = useState<ProjectExportHistoryItem[]>([]);
  const [renderHistory, setRenderHistory] = useState<ProjectRenderHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;

    async function loadHistory() {
      setLoading(true);
      setError(null);
      try {
        const [exportResponse, renderResponse] = await Promise.all([
          projectService.getProjectExportHistory(projectId),
          projectService.getProjectRenderHistory(projectId),
        ]);
        if (active) {
          setHistory(exportResponse);
          setRenderHistory(renderResponse);
        }
      } catch (loadError) {
        console.error('Failed to load project export history:', loadError);
        if (active) setError('Export history is unavailable right now. Your existing outputs are unchanged.');
      } finally {
        if (active) setLoading(false);
      }
    }

    void loadHistory();
    return () => { active = false; };
  }, [projectId]);

  return (
    <section className="gs-panel space-y-4 p-5" aria-labelledby="export-history-heading">
      <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-2">
        <h2 id="export-history-heading" className="text-xs font-bold uppercase tracking-wider text-slate-400">Project outputs</h2>
        <span className="text-[10px] text-slate-500">Authorized links expire after 2 hours</span>
      </div>

      {loading && history.length === 0 && renderHistory.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500" role="status">Loading export history...</div>
      ) : error ? (
        <StatePanel title="Could not load export history" tone="warning">{error}</StatePanel>
      ) : history.length === 0 && renderHistory.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500">No exports have been created for this project yet.</div>
      ) : (
        <div className="max-h-80 space-y-5 overflow-y-auto pr-2">
          {renderHistory.length > 0 && (
            <section className="space-y-3" aria-label="Dub and lip-sync outputs">
              <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Dub and lip-sync builds</h3>
              {renderHistory.map((item) => (
                <div key={item.job_id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-xs font-bold text-white">{item.render_mode === 'dub_only' ? 'Dub only' : 'Dub + Lip-Sync'}</h4>
                      <StatusBadge tone={getStatusTone(item.status)} className="px-1.5 py-0.5 text-[10px] uppercase">{item.status}</StatusBadge>
                    </div>
                    <p className="mt-1 text-[10px] text-slate-500">
                      {item.target_language.toUpperCase()} · {new Date(item.created_at).toLocaleString()}
                    </p>
                  </div>
                  {item.output_video_url ? (
                    <a href={item.output_video_url} download className="gs-button-primary min-h-8 shrink-0 rounded-lg px-3 py-1 text-[10px]">Download</a>
                  ) : (
                    <span className="shrink-0 text-[10px] text-slate-500">No output</span>
                  )}
                </div>
              ))}
            </section>
          )}
          {history.length > 0 && <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Format exports</h3>}
          {history.map((item) => (
            <div key={item.id} className="flex items-center justify-between gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-xs font-bold uppercase text-white">{item.format} | {item.resolution} | {item.target_language}</h3>
                  <StatusBadge tone={getStatusTone(item.status)} className="px-1.5 py-0.5 text-[10px] uppercase">{item.status}</StatusBadge>
                </div>
                <p className="mt-1 text-[10px] text-slate-500">{formatSize(item.filesize_bytes)} | {new Date(item.created_at).toLocaleDateString()}</p>
              </div>

              {item.output_video_url ? (
                <a href={item.output_video_url} download className="gs-button-primary min-h-8 shrink-0 rounded-lg px-3 py-1 text-[10px]">Download</a>
              ) : (
                <span className="shrink-0 text-[10px] text-slate-500">No output</span>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
};

export default ExportHistory;
