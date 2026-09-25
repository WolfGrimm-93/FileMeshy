"""Ronda 10 -- regresión del bug de SUPER_ADMIN con dominio `.local` bloqueado
para login (ver scripts/create_super_admin.py::_validate_email_or_raise).

Contexto del bug: `create_super_admin()` inserta con SQL crudo, sin pasar
por ningún schema Pydantic -- podía crear una cuenta con un email que el
LOGIN (`app/users/schemas.py::LoginRequest`, que sí exige `EmailStr`)
rechazaría para siempre, dejando un SUPER_ADMIN existente pero inutilizable.

Investigación confirmada en vivo (ver docstring de `_validate_email_or_raise`
para el detalle completo): NO es un tema de `check_deliverability` (ya está
apagado por default en pydantic 2.5.2, hardcodeado, nunca hace DNS real acá).
El rechazo real es el chequeo INCONDICIONAL de `email_validator` contra
`SPECIAL_USE_DOMAIN_NAMES` (confirmado en vivo: `arpa`, `invalid`, `local`,
`localhost`, `onion`, `test` -- OJO, ".example" NO está en esa lista pese a
estar "reservado" por RFC 2606, esa RFC reserva los dominios puntuales
example.com/.net/.org, no el sufijo ".example" en general) -- corre siempre,
sin gate posible. Por eso el fix elegido es (a) del prompt de la ronda:
fallar temprano en la CREACIÓN, no relajar nada del lado del login (fuera de
alcance de este script, y tampoco sería posible con `EmailStr` tal como lo
expone pydantic).
"""
from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError
from sqlalchemy import text

from scripts.create_super_admin import SuperAdminCreationError, create_super_admin
from app.users.schemas import LoginRequest

from conftest import unique_email


def _delete_user(db_session, email: str) -> None:
    db_session.execute(text("DELETE FROM users WHERE email = :email"), {"email": email})
    db_session.commit()


def test_create_super_admin_rejects_local_domain_before_inserting(db_session):
    """El bug reportado: `admin@empresa.local` -- válido para el script viejo
    (SQL crudo, sin validar), pero el login lo rechaza siempre. El fix debe
    fallar ACÁ, sin dejar ninguna fila en `users`."""
    email = f"pytest_admin_{uuid.uuid4().hex[:12]}@filemeshy.local"

    with pytest.raises(SuperAdminCreationError, match="Email inválido"):
        create_super_admin(email, "SomeStrongPass123!")

    # No debe haber quedado un usuario a medio crear con ese email.
    row = db_session.execute(text("SELECT id FROM users WHERE email = :email"), {"email": email}).first()
    assert row is None, "create_super_admin() no debería insertar nada si el email es inválido para login"

    # Confirma que el motivo real es el mismo que rechazaría el login (no una
    # reimplementación separada que podría desincronizarse) -- LoginRequest
    # usa EmailStr, que debe rechazar este mismo email por el mismo motivo.
    with pytest.raises(ValidationError):
        LoginRequest(email=email, password="cualquier-cosa")


@pytest.mark.parametrize(
    "bad_domain",
    ["admin@x.test", "admin@x.invalid", "admin@x.localhost"],
)
def test_create_super_admin_rejects_other_reserved_domains(db_session, bad_domain):
    """No es un caso especial de `.local` -- CUALQUIER dominio de la lista
    real de `email_validator.SPECIAL_USE_DOMAIN_NAMES` (confirmado en vivo:
    `arpa`, `invalid`, `local`, `localhost`, `onion`, `test` -- OJO,
    `.example` NO está en esa lista pese a estar reservado por RFC 2606
    para dominios específicos como example.com/.net/.org, así que
    "x.example" SÍ pasa la validación) se rechaza igual, mismo mecanismo."""
    with pytest.raises(SuperAdminCreationError):
        create_super_admin(bad_domain, "SomeStrongPass123!")

    row = db_session.execute(text("SELECT id FROM users WHERE email = :email"), {"email": bad_domain}).first()
    assert row is None


def test_create_super_admin_accepts_real_domain_and_login_would_too(db_session):
    """Regresión del camino feliz -- el fix no debe romper la creación
    normal de un super admin con un dominio real."""
    email = unique_email()  # @example.com -- NO es un dominio reservado
    try:
        resultado = create_super_admin(email, "SomeStrongPass123!", first_name="Pytest", last_name="SuperAdmin")
        assert resultado["created"] is True
        assert resultado["email"] == email

        row = db_session.execute(
            text("SELECT is_superuser, is_active FROM users WHERE email = :email"), {"email": email}
        ).first()
        assert row is not None
        assert row[0] is True  # is_superuser
        assert row[1] is True  # is_active

        # El mismo email tiene que pasar la validación real del login.
        LoginRequest(email=email, password="cualquier-cosa")
    finally:
        _delete_user(db_session, email)


def test_create_super_admin_is_idempotent_for_existing_email(db_session):
    """`created=False` si el email ya existe -- no debe re-crear ni re-validar
    de forma distinta (ver docstring de create_super_admin)."""
    email = unique_email()
    try:
        primero = create_super_admin(email, "SomeStrongPass123!")
        assert primero["created"] is True

        segundo = create_super_admin(email, "OtraPassword456!")
        assert segundo["created"] is False
        assert segundo["user_id"] == primero["user_id"]
    finally:
        _delete_user(db_session, email)
