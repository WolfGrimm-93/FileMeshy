"""Fase 5 (Ronda 12) -- secretos de system_configuration cifrados al guardar.

Antes: POST /admin/config/smtp, PUT /admin/config/turnstile, POST /create y PUT
/update/{key} guardaban el secreto EN CLARO aunque marcaban is_encrypted=True (y
el consumidor, al intentar descifrar un valor en claro, fallaba). Ahora se cifra
con el mismo Fernet de PUT /email y los consumidores descifran tolerando valores
legados en claro. Usa el mecanismo REAL de cifrado (sin mocks) y filas reales;
cada test guarda y restaura las filas que toca (BD compartida)."""
import asyncio
from types import SimpleNamespace

import pytest
from sqlalchemy import text

from app.core.security import (
    decrypt_secret_tolerant,
    encrypt_secret_if_needed,
    encrypt_sensitive_data,
    is_encrypted_token,
)

KEYS = ("SMTP_PASSWORD", "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "EMAIL_FROM",
        "email_smtp_password", "turnstile_secret_key", "pytest_dummy_password", "pytest_dummy_api_key")


@pytest.fixture
def restore_rows(db_session):
    """Guarda las filas de KEYS antes del test y las restaura al terminar."""
    def snap():
        return [dict(r._mapping) for r in db_session.execute(
            text("SELECT * FROM system_configuration WHERE config_key = ANY(:k)"), {"k": list(KEYS)})]

    db_session.rollback()
    before = snap()
    yield
    db_session.rollback()
    db_session.execute(text("DELETE FROM system_configuration WHERE config_key = ANY(:k)"), {"k": list(KEYS)})
    for row in before:
        cols = ", ".join(row)
        binds = ", ".join(f":{c}" for c in row)
        db_session.execute(text(f"INSERT INTO system_configuration ({cols}) VALUES ({binds})"), row)
    db_session.commit()


def _row(db_session, key):
    db_session.expire_all()
    return db_session.execute(
        text("SELECT value_string, is_encrypted FROM system_configuration WHERE config_key = :k"), {"k": key}
    ).first()


ADMIN = SimpleNamespace(email="pytest_admin@example.com")


# ---- helpers de cifrado ------------------------------------------------------

def test_encrypt_is_idempotent_and_decrypt_tolerates_plaintext():
    token = encrypt_secret_if_needed("clave-real")
    assert token != "clave-real" and is_encrypted_token(token)
    assert encrypt_secret_if_needed(token) == token  # sin doble cifrado
    assert decrypt_secret_tolerant(token) == "clave-real"
    assert decrypt_secret_tolerant("legado-en-claro") == "legado-en-claro"  # tolera claro
    assert decrypt_secret_tolerant(None) is None and decrypt_secret_tolerant("") == ""


# ---- caminos de escritura -----------------------------------------------------

def test_smtp_endpoint_encrypts_password(db_session, restore_rows):
    from app.configuration.router import SMTPConfigRequest, update_smtp_config

    update_smtp_config(
        SMTPConfigRequest(smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="pw-smtp-1", email_from="a@b.c"),
        db=db_session, current_user=ADMIN,
    )
    value, encrypted = _row(db_session, "SMTP_PASSWORD")
    assert value != "pw-smtp-1" and encrypted and decrypt_secret_tolerant(value) == "pw-smtp-1"
    # Re-guardar (fila ya existente) también cifra.
    update_smtp_config(
        SMTPConfigRequest(smtp_host="h", smtp_port=587, smtp_user="u", smtp_password="pw-smtp-2", email_from="a@b.c"),
        db=db_session, current_user=ADMIN,
    )
    value, _ = _row(db_session, "SMTP_PASSWORD")
    assert value != "pw-smtp-2" and decrypt_secret_tolerant(value) == "pw-smtp-2"


def test_turnstile_endpoint_encrypts_secret_and_consumer_reads_it(db_session, restore_rows):
    from app.auth.router import _turnstile_secret_from_config
    from app.configuration.repository import crud_system_configuration
    from app.configuration.router import update_turnstile_config

    asyncio.run(update_turnstile_config({"secret_key": "ts-secret-1"}, db=db_session, current_user=ADMIN))
    value, encrypted = _row(db_session, "turnstile_secret_key")
    assert value != "ts-secret-1" and encrypted
    cfg = crud_system_configuration.get_by_key(db_session, "turnstile_secret_key")
    assert _turnstile_secret_from_config(cfg) == "ts-secret-1"


