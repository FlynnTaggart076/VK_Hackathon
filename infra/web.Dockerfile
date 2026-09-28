FROM node:22-bookworm-slim AS build
WORKDIR /workspace/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci
COPY apps/web ./
ARG VITE_APP_BASE=/team/zhkh/
ARG VITE_PREVIEW_MODE=false
RUN npm run build

FROM nginx:1.27.5-alpine
COPY --from=build /workspace/apps/web/dist /usr/share/nginx/html
COPY infra/nginx/app-vm.conf /etc/nginx/conf.d/default.conf
