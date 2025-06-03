FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies including Docker CLI
RUN apt-get update && apt-get install -y \
    curl \
    git \
    && curl -fsSL https://get.docker.com -o get-docker.sh \
    && sh get-docker.sh \
    && rm get-docker.sh \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better Docker layer caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/
COPY tests/ ./tests/

# Create non-root user for security
RUN useradd --create-home --shell /bin/bash tenant_user \
    && chown -R tenant_user:tenant_user /app

# Switch to non-root user
USER tenant_user

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8002/health')"

# Expose port
EXPOSE 8002

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8002", "--reload"] 