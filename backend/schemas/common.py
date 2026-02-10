from pydantic import BaseModel


class ErrorResponse(BaseModel):
    detail: str
    status_code: int


class PaginatedResponse(BaseModel):
    items: list
    total: int
    page: int = 1
    page_size: int = 20
