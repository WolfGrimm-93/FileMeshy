"""Rutas del FRONTEND a las que apuntan las notificaciones (`action_url`).

Fuente única: cualquier notificación nueva debe usar estas constantes. Tienen
que existir en filemeshy_front/src/App.tsx (lo verifica
tests/test_notification_action_urls.py). Ronda 12b: antes se generaban
`/configuracion/almacenamiento` y `/archivos/compartidos`, que dan 404 en el
frontend."""

# "Compartido conmigo" (share dirigido recién creado)
ACTION_URL_SHARED_WITH_ME = "/compartido-conmigo"
# Cuota propia cerca del límite: el uso se ve en el explorador de archivos
# (`/cuotas-almacenamiento` es la pantalla ADMIN de cuotas, requiere permiso)
ACTION_URL_MY_FILES = "/archivos"
# Aviso de cambio de contraseña -> pantalla de preferencias de la cuenta
ACTION_URL_PREFERENCES = "/preferencias"
# Alertas de seguridad -> logs de auditoría (pantalla de administradores)
ACTION_URL_AUDIT_LOGS = "/logs"

# Migración de filas históricas de `notifications` (scripts/fix_notification_urls.py)
LEGACY_ACTION_URL_MAP = {
    "/archivos/compartidos": ACTION_URL_SHARED_WITH_ME,
    "/configuracion/almacenamiento": ACTION_URL_MY_FILES,
}
