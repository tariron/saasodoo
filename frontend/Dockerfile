FROM python:3.9-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

EXPOSE 5001

# The command in docker-compose.yml will override this for development
CMD ["python", "app.py"] 