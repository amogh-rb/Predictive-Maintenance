"""Spark nightly feature job (PLAN §2 "Batch/ML", §6.3 session 5).

Reads raw FAST/HEALTH telemetry straight from TimescaleDB (not the
`telemetry_fast_daily` continuous aggregate — that cagg only covers the
FAST-side columns session 3 anticipated needing; the failure signals that
matter most here (brake pad wear, 12V charge dip, DTC recurrence, tyre
sibling deltas) live in HEALTH, so this job aggregates both tables itself),
computes daily per-vehicle features with 7-day trailing slopes, joins the
offline ground-truth labels `db/timescale/backfill_history.py` wrote to
`data/labels.csv` (never a live store — PLAN §2 ML: "ground truth kept out of
feature tables to prevent leakage"), and writes one Parquet feature table for
`services/ml/train.py` to read.

Run via `make batch` (submits this into the `batch` profile's `spark`
container, which mounts this directory at /opt/spark-jobs).
"""
from __future__ import annotations

import os

from pyspark.sql import SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType

JOBS_DIR = "/opt/spark-jobs"
LABELS_PATH = f"{JOBS_DIR}/data/labels.csv"
OUTPUT_PATH = f"{JOBS_DIR}/output/features.parquet"

# Trailing window for slope/recurrence features (PLAN §2 Spark batch: "7/14-day
# slopes"); 7 chosen as the primary horizon since it matches the label horizon
# (predict failure within 7 days) — see `services/ml/train.py`.
TRAIL_DAYS = 7


def _tyre_sibling_delta(kpa: list) -> float | None:
    """Max deviation of one tyre's pressure from the mean of the other three."""
    if not kpa or len(kpa) < 2:
        return None
    total = sum(kpa)
    return max(abs(v - (total - v) / (len(kpa) - 1)) for v in kpa)


