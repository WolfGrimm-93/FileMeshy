# Seguridad

Parte de [Estándares Cliente-Servidor 2026](index.md)

## Checklist
- [ ] Autenticación robusta (OAuth2/OIDC, JWT con rotación de refresh tokens)
- [ ] Autorización granular (RBAC o ABAC según el caso)
- [ ] HTTPS/TLS en todo el tráfico, HSTS
- [ ] Protección contra OWASP Top 10 (inyección, XSS, CSRF, SSRF, etc.)
- [ ] Gestión de secretos fuera del código (vault/env, nunca hardcodeados)
- [ ] Cifrado de datos sensibles en reposo
- [ ] Auditoría de accesos y cambios
- [ ] Dependencias escaneadas por vulnerabilidades (SCA automatizado)
- [ ] CSP y demás headers de seguridad en el frontend
