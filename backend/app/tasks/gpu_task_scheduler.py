import time
from typing import Any, Dict, List


class GPUTaskScheduler:
    """Schedules, batches, and prioritizes neural lip-sync GPU rendering tasks."""

    @staticmethod
    def batch_segments_for_gpu(
        segments: List[Any],
        batch_size: int = 15,
    ) -> List[List[Any]]:
        """Splits long segment lists into concurrent GPU worker batches."""
        batches = []
        for i in range(0, len(segments), batch_size):
            batches.append(segments[i : i + batch_size])
        return batches

    @staticmethod
    def estimate_eta_seconds(
        total_segments: int,
        completed_segments: int,
        elapsed_seconds: float,
    ) -> float:
        """Calculates dynamic Estimated Time to Arrival (ETA) in seconds."""
        if completed_segments == 0:
            # Assume average 6.0 seconds per segment inference
            return float(total_segments * 6.0)
        
        avg_time_per_segment = elapsed_seconds / completed_segments
        remaining_segments = total_segments - completed_segments
        return round(float(remaining_segments * avg_time_per_segment), 1)


gpu_scheduler = GPUTaskScheduler()
