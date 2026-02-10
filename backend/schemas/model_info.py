from datetime import datetime
from pydantic import BaseModel


class ModelInfo(BaseModel):
    name: str
    description: str = ""
    input_shape: list[int] | None = None
    output_shape: list[int] | None = None
    created_at: datetime | None = None
    file_path: str | None = None
