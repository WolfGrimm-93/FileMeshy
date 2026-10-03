# Pin por DIGEST (Ronda 10) -- "22-alpine" es una tag flotante (Node 22.x +
# base Alpine que se actualizan sin aviso en cualquier rebuild). v22.23.2
# confirmado en vivo con `node --version` corriendo la imagen real,
# digest vigente al 2026-09-22.
FROM node:22-alpine@sha256:b6f26b36c8ff49624cfdac716b8ea1138d606df02586a77d364bb5536a634f85 AS build

RUN corepack enable && corepack prepare pnpm@11.6.0 --activate

WORKDIR /app

# Copiar package files e instalar dependencias
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN pnpm install --frozen-lockfile

# Copiar codigo fuente
COPY . .

# Variables de entorno para el build (se pueden sobreescribir en docker-compose)
ARG VITE_API_URL=http://localhost:8000/api/v1
ARG VITE_APP_NAME=FileMeshy
ARG VITE_APP_ENV=production
ARG VITE_TENANT_SLUG=
ARG VITE_ENABLE_TENANT_SELECTOR=false

ENV VITE_API_URL=$VITE_API_URL
ENV VITE_APP_NAME=$VITE_APP_NAME
ENV VITE_APP_ENV=$VITE_APP_ENV
ENV VITE_TENANT_SLUG=$VITE_TENANT_SLUG
ENV VITE_ENABLE_TENANT_SELECTOR=$VITE_ENABLE_TENANT_SELECTOR

# Build de produccion (solo vite build, sin tsc que falla por ejemplos legacy)
RUN pnpm build:prod

# --- Etapa de produccion ---
# Pin por DIGEST (Ronda 10) -- mismo criterio que la etapa de build:
# "alpine" es flotante. nginx/1.31.6 confirmado en vivo con `nginx -v`
# corriendo la imagen real, digest vigente al 2026-09-22.
FROM nginx:alpine@sha256:df221db836e1754089190208cee7eeda94f233197056426eda74a43ab1abeac2

# Copiar config de nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiar build del frontend
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
