# Dockerfile for API Gateway service
# This will be a simple Flask/FastAPI or other lightweight framework container.
FROM python:3.11-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# CMD [ "python", "app.py" ] # Or uvicorn, gunicorn, etc. 