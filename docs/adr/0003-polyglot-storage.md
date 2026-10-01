# ADR 3: Polyglot storage

**Status:** accepted

| Store | Holds | Why |
|---|---|---|
| PostgreSQL 16 + pgvector | 3NF core, alerts, work orders, predictions, audit, DTC KB | ACID, RLS tenant isolation, CP |
| TimescaleDB (separate instance) | telemetry hypertables, continuous aggregate | isolates scan/write load from OLTP |
| MongoDB | vehicle twin documents, 7-day raw archive | shape varies by powertrain and tyre count |
| Redis | latest state, rate-limit buckets | sub-millisecond reads |
| S3-compatible lake (Garage) | JSON/Parquet history for Spark | cheap cold tier |

**Deviations (stated, not hidden).** MinIO became Garage (MinIO CE was pulled from registries). Parquet files come from Spark; the Flink lake sink writes JSON. Iceberg was dropped for the POC. Embeddings use a hashing trick instead of a sentence-transformer to avoid a ~2 GB dependency.

**Consequences.** Tenant isolation lives in Postgres RLS (API role is NOSUPERUSER NOBYPASSRLS). Metabase uses a read-only BYPASSRLS role on purpose (pooled connections cannot set a per-request tenant); it is cross-tenant analytics for a single-tenant demo, gated in the API by role. Erasure touches Postgres and Mongo; Timescale holds no driver PII.
