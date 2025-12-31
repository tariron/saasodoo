FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY services/notification-service/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities and schemas
COPY shared /app/shared

# Copy application code
COPY services/notification-service/ .

# Create non-root user for security
RUN useradd -m -u 1000 notificationuser && chown -R notificationuser:notificationuser /app
USER notificationuser

# Expose port
EXPOSE 5000

# Health check using Python httpx (curl not available in slim image)
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD python -c "import httpx; r = httpx.get('http://localhost:5000/health', timeout=10); exit(0 if r.status_code == 200 else 1)"

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "5000"]
