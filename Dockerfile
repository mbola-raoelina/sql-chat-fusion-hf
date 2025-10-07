# Dockerfile for Oracle SQL Assistant - Bedrock Enhanced
# Optimized for Hugging Face Spaces deployment

FROM python:3.10-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# CRITICAL FIX: Pre-download sentence-transformers models during build
# This ensures models are cached before container becomes read-only
RUN python -c "from sentence_transformers import SentenceTransformer; \
    import os; \
    os.makedirs('/tmp/sentence_transformers', exist_ok=True); \
    print('Downloading thenlper/gte-base...'); \
    SentenceTransformer('thenlper/gte-base', cache_folder='/tmp/sentence_transformers', device='cpu'); \
    print('Downloading all-MiniLM-L6-v2 (fallback)...'); \
    SentenceTransformer('all-MiniLM-L6-v2', cache_folder='/tmp/sentence_transformers', device='cpu'); \
    print('Models downloaded successfully!')"

# Copy application files
COPY . .

# Expose port for Flask app
EXPOSE 7860

# Set environment variables for Flask
ENV FLASK_APP=app_enhanced.py
ENV FLASK_ENV=production
ENV PYTHONUNBUFFERED=1

# CRITICAL FIX: Set cache directories to /tmp/ (writable in Docker)
ENV HF_HOME=/tmp/huggingface
ENV TRANSFORMERS_CACHE=/tmp/transformers
ENV SENTENCE_TRANSFORMERS_HOME=/tmp/sentence_transformers
ENV HOME=/tmp

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:7860/ || exit 1

# Run the Flask application
CMD ["python", "app_enhanced.py"]

