.DEFAULT_GOAL := help
RATE ?= 1000
VIN ?=
TYPE ?= overheat
PYTHON := $(shell if [ -x .venv/Scripts/python.exe ]; then echo .venv/Scripts/python.exe; \
                   elif [ -x .venv/bin/python ]; then echo .venv/bin/python; \
                   else echo python; fi)

.PHONY: help setup certs up down ps logs migrate seed simulate bench-ingest burst inject-fault \
        lake-init flink-submit backfill batch train build-kb refresh-risk metabase-init test \
        test-integration test-contract test-bdd test-all chaos lint explain

VEHICLES ?= 5000
DAYS ?= 30
BASELINE_RATE ?= 500

help: ## Show this help
	@grep -hE '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN{FS=":.*## "}{printf "%-16s %s\n", $$1, $$2}'

setup: ## Create .venv and install dev + fleetcore + ml deps (run once, or after touching requirements)
	python -m venv .venv
	$(PYTHON) -m pip install -q --upgrade pip
	$(PYTHON) -m pip install -q -r requirements-dev.txt -r services/ml/requirements.txt -e libs

certs: ## Generate the dev CA + Mosquitto server cert, plus per-shard client certs, for mTLS
	bash infra/certs/generate-dev-certs.sh
	$(PYTHON) infra/certs/issue-shard-certs.py

up: certs ## Start the core compose profile
	docker compose --profile core up -d

down: ## Stop the core compose profile
	docker compose --profile core down

ps: ## Show status of running compose services
	docker compose ps

logs: ## Tail logs for the core profile
	docker compose --profile core logs -f --tail=100

migrate: ## Apply Postgres + Timescale SQL migrations against the running core stack
	bash db/migrate.sh

seed: migrate ## Seed 100K vehicles/drivers/depots into Postgres
	$(PYTHON) db/postgres/seed_fleet.py

simulate: ## Run the truck simulator against MQTT, e.g. make simulate RATE=20000
	$(PYTHON) services/simulator/main.py --rate $(RATE)

bench-ingest: ## Dedicated ingest throughput benchmark, 5 min, e.g. make bench-ingest RATE=20000
	$(PYTHON) services/simulator/bench_ingest.py --rate $(RATE) --duration 300

burst: ## 3x burst load test: lag + zero-loss, e.g. make burst BASELINE_RATE=500
	$(PYTHON) services/simulator/burst_test.py --baseline-rate $(BASELINE_RATE)

inject-fault: ## Inject a planted failure, e.g. make inject-fault VIN=... TYPE=overheat
	$(PYTHON) services/simulator/inject_fault.py --vin "$(VIN)" --type $(TYPE)

lake-init: ## One-time: provision the Garage bucket/key for Flink's Parquet/JSON lake sink
	bash infra/compose/garage-provision.sh

flink-submit: ## Submit the Flink SQL pipeline (dedup, rules, CEP, sinks) as one job
	bash stream/flink/run-jobs.sh

backfill: ## Backfill synthetic telemetry history for ML training, e.g. make backfill VEHICLES=20000 DAYS=30
	$(PYTHON) db/timescale/backfill_history.py --vehicles $(VEHICLES) --days $(DAYS)

batch: ## Run the Spark nightly feature job (reads backfilled history, writes features.parquet)
	MSYS_NO_PATHCONV=1 docker compose --profile batch run --rm spark \
		/opt/spark/bin/spark-submit --conf spark.jars.ivy=/tmp/ivy2 \
		--packages org.postgresql:postgresql:42.7.3 /opt/spark-jobs/feature_job.py

train: ## Train the sklearn model vs baseline, write docs/evidence/ml/report.md, score predictions
	$(PYTHON) services/ml/train.py

build-kb: ## Populate the pgvector DTC knowledge base + failure signatures
	$(PYTHON) services/ml/build_kb.py

refresh-risk: ## Refresh the vehicle_latest_risk materialized view the at-risk API reads (run after make train)
	docker compose exec -T postgres sh -c 'psql -U "$$POSTGRES_USER" -d "$$POSTGRES_DB" -v ON_ERROR_STOP=1 -q -c "REFRESH MATERIALIZED VIEW CONCURRENTLY vehicle_latest_risk;"'

metabase-init: ## One-time (idempotent): bootstrap Metabase admin + DB connections + dashboard (needs obs profile up)
	$(PYTHON) infra/compose/metabase-provision.py

test: ## Run the unit suite only (fast, no docker required beyond what's already up)
	$(PYTHON) -m pytest tests/unit -q

test-integration: ## Testcontainers integration tests (spins ephemeral Postgres/Kafka/Redis/Mongo — no `make up` needed)
	$(PYTHON) -m pytest tests/integration -q

test-contract: ## Pact (web<->api) + JSON-Schema (telemetry message) contract tests
	$(PYTHON) -m pytest tests/contract -q

test-bdd: ## behave acceptance scenarios (PLAN §5) — needs the live core stack: run `make up && make seed` first
	PYTHONPATH="libs;services/simulator/src" $(PYTHON) -m behave tests/bdd

test-all: test test-integration test-contract test-bdd ## Everything: unit, integration, contract, BDD

explain: ## Capture real EXPLAIN ANALYZE before/after for PLAN §2's 3 SQL optimisations
	$(PYTHON) docs/evidence/sql/run_explain.py

chaos: ## Kill flink-taskmanager mid-load, verify zero-loss recovery by seq (needs make flink-submit first)
	$(PYTHON) services/simulator/chaos_test.py

chaos-broker: ## Kill a Kafka broker (chaos profile, 3-broker cluster) mid-produce, verify zero-loss (needs: docker compose --profile chaos up -d)
	$(PYTHON) services/simulator/chaos_broker_test.py

chaos-gateway: ## Kill one of 2 ingest-gateway copies mid-load, verify zero-loss (needs: docker compose --profile core up -d --scale ingest-gateway=2)
	$(PYTHON) services/simulator/chaos_gateway_test.py

lint: ## Ruff over every Python service/lib + eslint over web
	$(PYTHON) -m ruff check libs services db batch tests
	cd web && npm run lint
