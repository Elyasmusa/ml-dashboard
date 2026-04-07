"""Shared job-management infrastructure for ML training services.

Both TrainingService (order prediction) and ProductTrainingService (product
prediction) follow the same lifecycle:
  start()      → create job record, schedule background task, return job_id
  get_status() → look up job record by id
  _run_training() → the variant training loop (implemented by each subclass)
  incremental_train() → fine-tune on new data (implemented by each subclass)

BaseTrainingService owns start/get_status/eviction so each subclass only
implements the parts that differ.
"""

from __future__ import annotations

import logging
import uuid
from abc import ABC, abstractmethod

import pandas as pd
from fastapi import BackgroundTasks

from schemas.training import TrainingRequest, TrainingStatus

logger = logging.getLogger(__name__)

_MAX_JOBS = 20  # Maximum job records kept in memory across both service types


class BaseTrainingService(ABC):
    """Abstract base for order and product training services.

    Subclasses must implement:
    - _create_job(job_id) → the initial job-response Pydantic object
    - _run_training(job_id, request) → full variant training loop
    - incremental_train(variant, df) → fine-tune on new order data
    """

    def __init__(self) -> None:
        # Instance-level dict so order and product jobs never share state.
        self._jobs: dict = {}

    # ── Public API ─────────────────────────────────────────────────

    def start(self, request: TrainingRequest, background_tasks: BackgroundTasks) -> str:
        """Create a job, schedule it as a background task, and return its id."""
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = self._create_job(job_id)
        self._evict_old_jobs()
        background_tasks.add_task(self._run_training, job_id, request)
        return job_id

    def get_status(self, job_id: str):
        """Return the job record, raising KeyError if not found."""
        if job_id not in self._jobs:
            raise KeyError(f"Job '{job_id}' not found")
        return self._jobs[job_id]

    # ── Internal helpers ────────────────────────────────────────────

    def _evict_old_jobs(self) -> None:
        """Evict the oldest entries once the in-memory cap is exceeded."""
        if len(self._jobs) > _MAX_JOBS:
            for oldest_key in list(self._jobs.keys())[:-_MAX_JOBS]:
                del self._jobs[oldest_key]

    # ── Abstract interface ──────────────────────────────────────────

    @abstractmethod
    def _create_job(self, job_id: str):
        """Return a new job-response Pydantic object with STARTED status."""
        ...

    @abstractmethod
    def _run_training(self, job_id: str, request: TrainingRequest) -> None:
        """Execute the full multi-variant training loop.

        Must update self._jobs[job_id] in-place and set status to COMPLETED
        or FAILED on exit.
        """
        ...

    @abstractmethod
    def incremental_train(self, variant: str, df: pd.DataFrame) -> None:
        """Fine-tune the trained model for *variant* on new order data *df*."""
        ...
