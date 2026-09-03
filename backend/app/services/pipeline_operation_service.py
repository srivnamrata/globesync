"""Helpers for durable progress of upstream pipeline operations."""

from typing import Optional
from sqlalchemy.orm import Session

from app.models.pipeline_operation import PipelineOperation


def checkpoint_operation(
    db: Session,
    operation_id: Optional[str],
    *,
    status: str,
    stage: str,
    progress_percent: int,
    message: str,
    successful_stage: Optional[str] = None,
    error_message: Optional[str] = None,
) -> None:
    if not operation_id:
        return
    operation = db.get(PipelineOperation, operation_id)
    if operation is None:
        return
    operation.status = status
    operation.current_stage = stage
    operation.progress_percent = max(0, min(100, progress_percent))
    operation.message = message
    operation.error_message = error_message
    if successful_stage is not None:
        operation.last_successful_stage = successful_stage
    db.commit()
