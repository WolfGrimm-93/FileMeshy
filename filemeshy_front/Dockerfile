FROM node:22-alpine AS build

RUN corepack enable && corepack prepare pnpm@latest --activate

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
FROM nginx:alpine

# Copiar config de nginx
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copiar build del frontend
COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
