import math
import re
from typing import Any, Dict, Optional, Tuple

# Emotion & Style preset configurations for ElevenLabs Multilingual v2
EMOTION_STYLE_PRESETS: Dict[str, Dict[str, float]] = {
    "natural": {"stability": 0.50, "similarity_boost": 0.80, "style": 0.05, "use_speaker_boost": True},
    "formal": {"stability": 0.65, "similarity_boost": 0.85, "style": 0.00, "use_speaker_boost": True},
    "friendly": {"stability": 0.45, "similarity_boost": 0.80, "style": 0.20, "use_speaker_boost": True},
    "energetic": {"stability": 0.35, "similarity_boost": 0.75, "style": 0.35, "use_speaker_boost": True},
    "empathetic": {"stability": 0.55, "similarity_boost": 0.85, "style": 0.15, "use_speaker_boost": True},
    "dramatic": {"stability": 0.30, "similarity_boost": 0.70, "style": 0.45, "use_speaker_boost": True},
}


class ElevenLabsUtils:
    """Helper utilities for voice design tuning, emotion mappings, pitch shifting, and reverb estimation."""

    @classmethod
    def get_voice_settings_for_style(
        cls,
        emotion: str = "natural",
        warmth: float = 0.5,
        depth: float = 0.5,
        expressiveness: float = 0.5,
    ) -> Dict[str, Any]:
        """
        Builds calibrated ElevenLabs voice settings by blending emotion preset with acoustic prosody warmth/depth.
        """
        preset = EMOTION_STYLE_PRESETS.get(emotion.lower(), EMOTION_STYLE_PRESETS["natural"]).copy()

        # Modulate stability based on expressiveness (higher expressiveness -> lower stability for dynamic range)
        stability_adjusted = preset["stability"] - ((expressiveness - 0.5) * 0.2)
        preset["stability"] = round(float(max(0.25, min(0.85, stability_adjusted))), 2)

        # Modulate style based on warmth & expressiveness
        style_adjusted = preset["style"] + ((expressiveness - 0.5) * 0.15)
        preset["style"] = round(float(max(0.0, min(0.50, style_adjusted))), 2)

        # Higher warmth increases similarity boost
        sim_boost = preset["similarity_boost"] + ((warmth - 0.5) * 0.1)
        preset["similarity_boost"] = round(float(max(0.50, min(0.95, sim_boost))), 2)

        return preset

    @staticmethod
    def calculate_pitch_shift_factor(semitones: float) -> float:
        """
        Converts semitone delta (e.g. +2.0 or -2.0) into pitch frequency multiplier:
        Multiplier = 2^(semitones / 12.0)
        """
        clamped_semitones = max(-2.0, min(2.0, semitones))
        return round(math.pow(2.0, clamped_semitones / 12.0), 4)

    @staticmethod
    def estimate_room_reverb(audio_energy_decay_db: float) -> Optional[Dict[str, float]]:
        """
        Estimates room reverberation from energy decay rate (RT60 approximation).
        If decay is slow (> -15dB over 200ms), returns FFmpeg aecho / freeverb parameters.
        """
        if audio_energy_decay_db > -18.0:
            # Moderate room reverb detected (e.g. conference room or studio with slight reflection)
            return {
                "in_gain": 0.85,
                "out_gain": 0.90,
                "delays": 40.0,  # 40ms early reflections
                "decays": 0.25,
            }
        elif audio_energy_decay_db > -12.0:
            # Large hall / auditorium reverb
            return {
                "in_gain": 0.75,
                "out_gain": 0.85,
                "delays": 80.0,
                "decays": 0.40,
            }
        return None  # Dry studio vocal, no artificial reverb required


elevenlabs_utils = ElevenLabsUtils()
