from pydantic import BaseModel, ConfigDict


class PredictionRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    input_data: list[list[float]]


class PredictionResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str
    predictions: list[float]
