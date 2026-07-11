FROM python:3.10-slim

# Prevent Python from writing .pyc files and buffering stdout/stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install system dependencies required for compiling libraries (if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt /app/
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy project files
COPY . /app/

# Create a non-root user and assign ownership of the /app directory
RUN groupadd -g 8888 appgroup && \
    useradd -r -u 8888 -g appgroup appuser && \
    mkdir -p /app/app/data /app/app/data/uploads /app/app/data/outputs /app/app/data/history && \
    chown -R appuser:appgroup /app

# Switch to the non-root user
USER appuser

# Expose port (default for FastAPI)
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
