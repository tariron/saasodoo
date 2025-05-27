FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Assuming backend.app:app refers to /app/backend/app.py or similar
ENV FLASK_APP=backend.app:app

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libpq-dev \
        curl \
        git \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies from root
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

# Copy backend application code from the backend directory in the build context
COPY backend /app/backend
# Copy config directory from the build context
COPY config /app/config

# Create non-root user
RUN adduser --disabled-password --gecos '' appuser \
    && chown -R appuser:appuser /app
USER appuser

# Expose port
EXPOSE 5000

# Health check
# Ensure the health check URL is correct based on your app structure in /app/backend
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/api/health || exit 1

# Run the application
# WORKDIR is /app. Gunicorn needs to find backend.app:app
# This implies that /app must be in PYTHONPATH, or the app is structured such that backend.app works.
# If backend/app.py contains app=Flask(__name__), and backend is in /app/backend,
# then backend.app:app should resolve if /app is implicitly in python path or if app is run from /app.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "4", "--worker-class", "gevent", "backend.app:app"] 