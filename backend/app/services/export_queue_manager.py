import logging
import os
from typing import Dict, List
import redis
from app.core.config import settings

logger = logging.getLogger("export_queue_manager")


class ExportQueueManager:
    """Manages active export queues, cancellations, prioritizations, and temp file cleanups."""

    def __init__(self):
        self.redis = redis.Redis.from_url(settings.REDIS_URL)
        self.active_exports_key = "active_export_jobs_list"

    def register_job(self, job_id: str):
        """Registers a job to the active exports list."""
        try:
            self.redis.rpush(self.active_exports_key, job_id)
        except Exception as e:
            logger.warning(f"Failed to register export job in Redis: {e}")

    def deregister_job(self, job_id: str):
        """Deregisters a job from the active exports list."""
        try:
            self.redis.lrem(self.active_exports_key, 0, job_id)
        except Exception as e:
            logger.warning(f"Failed to remove export job from Redis: {e}")

    def cancel_job(self, job_id: str):
        """Cancels a running export job (signals Celery or marks canceled state)."""
        try:
            # Set cancel flag in Redis
            self.redis.set(f"cancel_flag_job:{job_id}", "true", ex=3600)
            self.deregister_job(job_id)
        except Exception as e:
            logger.warning(f"Failed to cancel export job: {e}")

    def is_cancelled(self, job_id: str) -> bool:
        """Checks if a cancel signal has been set for this job."""
        try:
            return self.redis.exists(f"cancel_flag_job:{job_id}") > 0
        except Exception:
            return False

    @staticmethod
    def cleanup_temporary_files(paths: List[str]):
        """Safely cleans up temporary video slices, thumbnails, or subtitle SRTs."""
        for p in paths:
            if p and os.path.exists(p):
                try:
                    os.remove(p)
                    logger.info(f"Cleaned up temporary export scratch file: {p}")
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {p}: {e}")


export_queue_manager = ExportQueueManager()
