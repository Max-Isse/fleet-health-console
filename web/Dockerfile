FROM node:25-alpine AS build
WORKDIR /web
COPY package.json package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY . .
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.29-alpine
# Apply Alpine security fixes released after the base image was built (Trivy gates CRITICAL ones in CI).
USER root
RUN apk upgrade --no-cache
USER 101
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY security-headers.inc /etc/nginx/snippets/security-headers.inc
COPY --from=build /web/dist /usr/share/nginx/html
EXPOSE 8080
