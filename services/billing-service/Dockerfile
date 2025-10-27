FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY app/ ./app/

# Copy tests
COPY tests/ ./tests/

# Copy overdue configuration
COPY overdue.xml ./overdue.xml

# Copy catalog configuration
COPY killbill_catalog.xml ./killbill_catalog.xml

# Expose port
EXPOSE 8004

# Run the application with Hypercorn (HTTP/2 support)
CMD ["hypercorn", "app.main:app", "--bind", "0.0.0.0:8004", "--reload"]
