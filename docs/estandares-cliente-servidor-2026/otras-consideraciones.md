# Otras Consideraciones

Parte de [Estándares Cliente-Servidor 2026](index.md)

Puntos que no entran limpio en las demás categorías, pero valen la pena tener en cuenta.

## Checklist
- [ ] Passkeys/WebAuthn — login sin contraseña, no solo 2FA por TOTP
- [ ] Zero-trust / principio de menor privilegio entre servicios internos (backend↔worker↔storage), no solo en el borde
- [ ] Supply chain security: SBOM, verificación de firmas de imágenes Docker, pinning de versiones exactas de dependencias
- [ ] Exportación de datos / portabilidad (archivos + metadata) sin depender de soporte manual
- [ ] Flujo de borrado de cuenta completo (no solo desactivar) y qué pasa con lo compartido con terceros
- [ ] CAPTCHa / protección anti-bot en registro y endpoints públicos (compartir por link, login)
- [ ] Manejo de abuso de contenido en compartir público (contenido ilegal, spam masivo por link)
- [ ] Feature flags para lanzar y apagar cambios sin deploy
- [ ] Runbooks de incidentes (pasos concretos ante caída de DB/storage, no solo alertas)
- [ ] IaC (Infrastructure as Code) — infra versionada, no configurada a mano en el servidor
- [ ] Presupuesto de performance (Core Web Vitals: LCP/INP/CLS) medido, no solo "se ve rápido"
- [ ] Costo de storage a escala — política de retención/compresión antes de que el costo deje de ser trivial
- [ ] Términos de servicio / política de privacidad si hay usuarios externos reales
- [ ] Rotación automática de secretos sin downtime
