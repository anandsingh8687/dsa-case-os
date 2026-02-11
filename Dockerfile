# Production Dockerfile for DSA Case OS Backend
# Optimized for Railway deployment

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-eng \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first (for better caching)
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/ ./

# Create necessary directories
RUN mkdir -p /app/uploads /app/temp

# Health check
HEALTHCHECK --interval=30s --timeout=3s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:${PORT:-8000}/health || exit 1

# Expose port (Railway will set PORT env variable)
EXPOSE 8000

# Run with dynamic port from Railway
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
