FROM python:3.11-slim

# Install system dependencies for PostgreSQL client and CephFS utilities
RUN apt-get update && apt-get install -y \
    postgresql-client \
    attr \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY services/database-service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/database-service/app/ ./app/

# Copy shared utilities (mounted as volume in production, but copy for builds)
# COPY ../shared /app/shared

# Expose port
EXPOSE 8005

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8005/health')" || exit 1

# Run the FastAPI application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
