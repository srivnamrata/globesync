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

function formatStatus(status: string): string {
  if (status === 'completed') return 'Completed';
  if (status === 'failed') return 'Needs attention';
  if (status === 'in_progress' || status === 'processing') return 'In progress';
  return 'Queued';
}

function formatStage(stage?: string | null): string {
  if (!stage) return 'No checkpoint recorded';
  return stage.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function formatElapsedTime(seconds?: number | null): string | null {
  if (!seconds || seconds <= 0) return null;
  if (seconds < 60) return `${Math.round(seconds)}s render time`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s render time`;
}

export const ExportHistory: React.FC<{ projectId: string }> = ({ projectId }) => {
  const [history, setHistory] = useState<ProjectExportHistoryItem[]>([]);
  const [renderHistory, setRenderHistory] = useState<ProjectRenderHistoryItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;

    async function loadHistory() {
      setLoading(true);
      setExportError(null);
      setRenderError(null);
      const [exportResult, renderResult] = await Promise.allSettled([
          projectService.getProjectExportHistory(projectId),
          projectService.getProjectRenderHistory(projectId),
      ]);
      if (!active) return;

      if (exportResult.status === 'fulfilled') {
        setHistory(exportResult.value);
      } else {
        console.error('Failed to load format export history:', exportResult.reason);
        setExportError('Format export history is unavailable right now. Existing outputs are unchanged.');
      }
      if (renderResult.status === 'fulfilled') {
        setRenderHistory(renderResult.value);
      } else {
        console.error('Failed to load dub and lip-sync history:', renderResult.reason);
        setRenderError('Dub and lip-sync history is unavailable right now. Existing outputs are unchanged.');
      }
      setLoading(false);
    }

    void loadHistory();
    return () => { active = false; };
  }, [projectId, reloadToken]);

  const retryAction = (
    <button
      type="button"
      onClick={() => setReloadToken((token) => token + 1)}
      disabled={loading}
      aria-label={loading ? 'Retrying export history' : 'Retry export history'}
      className="gs-button-secondary min-h-8 rounded-lg px-3 py-1 text-[10px]"
    >
      {loading ? 'Retrying...' : 'Try again'}
    </button>
  );

  return (
    <section className="gs-panel space-y-4 p-5" aria-labelledby="export-history-heading" aria-busy={loading}>
      <div className="flex items-center justify-between gap-3 border-b border-slate-800 pb-2">
        <h2 id="export-history-heading" className="text-xs font-bold uppercase tracking-wider text-slate-400">Project outputs</h2>
        <span className="text-[10px] text-slate-500">Authorized links expire after 2 hours</span>
      </div>

      {loading && history.length === 0 && renderHistory.length === 0 ? (
        <div className="py-8 text-center text-xs text-slate-500" role="status">Loading export history...</div>
      ) : history.length === 0 && renderHistory.length === 0 && !exportError && !renderError ? (
        <div className="py-8 text-center text-xs text-slate-500">No exports have been created for this project yet.</div>
      ) : (
        <div className="max-h-80 space-y-5 overflow-y-auto pr-2">
          {renderError && <StatePanel title="Dub and Lip-Sync history unavailable" tone="warning" action={retryAction}>{renderError}</StatePanel>}
          {renderHistory.length > 0 && (
            <section className="space-y-3" aria-label="Dub and lip-sync outputs">
              <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Dub and lip-sync builds</h3>
              {renderHistory.map((item) => (
                <div key={item.job_id} className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3 sm:flex-row sm:items-center sm:justify-between">
                  <div className="min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h4 className="text-xs font-bold text-white">{item.render_mode === 'dub_only' ? 'Dub only' : 'Dub + Lip-Sync'}</h4>
                      <StatusBadge tone={getStatusTone(item.status)} className="px-1.5 py-0.5 text-[10px] uppercase">{formatStatus(item.status)}</StatusBadge>
                    </div>
                    <p className="mt-1 text-[10px] text-slate-500">
                      {item.target_language.toUpperCase()} · {formatSize(item.output_filesize_bytes)} · {formatElapsedTime(item.execution_time_seconds) ?? 'Render time unavailable'} · {new Date(item.created_at).toLocaleString()}
                    </p>
                    {item.status === 'failed' && (
                      <p className="mt-2 text-[10px] text-rose-300">
                        Last successful stage: {formatStage(item.last_successful_stage)}. Start a new build after resolving the issue.
                      </p>
                    )}
                  </div>
                  {item.output_video_url ? (
                    <div className="flex shrink-0 gap-2 self-start sm:self-auto">
                      <a href={item.output_video_url} target="_blank" rel="noreferrer" className="gs-button-secondary min-h-8 rounded-lg px-3 py-1 text-[10px]">Open</a>
                      <a href={item.download_video_url ?? item.output_video_url} download className="gs-button-primary min-h-8 rounded-lg px-3 py-1 text-[10px]">Download</a>
                    </div>
                  ) : (
                    <span className="shrink-0 text-[10px] text-slate-500">No output</span>
                  )}
                </div>
              ))}
            </section>
          )}
          {exportError && <StatePanel title="Format export history unavailable" tone="warning" action={retryAction}>{exportError}</StatePanel>}
          {history.length > 0 && <h3 className="text-[10px] font-bold uppercase tracking-wider text-slate-500">Format exports</h3>}
          {history.map((item) => (
            <div key={item.id} className="flex flex-col gap-3 rounded-lg border border-slate-800 bg-slate-950/40 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <h3 className="text-xs font-bold uppercase text-white">{item.format} | {item.resolution} | {item.target_language}</h3>
                  <StatusBadge tone={getStatusTone(item.status)} className="px-1.5 py-0.5 text-[10px] uppercase">{formatStatus(item.status)}</StatusBadge>
                </div>
                <p className="mt-1 text-[10px] text-slate-500">{formatSize(item.filesize_bytes)} | {new Date(item.created_at).toLocaleDateString()}</p>
              </div>

              {item.output_video_url ? (
                <div className="flex shrink-0 gap-2 self-start sm:self-auto">
                  <a href={item.output_video_url} target="_blank" rel="noreferrer" className="gs-button-secondary min-h-8 rounded-lg px-3 py-1 text-[10px]">Open</a>
                  <a href={item.download_video_url ?? item.output_video_url} download className="gs-button-primary min-h-8 rounded-lg px-3 py-1 text-[10px]">Download</a>
                </div>
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
