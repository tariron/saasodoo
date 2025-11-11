FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        libpq-dev \
        curl \
        postgresql-client \
        sudo \
        attr \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY services/instance-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities and schemas
COPY shared /app/shared

# Copy application code
COPY services/instance-service/ .

# Create non-root user with Docker access
RUN groupadd -r appuser && useradd -r -g appuser appuser
# Add user to docker group (gid 988) for socket access
RUN groupadd -g 988 docker || true && usermod -a -G docker appuser
# Create backup directories with proper ownership
RUN mkdir -p /var/lib/odoo/backups/active /var/lib/odoo/backups/staging /var/lib/odoo/backups/temp \
    && chown -R appuser:appuser /var/lib/odoo
RUN chown -R appuser:appuser /app
# Run as root to allow volume access and Docker operations
# USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:8003/health || exit 1

# Expose port
EXPOSE 8003

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8003"]
