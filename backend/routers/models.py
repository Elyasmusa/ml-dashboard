from fastapi import APIRouter, Depends

from schemas.model_info import ModelInfo
from services.model_registry import ModelRegistry

router = APIRouter(prefix="/models", tags=["models"])


def get_registry() -> ModelRegistry:
    return ModelRegistry()


@router.get("/", response_model=list[ModelInfo])
async def list_models(
    registry: ModelRegistry = Depends(get_registry),
):
    return registry.list_models()


@router.get("/{model_name}", response_model=ModelInfo)
async def get_model_info(
    model_name: str,
    registry: ModelRegistry = Depends(get_registry),
):
    return registry.get_model(model_name)
