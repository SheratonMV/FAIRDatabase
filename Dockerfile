FROM python:3.10-slim

# Runtime dependencies: libpq5 for psycopg2-binary, curl for healthcheck
RUN apt-get update \
    && apt-get install -y --no-install-recommends libpq5 curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps first for layer caching
COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

# Copy application code
# Must be at repo root because app.py references ../frontend/templates and ../static
COPY AnonyBiome/ /app/AnonyBiome/
COPY backend/ /app/backend/
COPY frontend/ /app/frontend/
COPY static/ /app/static/

# Entrypoint script
COPY docker-entrypoint.sh /app/docker-entrypoint.sh
RUN chmod +x /app/docker-entrypoint.sh

# Working directory matches the dev setup (run.sh runs from backend/)
WORKDIR /app/backend

# PYTHONPATH=/app mirrors run.sh: export PYTHONPATH=$(pwd)/..
# This makes "from AnonyBiome.anonymization..." resolve correctly
ENV PYTHONPATH=/app

# Create uploads directory
RUN mkdir -p /app/backend/uploads

EXPOSE 5000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["flask", "run", "--host", "0.0.0.0"]
