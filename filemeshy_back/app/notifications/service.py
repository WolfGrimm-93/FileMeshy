"""Servicio de notificaciones por email: configuración (lee de la BD) + envío SMTP.

Fusiona, durante la migración a monolito modular:
- app/services/email_config.py (EmailConfigService -- lee system_configuration)
- app/services/email_service.py (EmailService -- envío vía SMTP)
"""
from typing import Optional
from sqlalchemy.orm import Session
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import logging

from app.core.config import settings

logger = logging.getLogger(__name__)


class EmailConfigService:
    """
    Servicio para manejar configuración de email desde la DB.
    Lee las configuraciones guardadas en system_configuration table.
    """

    @staticmethod
    def get_smtp_config(db: Session) -> dict:
        """
        Obtener configuración SMTP desde la DB

        Primero intenta usar la nueva estructura (email_smtp_*),
        sino usa la antigua (SMTP_*)

        Returns:
            dict con las claves:
            {
                'smtp_host': str,
                'smtp_port': int,
                'smtp_user': str,
                'smtp_password': str,
                'email_from': str
            }
        """
        from app.core.security import decrypt_sensitive_data
        from app.configuration import service as configuration_service

        config = {
            'smtp_host': None,
            'smtp_port': None,
            'smtp_user': None,
            'smtp_password': None,
            'email_from': None
        }

        # Intentar obtener desde la nueva estructura (email_smtp_*)
        smtp_host_config = configuration_service.get_system_config(db, 'email_smtp_host')
        if smtp_host_config:
            config['smtp_host'] = smtp_host_config.value_string
        else:
            # Fallback a estructura antigua
            smtp_host_config = configuration_service.get_system_config(db, 'SMTP_HOST')
            if smtp_host_config:
                config['smtp_host'] = smtp_host_config.value_string

        # Puerto SMTP (inseguro por defecto 587)
        smtp_port_config = configuration_service.get_system_config(db, 'email_smtp_insecure_port')
        if smtp_port_config:
            config['smtp_port'] = int(smtp_port_config.value_number or 587)
        else:
            smtp_port_config = configuration_service.get_system_config(db, 'SMTP_PORT')
            if smtp_port_config:
                config['smtp_port'] = int(smtp_port_config.value_number or 587)

        # Usuario SMTP
        smtp_user_config = configuration_service.get_system_config(db, 'email_smtp_username')
        if smtp_user_config:
            config['smtp_user'] = smtp_user_config.value_string
        else:
            smtp_user_config = configuration_service.get_system_config(db, 'SMTP_USER')
            if smtp_user_config:
                config['smtp_user'] = smtp_user_config.value_string

        # Contraseña SMTP (desencriptar si está encriptada)
        smtp_password_config = configuration_service.get_system_config(db, 'email_smtp_password')
        if smtp_password_config:
            try:
                # Intentar desencriptar
                if smtp_password_config.is_encrypted:
                    config['smtp_password'] = decrypt_sensitive_data(smtp_password_config.value_string)
                else:
                    config['smtp_password'] = smtp_password_config.value_string
            except Exception as e:
                print(f"Error desencriptando contraseña SMTP: {e}")
                config['smtp_password'] = None
        else:
            smtp_password_config = configuration_service.get_system_config(db, 'SMTP_PASSWORD')
            if smtp_password_config:
                try:
                    if smtp_password_config.is_encrypted:
                        config['smtp_password'] = decrypt_sensitive_data(smtp_password_config.value_string)
                    else:
                        config['smtp_password'] = smtp_password_config.value_string
                except Exception as e:
                    print(f"Error desencriptando contraseña SMTP: {e}")
                    config['smtp_password'] = None

        # Email from (display email)
        email_from_config = configuration_service.get_system_config(db, 'email_account_email')
        if email_from_config:
            config['email_from'] = email_from_config.value_string
        else:
            email_from_config = configuration_service.get_system_config(db, 'EMAIL_FROM')
            if email_from_config:
                config['email_from'] = email_from_config.value_string

        return config

    @staticmethod
    def get_imap_config(db: Session) -> dict:
        """
        Obtener configuración IMAP desde la DB

        Returns:
            dict con toda la configuración IMAP/Inbound
        """
        from app.configuration import service as configuration_service

        config = {
            'account_email': None,
            'account_username': None,
            'domain_name': None,
            'imap_hostname': None,
            'imap_mail_hostname': None,
            'imap_insecure_port': None,
            'imap_secure_port': None,
            'service_type': None,
            'activesync_available': False,
            'activesync_port': None,
            'support_plaintext_auth': None,
            'mail_archive': False
        }

        # Mapeo de config_keys a campos del dict
        key_mapping = {
            'email_account_email': 'account_email',
            'email_account_username': 'account_username',
            'email_domain_name': 'domain_name',
            'email_imap_hostname': 'imap_hostname',
            'email_imap_mail_hostname': 'imap_mail_hostname',
            'email_imap_insecure_port': 'imap_insecure_port',
            'email_imap_secure_port': 'imap_secure_port',
            'email_service_type': 'service_type',
            'email_activesync_available': 'activesync_available',
            'email_activesync_port': 'activesync_port',
            'email_support_plaintext_auth': 'support_plaintext_auth',
            'email_mail_archive': 'mail_archive'
        }

        for config_key, field_name in key_mapping.items():
            db_config = configuration_service.get_system_config(db, config_key)
            if db_config:
                value = db_config.value_string or db_config.value_number or db_config.value_boolean
                config[field_name] = value

        return config

    @staticmethod
    def get_email_method(db: Session) -> str:
        """
        Retorna el proveedor de email configurado. Hoy solo existe 'smtp' --
        Por defecto retorna 'smtp' si no hay configuración guardada.
        """
        from app.configuration import service as configuration_service

        config = configuration_service.get_system_config(db, 'email_email_method')
        if config and config.value_string == 'smtp':
            return config.value_string
        return 'smtp'

    @staticmethod
    def is_smtp_configured(db: Session) -> bool:
        """
        Verificar si SMTP está completamente configurado

        Returns:
            True si todas las configuraciones están presentes
        """
        config = EmailConfigService.get_smtp_config(db)
        return all([
            config['smtp_host'],
            config['smtp_port'],
            config['smtp_user'],
            config['smtp_password'],
            config['email_from']
        ])

    @staticmethod
    def setup_default_configs(db: Session):
        """
        Crear configuraciones por defecto si no existen
        Esto se ejecuta en la inicialización de la app
        """
        from app.configuration import service as configuration_service

        default_configs = [
            {
                'config_key': 'SMTP_HOST',
                'config_name': 'SMTP Host',
                'config_category': 'notifications',
                'data_type': 'string',
                'description': 'Servidor SMTP (ej: smtp.gmail.com)',
                'is_encrypted': False
            },
            {
                'config_key': 'SMTP_PORT',
                'config_name': 'SMTP Port',
                'config_category': 'notifications',
                'data_type': 'number',
                'value_number': 587,
                'description': 'Puerto SMTP (generalmente 587 para TLS)',
                'is_encrypted': False
            },
            {
                'config_key': 'SMTP_USER',
                'config_name': 'SMTP User',
                'config_category': 'notifications',
                'data_type': 'string',
                'description': 'Usuario/email para autenticación SMTP',
                'is_encrypted': True
            },
            {
                'config_key': 'SMTP_PASSWORD',
                'config_name': 'SMTP Password',
                'config_category': 'notifications',
                'data_type': 'string',
                'description': 'Contraseña para autenticación SMTP',
                'is_encrypted': True
            },
            {
                'config_key': 'EMAIL_FROM',
                'config_name': 'Email From',
                'config_category': 'notifications',
                'data_type': 'string',
                'value_string': 'noreply@filemeshy.dev',
                'description': 'Email de origen para todos los emails',
                'is_encrypted': False
            }
        ]

        for config in default_configs:
            existing = configuration_service.get_system_config(db, config['config_key'])
            if not existing:
                configuration_service.create_system_config(
                    db,
                    config_key=config['config_key'],
                    config_name=config['config_name'],
                    config_category=config['config_category'],
                    data_type=config['data_type'],
                    value_string=config.get('value_string'),
                    value_number=config.get('value_number'),
                    description=config.get('description'),
                    is_encrypted=config.get('is_encrypted', False)
                )


