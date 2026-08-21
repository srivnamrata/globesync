from typing import Tuple


class AudioMatcher:
    """Calculates time-stretching factors, alignment windows, and duration error deltas."""

    @staticmethod
    def calculate_retiming_factor(
        actual_duration_ms: int,
        target_duration_ms: int,
        min_factor: float = 0.75,
        max_factor: float = 1.35,
    ) -> Tuple[float, int]:
        """
        Calculates exact speed factor:
        Factor = actual_duration / target_duration.
        Clamped between [min_factor, max_factor] to prevent unnatural audio artifacts.
        Returns (clamped_speed_factor, duration_delta_ms).
        """
        if target_duration_ms <= 0 or actual_duration_ms <= 0:
            return 1.0, 0

        raw_factor = actual_duration_ms / target_duration_ms
        clamped_factor = round(float(max(min_factor, min(max_factor, raw_factor))), 3)
        delta_ms = actual_duration_ms - target_duration_ms

        return clamped_factor, delta_ms


audio_matcher = AudioMatcher()