def test_turnstile_consumer_accepts_legacy_plaintext_row(db_session, restore_rows):
    from app.auth.router import _turnstile_secret_from_config

    db_session.execute(text("DELETE FROM system_configuration WHERE config_key = 'turnstile_secret_key'"))
    db_session.commit()
    legacy = SimpleNamespace(value_string="secreto-legado-en-claro")
    assert _turnstile_secret_from_config(legacy) == "secreto-legado-en-claro"
    assert _turnstile_secret_from_config(None) == ""


def test_generic_create_and_update_encrypt(db_session, restore_rows):
    from app.configuration.router import SystemConfigCreateRequest, create_system_config, update_system_config

    create_system_config(
        SystemConfigCreateRequest(config_key="pytest_dummy_password", config_name="d", config_category="security",
                                  data_type="string", value_string="dummy-1", is_encrypted=False),
        db=db_session, current_user=ADMIN,
    )
    value, encrypted = _row(db_session, "pytest_dummy_password")
    assert value != "dummy-1" and encrypted and decrypt_secret_tolerant(value) == "dummy-1"

    update_system_config(
        "pytest_dummy_password",
        SystemConfigCreateRequest(config_key="pytest_dummy_password", config_name="d", config_category="security",
                                  data_type="string", value_string="dummy-2"),
        db=db_session, current_user=ADMIN,
    )
    value, _ = _row(db_session, "pytest_dummy_password")
    assert value != "dummy-2" and decrypt_secret_tolerant(value) == "dummy-2"

    # Reenviar la máscara no pisa el secreto.
    update_system_config(
        "pytest_dummy_password",
        SystemConfigCreateRequest(config_key="pytest_dummy_password", config_name="d", config_category="security",
                                  data_type="string", value_string="****"),
        db=db_session, current_user=ADMIN,
    )
    assert decrypt_secret_tolerant(_row(db_session, "pytest_dummy_password")[0]) == "dummy-2"


def test_legacy_plaintext_row_is_encrypted_when_resaved(db_session, restore_rows):
    from app.configuration.repository import crud_system_configuration

    db_session.execute(text("DELETE FROM system_configuration WHERE config_key = 'pytest_dummy_api_key'"))
    crud_system_configuration.create(db_session, config_key="pytest_dummy_api_key", config_name="k",
                                     config_category="security", data_type="string")
    db_session.execute(text("UPDATE system_configuration SET value_string='en-claro', is_encrypted=false "
                            "WHERE config_key='pytest_dummy_api_key'"))
    db_session.commit()
    crud_system_configuration.update(db_session, "pytest_dummy_api_key", value_string="nuevo")
    value, encrypted = _row(db_session, "pytest_dummy_api_key")
    assert encrypted and value != "nuevo" and decrypt_secret_tolerant(value) == "nuevo"


# ---- consumidor de emails ------------------------------------------------------

@pytest.mark.parametrize("stored_encrypted", [True, False])
@pytest.mark.parametrize("key", ["email_smtp_password", "SMTP_PASSWORD"])
def test_email_consumer_reads_encrypted_and_legacy_plaintext(db_session, restore_rows, stored_encrypted, key):
    from app.notifications.service import EmailConfigService

    db_session.execute(text("DELETE FROM system_configuration WHERE config_key IN ('email_smtp_password','SMTP_PASSWORD')"))
    db_session.commit()
    stored = encrypt_sensitive_data("pw-para-smtp") if stored_encrypted else "pw-para-smtp"
    db_session.execute(
        text("INSERT INTO system_configuration (id, config_key, config_name, config_category, data_type, "
             "value_string, is_encrypted, is_readonly, version) "
             "VALUES (gen_random_uuid(), :k, :k, 'email', 'string', :v, :e, false, 1)"),
        {"k": key, "v": stored, "e": stored_encrypted},
    )
    db_session.commit()
    assert EmailConfigService.get_smtp_config(db_session)["smtp_password"] == "pw-para-smtp"


