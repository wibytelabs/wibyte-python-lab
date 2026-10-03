FROM node:22-slim AS build

WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend ./

ARG VITE_API_URL
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_PUBLISHABLE_KEY

RUN test -n "$VITE_API_URL" \
    && test -n "$VITE_SUPABASE_URL" \
    && test -n "$VITE_SUPABASE_PUBLISHABLE_KEY" \
    && npm run build

FROM nginx:1.28-alpine

ENV WPL_LISTEN_ADDRESS=127.0.0.1 \
    WPL_HTTP_PORT=8080

COPY --from=build /app/frontend/dist /usr/share/nginx/html
COPY deploy/nginx.conf.template /etc/nginx/templates/default.conf.template
