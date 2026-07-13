FROM python:3.11-slim

WORKDIR /app

# System dependencies for compiling psycopg2 and PostGIS drivers
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ /app/

# Expose FastAPI port
EXPOSE 8000

# Run uvicorn on 0.0.0.0
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
