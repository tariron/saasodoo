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
# Production Runtime
# ======================
FROM python:3.11-slim AS runtime

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy React build output
COPY --from=builder /app/build ./frontend/build

# Copy Flask application
COPY backend/ .

# Create non-root user
RUN useradd --create-home --shell /bin/bash frontend_user \
    && chown -R frontend_user:frontend_user /app

USER frontend_user

# Expose port
EXPOSE 3000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:3000/health || exit 1

# Production command
CMD ["gunicorn", "--bind", "0.0.0.0:3000", "--workers", "2", "--timeout", "30", "app:app"]