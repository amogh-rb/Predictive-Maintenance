# Build context is the repo root (docker-compose.yml), so this can pull in
# libs/fleetcore, the shared domain lib every service depends on.
FROM python:3.12-slim

WORKDIR /app

COPY libs /app/libs
COPY services/ingest-gateway/requirements.txt /app/services/ingest-gateway/requirements.txt
RUN pip install --no-cache-dir -r /app/services/ingest-gateway/requirements.txt -e /app/libs

COPY services/ingest-gateway /app/services/ingest-gateway

CMD ["python", "/app/services/ingest-gateway/main.py"]
