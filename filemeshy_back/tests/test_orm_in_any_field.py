"""Ronda 12b -- objetos ORM dentro de un campo `Any` de un response_model.

Regresión de FastAPI 0.135: la respuesta se serializa con Pydantic directo y un
objeto ORM en `SuccessResponse.data: Any` reventaba con PydanticSerializationError
(500), p. ej. PUT /config/preferences/my-preferences. `SuccessResponse` ahora
serializa `data` con jsonable_encoder(sqlalchemy_safe=True), como FastAPI 0.115."""
import datetime as dt
import decimal
import enum
import uuid

from fastapi import FastAPI

from app.shared.schemas.common import ErrorResponse, SuccessResponse

from conftest import auth_headers, login_user, register_user


def _orm_row():
    from app.configuration.models import UserPreferences

    return UserPreferences(id=uuid.uuid4(), user_id=uuid.uuid4(), theme="dark", language="es-DO",
                           rows_per_page=25, created_at=dt.datetime(2026, 1, 2, 3, 4, 5, tzinfo=dt.timezone.utc))


def test_success_response_serializes_orm_object_in_data():
    import app.worker.celery_app  # noqa: F401  (registra los mappers)

    row = _orm_row()
    payload = SuccessResponse(message="ok", data=row).model_dump(mode="json")
    assert payload["data"]["theme"] == "dark" and payload["data"]["rows_per_page"] == 25
    assert payload["data"]["id"] == str(row.id)
    assert "_sa_instance_state" not in payload["data"]


def test_success_response_through_real_fastapi_route_with_orm():
    """Un endpoint mínimo real (response_model=SuccessResponse) que devuelve ORM."""
    import app.worker.celery_app  # noqa: F401

    app = FastAPI()
    row = _orm_row()

    @app.get("/orm", response_model=SuccessResponse)
    def orm():
        return SuccessResponse(message="ok", data=row)

    @app.get("/orm-dict", response_model=SuccessResponse)
    def orm_dict():
        return {"message": "ok", "data": {"items": [row], "when": dt.datetime(2026, 1, 1)}}

    from starlette.testclient import TestClient

    with TestClient(app) as c:
        r = c.get("/orm")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["theme"] == "dark"
        r = c.get("/orm-dict")
        assert r.status_code == 200, r.text
        assert r.json()["data"]["items"][0]["language"] == "es-DO"


def test_plain_values_serialize_like_before():
    class Color(enum.Enum):
        RED = "red"

    data = {
        "n": 1, "s": "x", "l": [1, 2], "none": None, "u": uuid.UUID(int=5), "dec": decimal.Decimal("1.5"),
        "color": Color.RED, "when": dt.datetime(2026, 1, 2, 3, 4, 5), "day": dt.date(2026, 1, 2),
    }
    out = SuccessResponse(message="ok", data=data).model_dump(mode="json")["data"]
    assert out["n"] == 1 and out["l"] == [1, 2] and out["none"] is None
    assert out["u"] == str(uuid.UUID(int=5)) and out["dec"] == 1.5 and out["color"] == "red"
    assert out["when"] == "2026-01-02T03:04:05Z" and out["day"] == "2026-01-02"  # datetime -> ISO UTC con Z
    assert SuccessResponse(message="ok").model_dump(mode="json")["data"] is None


def test_error_response_detail_serializes_orm():
    import app.worker.celery_app  # noqa: F401

    out = ErrorResponse(status=400, message="m", detail={"row": _orm_row()}).model_dump(mode="json")
    assert out["detail"]["row"]["theme"] == "dark"


def test_my_preferences_put_returns_200_and_get_reflects_it(client):
    creds = register_user(client)
    token = login_user(client, creds["email"], creds["password"]).json()["data"]["access_token"]
    put = client.put("/config/preferences/my-preferences", headers=auth_headers(token),
                     json={"theme": "dark", "language": "en-US", "rows_per_page": 50, "email_notifications": False})
    assert put.status_code == 200, put.text
    body = put.json()
    assert body["message"] == "Preferencias actualizadas"
    assert body["data"]["theme"] == "dark" and body["data"]["rows_per_page"] == 50
    got = client.get("/config/preferences/my-preferences", headers=auth_headers(token))
    assert got.status_code == 200
    assert got.json()["theme"] == "dark" and got.json()["language"] == "en-US"
    assert got.json()["rows_per_page"] == 50 and got.json()["email_notifications"] is False
