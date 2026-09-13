# Checklist de Funcionalidades

Lista de funcionalidades típicas de una nube personal tipo Google Drive, para usar como
referencia de alcance del producto. Ver también [Módulos](modulos/index.md) para el mismo
checklist desglosado por módulo de producto, y
[Estándares Cliente-Servidor 2026](estandares-cliente-servidor-2026/index.md) para los
estándares técnicos de calidad (no son funcionalidades del producto).

## Almacenamiento y archivos
- Subida/descarga de archivos (individual y por lotes)
- Soporte de carpetas y subcarpetas
- Drag & drop
- Vista previa de archivos (imágenes, PDF, video, audio, documentos de office)
- Búsqueda por nombre y contenido
- Papelera con recuperación
- Versionado de archivos (historial de cambios)
- Cuotas de almacenamiento por usuario

## Organización
- Renombrar, mover, copiar, eliminar
- Favoritos / destacados
- Etiquetas o categorías
- Ordenamiento (nombre, fecha, tamaño, tipo)
- Vista en lista y en cuadrícula

## Compartir y colaboración
- Compartir por enlace (con o sin expiración)
- Permisos granulares (lectura, escritura, solo comentar)
- Compartir con usuarios específicos
- Protección con contraseña en enlaces compartidos
- Edición colaborativa en tiempo real (documentos/hojas de cálculo)
- Comentarios sobre archivos

## Sincronización y acceso
- Cliente de sincronización de escritorio (Windows/Mac/Linux)
- App móvil con subida automática de fotos
- Acceso web (navegador)
- Sincronización selectiva de carpetas
- Acceso offline

## Seguridad
- Autenticación de dos factores (2FA)
- Cifrado en tránsito (TLS)
- Cifrado en reposo
- Cifrado de extremo a extremo (opcional)
- Registro de auditoría (quién accedió/modificó qué)
- Control de sesiones activas / cierre remoto

## Administración
- Gestión de usuarios y grupos
- Panel de administración
- Backups automáticos
- Monitoreo de uso de almacenamiento y actividad
- Multi-tenant (aislar datos, usuarios y almacenamiento por organización/espacio de trabajo dentro de la misma instancia)

## Extras
- Integración con apps de terceros (API)
- Escaneo de virus/malware en archivos subidos
- Notificaciones (cambios, comentarios, compartidos)
- Búsqueda avanzada (filtros por tipo, fecha, tamaño)
- OCR / búsqueda de texto dentro de imágenes o PDFs escaneados
