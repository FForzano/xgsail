# SailFrames self-hosted API service.
# Serves the web dashboard (static), the read/write API, and the MinIO
# ingest webhook. See deploy/README.md for the full stack.
#
# Debian-slim base: numpy/pandas ship precompiled glibc wheels here.
FROM python:3.12-slim

# Reachable from compose: web.api.main imported as a package.
WORKDIR /app

# Install deps first for layer caching.
COPY deploy/requirements.txt /app/deploy/requirements.txt
RUN pip install --no-cache-dir -r /app/deploy/requirements.txt

# Application code: web app + processing pipeline + the upload handler.
COPY web/ /app/web/
COPY processing/ /app/processing/
COPY lambda/process_upload/ /app/lambda/process_upload/

# Self-hosted frontend config (empty API URL -> same-origin).
COPY deploy/config.docker.js /app/web/config.js

# handler.py is imported as a top-level module via PYTHONPATH.
ENV PYTHONPATH=/app:/app/lambda/process_upload
ENV PYTHONUNBUFFERED=1

# Run as non-root.
RUN useradd --create-home --uid 10001 sailframes \
    && chown -R sailframes:sailframes /app
USER sailframes

EXPOSE 8000
CMD ["uvicorn", "web.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
