from fastapi import APIRouter, Depends

from schemas.prediction import PredictionRequest, PredictionResponse
from services.inference_service import InferenceService

router = APIRouter(prefix="/predictions", tags=["predictions"])


def get_inference_service() -> InferenceService:
    return InferenceService()


@router.post("/", response_model=PredictionResponse)
async def create_prediction(
    request: PredictionRequest,
    service: InferenceService = Depends(get_inference_service),
):
    result = service.predict(request.model_name, request.input_data)
    return PredictionResponse(
        model_name=request.model_name,
        predictions=result,
    )
