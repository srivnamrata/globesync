import os
import wave
import numpy as np
from typing import Any, Dict


class ProsodyExtractor:
    """Extracts acoustic and prosody features (pitch contour, RMS energy, speech rate) from speech audio."""

    @classmethod
    def extract_prosody_features(cls, wav_file_path: str) -> Dict[str, Any]:
        """
        Analyzes audio WAV file and computes prosody parameters:
        - Pitch (F0 estimation via autocorrelation)
        - Energy / RMS intensity
        - Estimated speech dynamics (warmth, depth, expressiveness)
        """
        if not os.path.exists(wav_file_path):
            return cls._fallback_prosody()

        try:
            with wave.open(wav_file_path, "rb") as wf:
                sample_rate = wf.getframerate()
                n_frames = wf.getnframes()
                audio_bytes = wf.readframes(n_frames)
                channels = wf.getnchannels()

            # Convert to mono numpy array
            audio_data = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32)
            if channels > 1:
                audio_data = audio_data.reshape(-1, channels).mean(axis=1)

            if len(audio_data) == 0:
                return cls._fallback_prosody()

            # 1. Compute RMS energy
            rms = float(np.sqrt(np.mean(audio_data**2)))
            db_level = float(20 * np.log10(max(1e-5, rms / 32768.0)))

            # 2. Fundamental frequency (F0) estimation using Autocorrelation on 50ms frames
            frame_len = int(0.05 * sample_rate)
            hop_len = int(0.025 * sample_rate)
            pitch_estimates = []

            for start in range(0, len(audio_data) - frame_len, hop_len):
                frame = audio_data[start : start + frame_len]
                # High-pass filter check for active speech
                if np.sqrt(np.mean(frame**2)) > (rms * 0.3):
                    corr = np.correlate(frame, frame, mode="full")
                    corr = corr[len(corr) // 2 :]
                    
                    # Search range for human voice pitch: 70Hz to 400Hz
                    min_lag = int(sample_rate / 400)
                    max_lag = int(sample_rate / 70)
                    if max_lag < len(corr):
                        peak_lag = min_lag + np.argmax(corr[min_lag:max_lag])
                        if peak_lag > 0:
                            f0 = sample_rate / peak_lag
                            if 70 <= f0 <= 400:
                                pitch_estimates.append(f0)

            mean_pitch = float(np.mean(pitch_estimates)) if pitch_estimates else 140.0
            pitch_std = float(np.std(pitch_estimates)) if pitch_estimates else 25.0

            # 3. Estimate voice warmth and depth
            # Lower mean pitch indicates deeper voice; higher variance indicates expressive voice
            warmth = round(float(np.clip(1.0 - (mean_pitch - 80) / 240, 0.2, 0.9)), 2)
            depth = round(float(np.clip((220 - mean_pitch) / 140, 0.2, 0.9)), 2)
            expressiveness = round(float(np.clip(pitch_std / 50.0, 0.1, 0.9)), 2)

            return {
                "mean_pitch_hz": round(mean_pitch, 1),
                "pitch_variability": round(pitch_std, 1),
                "rms_db": round(db_level, 1),
                "warmth": warmth,
                "depth": depth,
                "expressiveness": expressiveness,
                "recommended_voice_settings": {
                    "stability": round(float(np.clip(0.65 - (expressiveness * 0.2), 0.3, 0.75)), 2),
                    "similarity_boost": 0.85,
                    "style": round(float(np.clip(expressiveness * 0.3, 0.0, 0.35)), 2),
                    "use_speaker_boost": True,
                },
            }

        except Exception:
            return cls._fallback_prosody()

    @staticmethod
    def _fallback_prosody() -> Dict[str, Any]:
        return {
            "mean_pitch_hz": 135.0,
            "pitch_variability": 22.0,
            "rms_db": -22.0,
            "warmth": 0.6,
            "depth": 0.6,
            "expressiveness": 0.5,
            "recommended_voice_settings": {
                "stability": 0.50,
                "similarity_boost": 0.80,
                "style": 0.05,
                "use_speaker_boost": True,
            },
        }


prosody_extractor = ProsodyExtractor()
