FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY services/billing-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy shared utilities and schemas
COPY shared /app/shared

# Copy application code
COPY services/billing-service/app/ ./app/

# Copy tests
COPY services/billing-service/tests/ ./tests/

# Copy overdue configuration
COPY services/billing-service/overdue.xml ./overdue.xml

# Copy catalog configuration
COPY services/billing-service/killbill_catalog.xml ./killbill_catalog.xml

# Expose port
EXPOSE 8004

# Run the application with Hypercorn (HTTP/2 support)
CMD ["hypercorn", "app.main:app", "--bind", "0.0.0.0:8004", "--reload"]
