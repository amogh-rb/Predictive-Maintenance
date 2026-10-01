# Build context is the repo root (docker-compose.yml), so this can pull in
# libs/fleetcore (depot_routing's Dijkstra) like every other service's
# Dockerfile.
FROM python:3.12-slim

WORKDIR /app

COPY libs /app/libs
COPY services/mcp-server/requirements.txt /app/services/mcp-server/requirements.txt
RUN pip install --no-cache-dir -r /app/services/mcp-server/requirements.txt -e /app/libs

COPY services/mcp-server /app/services/mcp-server

EXPOSE 9001
CMD ["python", "/app/services/mcp-server/main.py"]