# Instancia global
email_config_service = EmailConfigService()


class EmailService:
    """
    Servicio para envío de emails vía SMTP.

    Antes soportaba un segundo proveedor externo seleccionable por
    'email_email_method' en system_configuration -- se quitó junto con el
    resto de esa integración. Ahora SMTP es el único proveedor.
    """

    @staticmethod
    def _send_via_smtp(
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        smtp_config: dict = None,
        db: Session = None,
    ) -> bool:
        """Envía email directamente vía SMTP. Carga la config desde BD si no se pasa smtp_config."""
        if smtp_config is None:
            if db:
                try:
                    smtp_config = email_config_service.get_smtp_config(db)
                except Exception:
                    pass
            if smtp_config is None:
                smtp_config = {
                    'smtp_host':     settings.SMTP_HOST,
                    'smtp_port':     settings.SMTP_PORT,
                    'smtp_user':     settings.SMTP_USER,
                    'smtp_password': settings.SMTP_PASSWORD,
                    'email_from':    settings.EMAIL_FROM,
                }

        if not all([
            smtp_config.get('smtp_host'),
            smtp_config.get('smtp_port'),
            smtp_config.get('smtp_user'),
            smtp_config.get('smtp_password'),
            smtp_config.get('email_from'),
        ]):
            logger.warning("Configuración SMTP incompleta. Email no enviado a %s", to_email)
            return False

        try:
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"]    = smtp_config['email_from']
            message["To"]      = to_email
            if text_content:
                message.attach(MIMEText(text_content, "plain"))
            message.attach(MIMEText(html_content, "html"))

            port = int(smtp_config['smtp_port'])
            if port == 465:
                with smtplib.SMTP_SSL(smtp_config['smtp_host'], port) as server:
                    server.login(smtp_config['smtp_user'], smtp_config['smtp_password'])
                    server.send_message(message)
            else:
                with smtplib.SMTP(smtp_config['smtp_host'], port) as server:
                    server.starttls()
                    server.login(smtp_config['smtp_user'], smtp_config['smtp_password'])
                    server.send_message(message)

            logger.info("Email enviado vía SMTP → %s", to_email)
            return True
        except Exception as e:
            logger.error("SMTP error enviando a %s: %s", to_email, str(e))
            return False

    @staticmethod
    def _send_email(
        to_email: str,
        subject: str,
        html_content: str,
        text_content: Optional[str] = None,
        smtp_config: dict = None,
        db: Session = None,
    ) -> bool:
        """
        Punto de entrada principal para envío de email. Único proveedor: SMTP.
        """
        return EmailService._send_via_smtp(
            to_email=to_email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            smtp_config=smtp_config,
            db=db,
        )

    @staticmethod
    def send_password_reset_code(
        email: str,
        code: str,
        business_name: str = "FileMeshy",
        db: Session = None
    ) -> bool:
        """
        Envía el código de restablecimiento de contraseña.

        Args:
            email: Email del destinatario
            code: Código de 6 dígitos
            business_name: Nombre del negocio
            db: Session de BD para obtener configuración SMTP (opcional)

        Returns:
            True si se envió correctamente
        """
        # Obtener configuración SMTP de la DB si se proporciona
        smtp_config = None
        if db:
            try:
                smtp_config = email_config_service.get_smtp_config(db)
            except Exception as e:
                print(f"⚠️  No se pudo obtener configuración SMTP de DB: {str(e)}")
                smtp_config = None

        subject = f"Código de restablecimiento de contraseña - {business_name}"

        # Contenido HTML del email
        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f5f5f5;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">

                    <!-- Header -->
                    <tr>
                        <td style="background: linear-gradient(135deg, #3A64D9 0%, #254EC1 100%); padding: 40px 20px; text-align: center;">
                            <h1 style="color: #ffffff; margin: 0; font-size: 28px; font-weight: bold;">
                                {business_name}
                            </h1>
                        </td>
                    </tr>

                    <!-- Content -->
                    <tr>
                        <td style="padding: 40px 30px;">
                            <h2 style="color: #0B1638; margin: 0 0 20px 0; font-size: 24px;">
                                Restablece tu contraseña
                            </h2>

                            <p style="color: #666666; line-height: 1.6; margin: 0 0 20px 0; font-size: 16px;">
                                Hemos recibido una solicitud para restablecer la contraseña de tu cuenta.
                                Utiliza el siguiente código de verificación:
                            </p>

                            <!-- Code Box -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 30px 0;">
                                <tr>
                                    <td align="center" style="background-color: #f8f9fa; border: 2px solid #3A64D9; border-radius: 8px; padding: 20px;">
                                        <p style="margin: 0 0 10px 0; color: #666666; font-size: 14px; font-weight: bold;">
                                            CÓDIGO DE VERIFICACIÓN
                                        </p>
                                        <p style="margin: 0; color: #3A64D9; font-size: 36px; font-weight: bold; letter-spacing: 8px; font-family: 'Courier New', monospace;">
                                            {code}
                                        </p>
                                    </td>
                                </tr>
                            </table>

                            <p style="color: #666666; line-height: 1.6; margin: 20px 0; font-size: 16px;">
                                Este código <strong>expirará en 30 minutos</strong>. Si no solicitaste restablecer tu contraseña,
                                puedes ignorar este mensaje de forma segura.
                            </p>

                            <!-- Warning Box -->
                            <table width="100%" cellpadding="0" cellspacing="0" style="margin: 20px 0;">
                                <tr>
                                    <td style="background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 15px; border-radius: 4px;">
                                        <p style="margin: 0; color: #856404; font-size: 14px;">
                                            <strong>⚠️ Importante:</strong> Por seguridad, nunca compartas este código con nadie.
                                            Nuestro equipo nunca te pedirá este código por teléfono o email.
                                        </p>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>

                    <!-- Footer -->
                    <tr>
                        <td style="background-color: #f8f9fa; padding: 30px; text-align: center; border-top: 1px solid #e0e0e0;">
                            <p style="color: #999999; margin: 0 0 10px 0; font-size: 14px;">
                                {business_name} - Sistema de Gestión Empresarial
                            </p>
                            <p style="color: #999999; margin: 0; font-size: 12px;">
                                Este es un correo automático, por favor no respondas a este mensaje.
                            </p>
                        </td>
                    </tr>

                </table>
            </td>
        </tr>
    </table>
