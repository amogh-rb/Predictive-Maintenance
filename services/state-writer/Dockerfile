# Build context is the repo root (docker-compose.yml), so this can pull in
# libs/fleetcore like ingest-gateway's Dockerfile does — though state-writer
# doesn't currently import it, keeping the pattern consistent costs nothing.
FROM python:3.12-slim

WORKDIR /app

COPY libs /app/libs
COPY services/state-writer/requirements.txt /app/services/state-writer/requirements.txt
RUN pip install --no-cache-dir -r /app/services/state-writer/requirements.txt -e /app/libs

COPY services/state-writer /app/services/state-writer

CMD ["python", "/app/services/state-writer/main.py"]
