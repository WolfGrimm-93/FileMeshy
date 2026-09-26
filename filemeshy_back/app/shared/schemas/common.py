from datetime import datetime

from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, Any, Union

from app.shared.utils.datetime_iso import to_utc_iso


def _to_jsonable(value: Any) -> Any:
    """Serializa un valor `Any` como lo hacía FastAPI <= 0.115 (jsonable_encoder
    sobre toda la respuesta): objetos ORM de SQLAlchemy, modelos Pydantic, fechas,
    UUID, Decimal y enums salen como JSON. Desde FastAPI 0.135 la respuesta se
    serializa con Pydantic directo y un objeto ORM dentro de un campo `Any`
    reventaba con PydanticSerializationError (500). Único lugar donde se
    restaura ese comportamiento para los schemas genéricos de respuesta."""
    # datetime -> ISO 8601 UTC con `Z` (mismo formato que to_utc_iso y que los GET de fechas)
    return jsonable_encoder(value, sqlalchemy_safe=True, custom_encoder={datetime: to_utc_iso})


class Message(BaseModel):
    """Schema genérico para mensajes."""
    message: str


class ErrorResponse(BaseModel):
    """Schema para respuestas de error."""
    status: Union[int, str] = Field(description="HTTP status code o status string")
    message: str
    detail: Optional[Any] = None

    @field_serializer("detail")
    def _serialize_detail(self, value: Any) -> Any:
        return _to_jsonable(value)


class SuccessResponse(BaseModel):
    """Schema para respuestas exitosas."""
    status: Union[int, str] = Field(default="success", description="Status: 'success' o HTTP code")
    message: str
    data: Optional[Any] = None
    cached: Optional[bool] = Field(default=None, description="Indica si la respuesta viene de cache Redis")

    @field_serializer("data")
    def _serialize_data(self, value: Any) -> Any:
        return _to_jsonable(value)
