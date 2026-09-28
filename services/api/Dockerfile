# Build context is the repo root (docker-compose.yml), matching every other
# service's Dockerfile, so this can pull in libs/fleetcore (geohash,
# depot_routing) the same way ingest-gateway does.
FROM python:3.12-slim

WORKDIR /app

COPY libs /app/libs
COPY services/api/requirements.txt /app/services/api/requirements.txt
RUN pip install --no-cache-dir -r /app/services/api/requirements.txt -e /app/libs

COPY services/api /app/services/api

EXPOSE 8000
CMD ["python", "/app/services/api/main.py"]
