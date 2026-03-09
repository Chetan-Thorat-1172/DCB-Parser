# ── Base image ────────────────────────────────────────────────────────────
FROM python:3.13-slim

# ── System deps ───────────────────────────────────────────────────────────
# pymupdf needs some native libraries
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libmupdf-dev \
        libfreetype6 \
        libharfbuzz0b \
        libjpeg62-turbo \
        libopenjp2-7 \
    && rm -rf /var/lib/apt/lists/*

# ── Working directory ─────────────────────────────────────────────────────
WORKDIR /app

# ── Install Python dependencies ──────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Copy the parser package source ────────────────────────────────────────
COPY pyproject.toml .
COPY src/ src/
RUN pip install --no-cache-dir .

# ── Copy the Cloud Run service ────────────────────────────────────────────
COPY service/ service/

# ── Environment variables (overridable at deploy time) ────────────────────
ENV PORT=8080
ENV RAW_PDF_BUCKET=dcb-credit-raw-pdf
ENV PROCESSED_JSON_BUCKET=dcb-credit-processed-json
ENV PUBSUB_TOPIC=cibil-pdf-parsed
ENV LOG_LEVEL=INFO
ENV TEMP_DIR=/tmp/cibil-parser

# ── Expose port ───────────────────────────────────────────────────────────
EXPOSE 8080

# ── Run with gunicorn for production ──────────────────────────────────────
CMD exec gunicorn \
    --bind 0.0.0.0:$PORT \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --chdir /app/service \
    main:app
