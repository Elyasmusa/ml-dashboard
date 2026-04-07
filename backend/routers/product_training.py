from fastapi import APIRouter, BackgroundTasks, Depends

from schemas.training import TrainingRequest, ProductTrainingResponse, TrainingStatus
from services.product_training_service import ProductTrainingService

router = APIRouter(prefix="/training/products", tags=["product-training"])


def get_product_training_service() -> ProductTrainingService:
    return ProductTrainingService()


@router.post("/", response_model=ProductTrainingResponse)
async def start_product_training(
    request: TrainingRequest,
    background_tasks: BackgroundTasks,
    service: ProductTrainingService = Depends(get_product_training_service),
):
    job_id = service.start(request, background_tasks)
    return ProductTrainingResponse(job_id=job_id, status=TrainingStatus.STARTED)


@router.get("/{job_id}", response_model=ProductTrainingResponse)
async def get_product_training_status(
    job_id: str,
    service: ProductTrainingService = Depends(get_product_training_service),
):
    return service.get_status(job_id)
