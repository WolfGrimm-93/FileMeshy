from pydantic import BaseModel, Field
from typing import Optional, Any, Union


class Message(BaseModel):
    """Schema genérico para mensajes."""
    message: str


class ErrorResponse(BaseModel):
    """Schema para respuestas de error."""
    status: Union[int, str] = Field(description="HTTP status code o status string")
    message: str
    detail: Optional[Any] = None


class SuccessResponse(BaseModel):
    """Schema para respuestas exitosas."""
    status: Union[int, str] = Field(default="success", description="Status: 'success' o HTTP code")
    message: str
    data: Optional[Any] = None
    cached: Optional[bool] = Field(default=None, description="Indica si la respuesta viene de cache Redis")
