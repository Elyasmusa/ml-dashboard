from enum import Enum
from pydantic import BaseModel, ConfigDict


class TrainingStatus(str, Enum):
    STARTED = "started"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class TrainingRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    epochs: int = 10
    batch_size: int = 32
    dataset_name: str | None = None


class TrainingResponse(BaseModel):
    job_id: str
    status: TrainingStatus
    epoch: int | None = None
    loss: float | None = None
    accuracy: float | None = None
