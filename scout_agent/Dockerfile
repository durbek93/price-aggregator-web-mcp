FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create a non-root user and assign ownership of the /app directory
RUN groupadd -g 8888 appgroup && \
    useradd -r -u 8888 -g appgroup appuser && \
    mkdir -p /app/downloads && \
    chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

CMD ["python", "main.py"]
