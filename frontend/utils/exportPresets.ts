export interface ExportSettings {
  format: 'mp4' | 'webm' | 'mov' | 'avi';
  resolution: '720p' | '1080p' | '2k' | '4k';
  frame_rate: 24 | 30 | 60;
  codec: 'h264' | 'h265' | 'vp9' | 'av1';
  video_quality: 'fast' | 'normal' | 'high';
  audio_codec: 'aac' | 'opus';
  subtitles: {
    enabled: boolean;
    format: 'burnt-in' | 'srt' | 'vtt';
    appearance: {
      font: string;
      size: number;
      color: string;
      background_color: string;
    };
  };
  post_processing: {
    color_grading: boolean;
    watermark: string | null;
    audio_normalization: boolean;
  };
}

export const EXPORT_PRESETS = {
  web_standard: {
    format: 'mp4',
    resolution: '1080p',
    frame_rate: 30,
    codec: 'h264',
    video_quality: 'normal',
    audio_codec: 'aac',
    subtitles: {
      enabled: false,
      format: 'burnt-in',
      appearance: { font: 'Arial', size: 16, color: '#FFFFFF', background_color: 'rgba(0,0,0,0.8)' },
    },
    post_processing: { color_grading: false, watermark: null, audio_normalization: true },
  } as ExportSettings,
};

export function estimateExportCostUSD(
  durationSeconds: number,
  resolution: string,
  quality: string
): number {
  // Cloud GPU rendering cost estimation: base 0.002$ per second for 1080p
  let rate = 0.002;
  if (resolution === '4k') rate = 0.008;
  else if (resolution === '2k') rate = 0.004;

  if (quality === 'high') rate *= 1.5;

  return Number((durationSeconds * rate).toFixed(4));
}