</body>
</html>
        """

        # Contenido de texto plano (fallback)
        text_content = f"""
{business_name}
Restablece tu contraseña

Hemos recibido una solicitud para restablecer la contraseña de tu cuenta.

Tu código de verificación es: {code}

Este código expirará en 30 minutos.

Si no solicitaste restablecer tu contraseña, puedes ignorar este mensaje de forma segura.

IMPORTANTE: Por seguridad, nunca compartas este código con nadie.

---
{business_name} - Sistema de Gestión Empresarial
Este es un correo automático, por favor no respondas a este mensaje.
        """

        return EmailService._send_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            smtp_config=smtp_config,
            db=db,
        )

    @staticmethod
    def send_welcome_email(email: str, name: str, business_name: str = "FileMeshy", db: Session = None) -> bool:
        """
        Envía email de bienvenida a nuevo usuario.

        Args:
            email: Email del destinatario
            name: Nombre del usuario
            business_name: Nombre del negocio

        Returns:
            True si se envió correctamente
        """
        subject = f"Bienvenido a {business_name}"

        html_content = f"""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
</head>
<body style="margin: 0; padding: 0; font-family: Arial, sans-serif; background-color: #f5f5f5;">
    <table width="100%" cellpadding="0" cellspacing="0" style="background-color: #f5f5f5; padding: 20px;">
        <tr>
            <td align="center">
                <table width="600" cellpadding="0" cellspacing="0" style="background-color: #ffffff; border-radius: 8px;">
                    <tr>
                        <td style="background: linear-gradient(135deg, #3A64D9 0%, #254EC1 100%); padding: 40px; text-align: center;">
                            <h1 style="color: #ffffff; margin: 0;">¡Bienvenido a {business_name}!</h1>
                        </td>
                    </tr>
                    <tr>
                        <td style="padding: 40px;">
                            <h2 style="color: #0B1638;">Hola {name},</h2>
                            <p style="color: #666666; line-height: 1.6;">
                                Gracias por unirte a {business_name}. Tu cuenta ha sido creada exitosamente.
                            </p>
                            <p style="color: #666666; line-height: 1.6;">
                                Ahora puedes acceder a todas las funcionalidades del sistema.
                            </p>
                        </td>
                    </tr>
                    <tr>
                        <td style="background-color: #f8f9fa; padding: 20px; text-align: center;">
                            <p style="color: #999999; margin: 0; font-size: 12px;">
                                {business_name} - Sistema de Gestión Empresarial
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
        """

        text_content = f"""
¡Bienvenido a {business_name}!

Hola {name},

Gracias por unirte a {business_name}. Tu cuenta ha sido creada exitosamente.

Ahora puedes acceder a todas las funcionalidades del sistema.

---
{business_name} - Sistema de Gestión Empresarial
        """

        return EmailService._send_email(
            to_email=email,
            subject=subject,
            html_content=html_content,
            text_content=text_content,
            db=db,
        )
