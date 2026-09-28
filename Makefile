.DEFAULT_GOAL := help
RATE ?= 1000
VIN ?=
TYPE ?= overheat

.PHONY: help certs up down ps logs seed simulate bench-ingest burst inject-fault \
        batch train test chaos lint

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*## "}{printf "%-16s %s\n", $$1, $$2}'

certs: ## Generate the dev CA + Mosquitto server cert for mTLS
	bash infra/certs/generate-dev-certs.sh

up: certs ## Start the core compose profile
	docker compose --profile core up -d

down: ## Stop the core compose profile
	docker compose --profile core down

ps: ## Show status of running compose services
	docker compose ps

logs: ## Tail logs for the core profile
	docker compose --profile core logs -f --tail=100

seed: ## Seed 100K vehicles/drivers/depots into Postgres (session 3+)
	@echo "TODO (session 3): seed script not yet built"

simulate: ## Run the truck simulator against MQTT, e.g. make simulate RATE=20000 (session 2+)
	@echo "TODO (session 2): simulator not yet built (RATE=$(RATE))"

bench-ingest: ## Dedicated ingest throughput benchmark (session 2+)
	@echo "TODO (session 2): bench-ingest not yet built"

burst: ## 3x burst load test (session 9+)
	@echo "TODO (session 9): burst test not yet built"

inject-fault: ## Inject a planted failure, e.g. make inject-fault VIN=... TYPE=overheat (session 2+)
	@echo "TODO (session 2): fault injection not yet built (VIN=$(VIN) TYPE=$(TYPE))"

batch: ## Run the Spark nightly feature job (session 5+)
	@echo "TODO (session 5): Spark batch job not yet built"

train: ## Train the sklearn model vs baseline (session 5+)
	@echo "TODO (session 5): training script not yet built"

test: ## Run the full test suite (unit + integration + contract + BDD)
	@echo "TODO: no test suites exist yet (session 2 adds the first unit tests)"

chaos: ## Kill a broker/gateway/TM mid-load and verify zero-loss recovery (session 9+)
	@echo "TODO (session 9): chaos scripts not yet built"

lint: ## Run lint stub (extended by each service as it's added)
	@echo "TODO: no lintable service code yet"