# ---- ítems 2 y 3 --------------------------------------------------------------

def test_email_endpoint_ignores_masked_password(db_session, restore_rows):
    from app.configuration.router import EmailConfigUpdateRequest, update_email_config

    update_email_config(EmailConfigUpdateRequest(smtp_password="real-pw"), db=db_session, current_user=ADMIN)
    assert decrypt_secret_tolerant(_row(db_session, "email_smtp_password")[0]) == "real-pw"
    update_email_config(EmailConfigUpdateRequest(smtp_password="****"), db=db_session, current_user=ADMIN)
    assert decrypt_secret_tolerant(_row(db_session, "email_smtp_password")[0]) == "real-pw"


def test_config_value_masks_only_when_a_value_exists():
    from app.configuration.router import _config_value

    def cfg(**kw):
        base = dict(config_key="smtp_password", is_encrypted=True, value_string=None, value_number=None,
                    value_boolean=None, value_json=None)
        return SimpleNamespace(**{**base, **kw})

    assert _config_value(cfg()) is None            # secreto sin valor: honesto
    assert _config_value(cfg(value_string="")) is None
    assert _config_value(cfg(value_string="x")) == "****"


# ---- ítem 4: sanitizado de valores del cliente en logs ---------------------------

def test_sanitize_for_log_strips_control_chars_and_truncates():
    from app.core.logging_config import sanitize_for_log

    assert sanitize_for_log("a\r\nFAKE | LINE\x00b") == "a  FAKE | LINE b"
    out = sanitize_for_log("X" * 1000)
    assert len(out) == 203 and out.endswith("...")
    assert sanitize_for_log(None) == ""


def test_audit_service_log_line_is_sanitized():
    import logging

    from app.auth.service import AuditService
    from app.core.logging_config import audit_logger

    records = []

    class _H(logging.Handler):
        def emit(self, record):
            records.append(record.getMessage())

    handler = _H()
    audit_logger.addHandler(handler)
    try:
        AuditService.log_password_reset_request(
            "a@example.com", "10.0.0.1", "Mozilla\r\n2026-01-01 | FAKE_EVENT | " + "Z" * 900, True
        )
    finally:
        audit_logger.removeHandler(handler)
    assert records and "\n" not in records[0] and "\r" not in records[0]
    assert len(records[0]) < 500


# ---- Ronda 12d --------------------------------------------------------------------

def test_undecryptable_fernet_looking_value_returns_none_and_logs_error_without_value(caplog):
    import logging

    bogus = "gAAAAABq" + "x" * 80  # forma de token Fernet, pero de otra SECRET_KEY
    with caplog.at_level(logging.ERROR, logger="filemeshy.security"):
        assert decrypt_secret_tolerant(bogus) is None
    assert "SECRET_KEY" in caplog.text and bogus not in caplog.text
    assert decrypt_secret_tolerant("clave-en-claro-legada") == "clave-en-claro-legada"  # legado en claro: intacto


def test_masked_marker_never_overwrites_mask_only_keys(db_session):
    """`*_token` solo se enmascara (no se cifra): reenviar "****" tampoco debe pisar el valor."""
    from app.configuration.repository import crud_system_configuration

    db_session.execute(text("DELETE FROM system_configuration WHERE config_key = 'pytest_api_token'"))
    db_session.commit()
    try:
        crud_system_configuration.create(db_session, config_key="pytest_api_token", config_name="t",
                                         config_category="security", data_type="string", value_string="abc123")
        assert _row(db_session, "pytest_api_token")[0] == "abc123"  # token: solo enmascarado, no cifrado
        crud_system_configuration.update(db_session, "pytest_api_token", value_string="****")
        assert _row(db_session, "pytest_api_token")[0] == "abc123"
        crud_system_configuration.update(db_session, "pytest_api_token", value_string="nuevo")
        assert _row(db_session, "pytest_api_token")[0] == "nuevo"
    finally:
        db_session.execute(text("DELETE FROM system_configuration WHERE config_key = 'pytest_api_token'"))
        db_session.commit()
