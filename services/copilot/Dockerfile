# Build context is the repo root (docker-compose.yml), matching every other
# service's Dockerfile.
FROM python:3.12-slim

WORKDIR /app

COPY libs /app/libs
COPY services/copilot/requirements.txt /app/services/copilot/requirements.txt
RUN pip install --no-cache-dir -r /app/services/copilot/requirements.txt -e /app/libs

COPY services/copilot /app/services/copilot

EXPOSE 9100
CMD ["python", "/app/services/copilot/main.py"]
