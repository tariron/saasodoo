# ======================
# Node.js Dependencies
# ======================
FROM node:18-alpine AS deps
WORKDIR /app
COPY frontend/package*.json ./
RUN npm install --only=production && npm cache clean --force

# ======================
# React Build Stage
# ======================
FROM node:18-alpine AS builder
WORKDIR /app

# Copy package files and install all dependencies
COPY frontend/package*.json ./
RUN npm install

# Copy source code and build
COPY frontend/ ./
RUN npm run build

# Verify build output
RUN ls -la build/ && test -f build/index.html

# ======================
# Production Runtime (Nginx)
# ======================
FROM nginx:alpine AS runtime

# Copy React build output
COPY --from=builder /app/build /usr/share/nginx/html

# Copy nginx config template
COPY nginx.conf /etc/nginx/templates/default.conf.template

# Nginx runs as non-root by default in alpine image
# Expose port 80
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD wget -q --spider http://localhost/health || exit 1

# Default environment values (override via ConfigMap)
ENV BASE_DOMAIN=localhost
ENV ENVIRONMENT=production

# Use envsubst to substitute environment variables at startup
CMD ["/bin/sh", "-c", "envsubst '${BASE_DOMAIN} ${ENVIRONMENT}' < /etc/nginx/templates/default.conf.template > /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
