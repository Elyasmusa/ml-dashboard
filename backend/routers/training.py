from fastapi import APIRouter, BackgroundTasks, Depends

from schemas.training import TrainingRequest, TrainingResponse, TrainingStatus
from services.training_service import TrainingService

router = APIRouter(prefix="/training", tags=["training"])


def get_training_service() -> TrainingService:
    return TrainingService()


@router.post("/", response_model=TrainingResponse)
async def start_training(
    request: TrainingRequest,
    background_tasks: BackgroundTasks,
    service: TrainingService = Depends(get_training_service),
):
    job_id = service.start(request, background_tasks)
    return TrainingResponse(job_id=job_id, status=TrainingStatus.STARTED)


@router.get("/{job_id}", response_model=TrainingResponse)
async def get_training_status(
    job_id: str,
    service: TrainingService = Depends(get_training_service),
):
    return service.get_status(job_id)
