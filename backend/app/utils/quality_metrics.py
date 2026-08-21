from typing import Any, Dict


class QualityMetrics:
    """Computes lip-synchronization accuracy, visual naturalness, and quality confidence scores."""

    @staticmethod
    def evaluate_lipsync_quality(
        av_sync_error_ms: float,
        face_confidence: float,
        duration_ratio: float,
    ) -> Dict[str, Any]:
        """
        Evaluates rendered video quality on a scale of 0.00 to 1.00 (0% - 100%).
        Penalizes A/V sync drift > 100ms and low face visibility.
        """
        # 1. Sync score: 1.0 for 0ms, drops to 0.70 at 100ms, drops sharply above 100ms
        abs_drift = abs(av_sync_error_ms)
        if abs_drift <= 50:
            sync_score = 0.98 - (abs_drift / 50.0) * 0.05
        elif abs_drift <= 100:
            sync_score = 0.93 - ((abs_drift - 50) / 50.0) * 0.15
        else:
            sync_score = max(0.40, 0.78 - ((abs_drift - 100) / 100.0) * 0.35)

        # 2. Timing ratio closeness
        timing_score = max(0.60, min(1.0, 1.0 - abs(duration_ratio - 1.0) * 0.5))

        # 3. Overall composite quality score
        overall_score = round(
            float((sync_score * 0.50) + (face_confidence * 0.30) + (timing_score * 0.20)), 4
        )

        needs_review = overall_score < 0.80 or abs_drift > 100.0

        return {
            "overall_quality_score": overall_score,
            "sync_accuracy_score": round(float(sync_score), 4),
            "face_visibility_score": round(float(face_confidence), 4),
            "av_sync_drift_ms": round(float(av_sync_error_ms), 1),
            "is_sync_compliant": abs_drift <= 100.0,
            "requires_manual_review": needs_review,
        }


quality_metrics = QualityMetrics()