def main() -> None:
    spark = (
        SparkSession.builder.appName("fleetpulse-feature-job")
        .master("local[*]")
        .getOrCreate()
    )
    spark.sparkContext.setLogLevel("WARN")

    jdbc_url = (
        f"jdbc:postgresql://{os.environ['TIMESCALE_HOST']}:{os.environ['TIMESCALE_PORT']}/"
        f"{os.environ['TIMESCALE_DB']}"
    )
    jdbc_props = {
        "user": os.environ["TIMESCALE_USER"],
        "password": os.environ["TIMESCALE_PASSWORD"],
        "driver": "org.postgresql.Driver",
        "fetchsize": "10000",
    }

    fast = spark.read.jdbc(
        jdbc_url, "(SELECT * FROM telemetry_fast WHERE tenant = 'demo') AS t", properties=jdbc_props
    )
    health = spark.read.jdbc(
        jdbc_url, "(SELECT * FROM telemetry_health WHERE tenant = 'demo') AS t", properties=jdbc_props
    )

    labels = (
        spark.read.option("header", True)
        .csv(LABELS_PATH)
        .withColumn("onset_at", F.to_timestamp("onset_at"))
        .withColumn("failure_at", F.to_timestamp("failure_at"))
    )
    labeled_vins = labels.select("vin").distinct()

    fast = fast.join(F.broadcast(labeled_vins), "vin", "inner").withColumn("day", F.to_date("ts"))
    health = health.join(F.broadcast(labeled_vins), "vin", "inner").withColumn("day", F.to_date("ts"))

    daily_fast = fast.groupBy("vin", "day").agg(
        F.avg("coolant_c").alias("avg_coolant_c"),
        F.max("coolant_c").alias("max_coolant_c"),
        F.avg("oil_kpa").alias("avg_oil_kpa"),
        F.min("oil_kpa").alias("min_oil_kpa"),
        F.avg("rpm").alias("avg_rpm"),
        F.avg("load_pct").alias("avg_load_pct"),
        F.avg("ambient_c").alias("avg_ambient_c"),
        F.avg("trans_c").alias("avg_trans_c"),
        F.max("trans_c").alias("max_trans_c"),
        F.avg("fuel_rate_lph").alias("avg_fuel_rate_lph"),
        F.count(F.lit(1)).alias("fast_samples"),
    )

    tyre_delta_udf = F.udf(_tyre_sibling_delta, DoubleType())
    health = health.withColumn("tyre_delta_kpa", tyre_delta_udf("tire_kpa"))
    health = health.withColumn("any_dtc", (F.size("active_dtc") > 0).cast("int"))

    daily_health = health.groupBy("vin", "day").agg(
        F.min("charge_v").alias("min_charge_v"),
        F.avg("charge_v").alias("avg_charge_v"),
        F.min("batt_12v_rest_v").alias("min_batt_12v_rest_v"),
        F.min(F.array_min("brake_pad_pct")).alias("min_brake_pad_pct"),
        F.max("tyre_delta_kpa").alias("max_tyre_delta_kpa"),
        F.max("any_dtc").alias("any_dtc_today"),
        F.max("cell_v_delta_mv").alias("max_cell_v_delta_mv"),
        F.min("soh_pct").alias("min_soh_pct"),
        F.count(F.lit(1)).alias("health_samples"),
    )

    daily = daily_fast.join(daily_health, ["vin", "day"], "outer")

    w = Window.partitionBy("vin").orderBy("day").rowsBetween(-(TRAIL_DAYS - 1), 0)
    lag_w = Window.partitionBy("vin").orderBy("day")

    daily = (
        daily.withColumn("coolant_slope_7d", F.col("avg_coolant_c") - F.lag("avg_coolant_c", TRAIL_DAYS - 1).over(lag_w))
        .withColumn("oil_kpa_slope_7d", F.col("min_oil_kpa") - F.lag("min_oil_kpa", TRAIL_DAYS - 1).over(lag_w))
        .withColumn("charge_v_slope_7d", F.col("min_charge_v") - F.lag("min_charge_v", TRAIL_DAYS - 1).over(lag_w))
        .withColumn("brake_pad_slope_7d", F.col("min_brake_pad_pct") - F.lag("min_brake_pad_pct", TRAIL_DAYS - 1).over(lag_w))
        .withColumn("dtc_recurrence_7d", F.sum("any_dtc_today").over(w))
        .withColumn("max_tyre_delta_7d", F.max("max_tyre_delta_kpa").over(w))
    )

    # Label: 1 if this day falls inside [failure_at - 7d, failure_at) for the
    # vin's planted failure (predicting a failure "within 7 days", PLAN §1);
    # rows on/after failure_at are dropped (post-failure data isn't a
    # predictive-window feature row for the failure that already happened).
    # No planted failure at all -> every day is a negative example.
    daily = daily.join(labels, "vin", "left")
    daily = daily.withColumn(
        "days_to_failure",
        F.when(F.col("failure_at").isNotNull(), F.datediff(F.to_date("failure_at"), F.col("day"))),
    )
    daily = daily.filter(F.col("failure_at").isNull() | (F.col("days_to_failure") > 0))
    # A per-vin/day "any of the 5 Must failures within 7 days" label — kept
    # for the report's headline metric; train.py derives the per-failure-type
    # labels it actually trains on from `failure_type` + `days_to_failure`.
    daily = daily.withColumn(
        "any_failure_label",
        F.when(F.col("failure_at").isNull(), F.lit(0))
        .when(F.col("days_to_failure") <= 7, F.lit(1))
        .otherwise(F.lit(0)),
    )

    # `failure_type`/`failure_at`/`days_to_failure` are ground truth, not
    # features — train.py excludes them from the feature matrix explicitly.
    # `failure_type` is kept as the *target* for training one classifier per
    # failure type (empty string = no failure this window, i.e. negative for
    # every type); `days_to_failure` is kept only to compute "recall at >=5
    # days' lead" on the held-out set.
    daily = daily.drop("onset_at", "tenant")

    daily.write.mode("overwrite").parquet(OUTPUT_PATH)

    n = daily.count()
    n_pos = daily.filter(F.col("any_failure_label") == 1).count()
    n_vins = daily.select("vin").distinct().count()
    print(f"feature_job: wrote {n} rows ({n_pos} positive, {n_vins} vins) -> {OUTPUT_PATH}")

    spark.stop()


if __name__ == "__main__":
    main()
