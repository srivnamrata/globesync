'use client';

import React, { useState } from 'react';
import { useUIStore } from '../../store/uiStore';
import { useExportStore, ExportJob } from '../../store/exportStore';
import { EXPORT_PRESETS, estimateExportCostUSD } from '../../utils/exportPresets';
import { apiClient } from '../../services/apiClient';

interface ExportDialogProps {
  projectId: string;
  mediaFileId: string;
  transcriptId: string;
  targetLanguage: string;
  durationSeconds: number;
}

export const ExportDialog: React.FC<ExportDialogProps> = ({
  projectId,
  mediaFileId,
  transcriptId,
  targetLanguage,
  durationSeconds,
}) => {
  const isOpen = useUIStore((s) => s.isExportDialogOpen);
  const setOpen = useUIStore((s) => s.setExportDialogOpen);
  const addJob = useExportStore((s) => s.addJob);

  const [format, setFormat] = useState<'mp4' | 'webm'>('mp4');
  const [resolution, setResolution] = useState<'720p' | '1080p' | '4k'>('1080p');
  const [codec, setCodec] = useState<'h264' | 'h265'>('h264');
  const [burnSubtitles, setBurnSubtitles] = useState(false);
  const [colorGrading, setColorGrading] = useState(false);

  if (!isOpen) return null;

  const costEst = estimateExportCostUSD(durationSeconds, resolution, 'normal');

  const handleStartExport = async () => {
    try {
      const body = {
        media_file_id: mediaFileId,
        transcript_id: transcriptId,
        project_id: projectId,
        target_language: targetLanguage,
        format,
        resolution,
        frame_rate: 30,
        codec,
        video_quality: 'normal',
        audio_codec: 'aac',
        subtitles: {
          enabled: burnSubtitles,
          format: 'burnt-in',
          appearance: { font: 'Arial', size: 16, color: '#FFFFFF', background_color: 'rgba(0,0,0,0.8)' },
        },
        post_processing: {
          color_grading: colorGrading,
          watermark: null,
          audio_normalization: true,
        },
      };

      const res = await apiClient.post<{ job_id: string }>('/export/render', body);

      const newJob: ExportJob = {
        id: res.job_id,
        projectId,
        targetLanguage,
        burnInSubtitles: burnSubtitles,
        status: 'queued',
        progressPercent: 0,
        createdAt: new Date().toISOString(),
      };

      addJob(newJob);
      setOpen(false);
    } catch (err) {
      console.error('Failed to trigger export render:', err);
    }
  };

  return (
    <div className="fixed inset-0 bg-slate-950/80 backdrop-blur-sm z-50 flex items-center justify-center p-4">
      <div className="bg-slate-900 border border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-6 shadow-2xl select-none">
        <div>
          <h3 className="text-lg font-bold text-white">Export & Rendering Settings</h3>
          <p className="text-xs text-slate-400 mt-1">Configure codecs, layouts and overlays before processing</p>
        </div>

        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">Format</label>
              <select
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs focus:outline-none"
                value={format}
                onChange={(e) => setFormat(e.target.value as any)}
              >
                <option value="mp4">MP4 Video</option>
                <option value="webm">WebM HTML5</option>
              </select>
            </div>

            <div>
              <label className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">Resolution</label>
              <select
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs focus:outline-none"
                value={resolution}
                onChange={(e) => setResolution(e.target.value as any)}
              >
                <option value="720p">720p Standard HD</option>
                <option value="1080p">1080p Full HD</option>
                <option value="4k">4K Ultra HD</option>
              </select>
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-[10px] font-semibold text-slate-400 uppercase tracking-wider mb-2">Video Codec</label>
              <select
                className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-white text-xs focus:outline-none"
                value={codec}
                onChange={(e) => setCodec(e.target.value as any)}
              >
                <option value="h264">H.264 (Broad Compatibility)</option>
                <option value="h265">H.265 / HEVC (Efficient)</option>
              </select>
            </div>

            <div className="flex flex-col justify-end">
              <label className="flex items-center gap-2.5 text-xs text-slate-300 cursor-pointer h-9">
                <input
                  type="checkbox"
                  checked={burnSubtitles}
                  onChange={(e) => setBurnSubtitles(e.target.checked)}
                  className="rounded border-slate-800 text-indigo-600 focus:ring-0 w-4 h-4 bg-slate-950"
                />
                Burn Subtitles to Video Pixels
              </label>
            </div>
          </div>

          <div className="flex items-center justify-between bg-slate-950/40 p-4 rounded-xl border border-slate-850">
            <div>
              <span className="text-xs text-slate-400">Estimated cloud GPU costs:</span>
              <span className="text-sm font-bold text-white ml-2">${costEst.toFixed(4)}</span>
            </div>
            <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={colorGrading}
                onChange={(e) => setColorGrading(e.target.checked)}
                className="rounded border-slate-800 text-indigo-600 focus:ring-0 bg-slate-950"
              />
              Subtle Color-Grade Enhancements
            </label>
          </div>
        </div>

        <div className="flex justify-end gap-3 pt-2">
          <button
            onClick={() => setOpen(false)}
            className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 text-sm font-semibold transition"
          >
            Cancel
          </button>
          <button
            onClick={handleStartExport}
            className="px-5 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white text-sm font-semibold transition"
          >
            Queue Render Task
          </button>
        </div>
      </div>
    </div>
  );
};
export default ExportDialog;
