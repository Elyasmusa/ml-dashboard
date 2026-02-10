import uuid
from fastapi import BackgroundTasks
from schemas.training import TrainingRequest, TrainingResponse, TrainingStatus


class TrainingService:
    _jobs: dict[str, TrainingResponse] = {}

    def start(self, request: TrainingRequest, background_tasks: BackgroundTasks) -> str:
        job_id = str(uuid.uuid4())
        self._jobs[job_id] = TrainingResponse(
            job_id=job_id, status=TrainingStatus.STARTED
        )
        background_tasks.add_task(self._run_training, job_id, request)
        return job_id

    def get_status(self, job_id: str) -> TrainingResponse:
        if job_id not in self._jobs:
            raise KeyError(f"Job '{job_id}' not found")
        return self._jobs[job_id]

    def _run_training(self, job_id: str, request: TrainingRequest) -> None:
        self._jobs[job_id].status = TrainingStatus.RUNNING
        try:
            # Placeholder: import and build the model, fit on data
            self._jobs[job_id].status = TrainingStatus.COMPLETED
            self._jobs[job_id].epoch = request.epochs
        except Exception:
            self._jobs[job_id].status = TrainingStatus.FAILED
