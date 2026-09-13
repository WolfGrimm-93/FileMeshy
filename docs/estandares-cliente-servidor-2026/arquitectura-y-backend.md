# Arquitectura y Backend

Parte de [Estándares Cliente-Servidor 2026](index.md)

## Checklist
- [ ] API bien versionada (REST/GraphQL/gRPC) con contrato documentado (OpenAPI/Swagger)
- [ ] Separación clara de capas (routing, lógica de negocio, acceso a datos)
- [ ] Validación de entrada en cada endpoint (esquemas, no confiar en el cliente)
- [ ] Manejo de errores consistente (códigos HTTP correctos, formato de error estándar)
- [ ] Migraciones de base de datos versionadas y reproducibles
- [ ] Idempotencia en operaciones críticas (pagos, creación de recursos)
- [ ] Rate limiting y throttling por usuario/IP
- [ ] Health checks y readiness/liveness probes
