"""Train one HistGradientBoostingClassifier per failure type (1-8: 1-5 Must
from session 5, 6-8 Should promoted to built in session 10b) vs the
threshold/DTC baseline (PLAN §2 ML, §6.3 session 5), report metrics, and
score the current fleet snapshot into Postgres `prediction`.

Reads `batch/spark/output/features.parquet` (written by `batch/spark/feature_job.py`).
Time-based split by day (train/val/test, chronological — no shuffling, so the
test set is always later in time than train, per PLAN §2 "Split: time-based").
One binary classifier per failure type, trained on that type's positives
only, since `prediction.failure_type` and the copilot's per-failure risk
questions both want a per-type score, not one blended "any failure" number.

Run via `make train`.
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.frozen import FrozenEstimator
from sklearn.inspection import permutation_importance
from sklearn.metrics import average_precision_score, precision_recall_curve, precision_score, recall_score

REPO_ROOT = Path(__file__).resolve().parents[5]
sys.path.insert(0, str(REPO_ROOT / "services" / "simulator" / "src"))
sys.path.insert(0, str(REPO_ROOT / "services" / "ml" / "src"))

from simulator.domain.failure import FailureType  # noqa: E402

from ml.domain import baseline  # noqa: E402
from ml.domain.lead_time import estimate_lead_days  # noqa: E402
from ml.infra.postgres import connect, set_tenant, tenant_id, vehicle_ids_by_vin, write_predictions  # noqa: E402

FEATURES_PATH = REPO_ROOT / "batch" / "spark" / "output" / "features.parquet"
REPORT_PATH = REPO_ROOT / "docs" / "evidence" / "ml" / "report.md"
TENANT_NAME = "demo"
# Score the fleet "as of" this many days before the end of the history, training only on what was
# knowable then. Planted failures all fall inside the backfill, so at the final day none is still
# ahead; an earlier snapshot has vehicles mid-ramp whose outcome we can check afterwards.
AS_OF_DAYS_BEFORE_END = 10

NUMERIC_FEATURE_COLUMNS = [
    "avg_coolant_c", "max_coolant_c", "avg_oil_kpa", "min_oil_kpa", "avg_rpm",
    "avg_load_pct", "avg_ambient_c", "avg_trans_c", "max_trans_c", "avg_fuel_rate_lph",
    "fast_samples", "min_charge_v", "avg_charge_v", "min_batt_12v_rest_v",
    "min_brake_pad_pct", "max_tyre_delta_kpa", "any_dtc_today", "max_cell_v_delta_mv",
    "min_soh_pct", "health_samples", "coolant_slope_7d", "oil_kpa_slope_7d",
    "charge_v_slope_7d", "brake_pad_slope_7d", "dtc_recurrence_7d", "max_tyre_delta_7d",
    # failures 6-8 (session 10b)
    "avg_speed_kmh", "rpm_per_speed_kmh", "min_tire_kpa", "max_tire_c", "max_cell_temp_c",
    "trans_c_slope_7d", "min_tire_kpa_slope_7d", "max_cell_temp_c_slope_7d",
]
VEHICLE_TYPE_DUMMIES = ["vt_ICE", "vt_EV", "vt_HYBRID"]
FEATURE_COLUMNS = NUMERIC_FEATURE_COLUMNS + VEHICLE_TYPE_DUMMIES

# PLAN §2 ML metrics: "recall at >=5 days' lead"
MIN_LEAD_DAYS = 5
# PLAN §2 ML metrics: "Rs saved (cost of breakdown vs inspection)" — rough
# POC estimates, not a costed study: a roadside breakdown (tow + lost use +
# emergency repair) vs a scheduled preventive inspection.
COST_BREAKDOWN_INR = 150_000
COST_INSPECTION_INR = 3_000
# The at-risk list reads one row per vehicle from these, so keep enough of the tail that the
# scores show a real spread instead of only the saturated top.
TOP_N_PREDICTIONS_WRITTEN = 5000
# Below this many positive/negative validation rows a sigmoid fit is noise; keep the raw model.
MIN_CALIBRATION_ROWS = 10


def _load_features() -> pd.DataFrame:
    df = pd.read_parquet(FEATURES_PATH)
    df["day"] = pd.to_datetime(df["day"])
    for c in NUMERIC_FEATURE_COLUMNS:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    for t in ("ICE", "EV", "HYBRID"):
        df[f"vt_{t}"] = (df["vehicle_type"] == t).astype(float)
    df["failure_type"] = df["failure_type"].fillna("")
    # NaT for vehicles with no planted failure; rows on/after failure were already dropped upstream.
    df["failure_day"] = df["day"] + pd.to_timedelta(df["days_to_failure"], unit="D")
    return df


def _resolve_as_of(df: pd.DataFrame) -> pd.Timestamp:
    override = os.environ.get("AS_OF_DATE")
    if override:
        return pd.Timestamp(override)
    return df["day"].max() - pd.Timedelta(days=AS_OF_DAYS_BEFORE_END)


def _time_split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    days = np.sort(df["day"].unique())
    n = len(days)
    train_cut = days[int(n * 0.70)]
    val_cut = days[int(n * 0.85)]
    train = df[df["day"] < train_cut]
    val = df[(df["day"] >= train_cut) & (df["day"] < val_cut)]
    test = df[df["day"] >= val_cut]
    return train, val, test


def _best_f1_threshold(y_val: np.ndarray, prob_val: np.ndarray) -> float:
    if y_val.sum() == 0:
        return 0.5
    precision, recall, thresholds = precision_recall_curve(y_val, prob_val)
    f1 = np.where((precision + recall) > 0, 2 * precision * recall / (precision + recall + 1e-12), 0.0)
    best_idx = int(np.argmax(f1[:-1])) if len(thresholds) else 0
    return float(thresholds[best_idx]) if len(thresholds) else 0.5


def _rupees_saved(y_true: np.ndarray, y_pred: np.ndarray) -> int:
    tp = int(((y_true == 1) & (y_pred == 1)).sum())
    fp = int(((y_true == 0) & (y_pred == 1)).sum())
    return tp * (COST_BREAKDOWN_INR - COST_INSPECTION_INR) - fp * COST_INSPECTION_INR


def main() -> None:
    load_dotenv(REPO_ROOT / ".env")
    full = _load_features()
    as_of = _resolve_as_of(full)
    # Only what was knowable at as_of: earlier days, and no vehicle whose failure is still in the
    # future (its pre-failure rows would otherwise be labelled with an outcome nobody knew yet).
    df = full[(full["day"] < as_of) & (full["failure_day"].isna() | (full["failure_day"] <= as_of))]
    train, val, test = _time_split(df)
    print(f"train.py: as-of {as_of.date()}, {len(df)} rows ({df['day'].min().date()}..{df['day'].max().date()}), "
          f"split train={len(train)} val={len(val)} test={len(test)}")

    X_train, X_val, X_test = train[FEATURE_COLUMNS], val[FEATURE_COLUMNS], test[FEATURE_COLUMNS]

    models: dict[str, object] = {}
    thresholds: dict[str, float] = {}
    report_lines: list[str] = []
    test_probs = pd.DataFrame(index=test.index)

    # Type-blind by construction (PLAN §2 baseline: "active DTC or threshold
    # breach"), so it's computed once, not per failure type.
    baseline_pred = test.apply(lambda row: baseline.predict(row.to_dict()), axis=1).to_numpy()

    for ftype in FailureType:
        name = ftype.value
        y_train = (train["failure_type"] == name).astype(int).to_numpy()
        y_val = (val["failure_type"] == name).astype(int).to_numpy()
        y_test = (test["failure_type"] == name).astype(int).to_numpy()

        # Shallow + regularised so clean synthetic signals can't push every score to ~1.0.
        model = HistGradientBoostingClassifier(
            random_state=42, max_depth=3, min_samples_leaf=100, l2_regularization=5.0,
            learning_rate=0.05, max_iter=300, early_stopping=True, validation_fraction=0.1,
            n_iter_no_change=15,
        )
        model.fit(X_train, y_train)
        # Platt-scale on the held-out validation split so a score reads as a probability.
        if y_val.sum() >= MIN_CALIBRATION_ROWS and (y_val == 0).sum() >= MIN_CALIBRATION_ROWS:
            model = CalibratedClassifierCV(FrozenEstimator(model), method="sigmoid").fit(X_val, y_val)
        models[name] = model

        prob_val = model.predict_proba(X_val)[:, 1]
        threshold = _best_f1_threshold(y_val, prob_val)
        thresholds[name] = threshold

        prob_test = model.predict_proba(X_test)[:, 1]
        test_probs[name] = prob_test
        pred_test = (prob_test >= threshold).astype(int)

        pr_auc = average_precision_score(y_test, prob_test) if y_test.sum() else float("nan")
        precision = precision_score(y_test, pred_test, zero_division=0)
        recall = recall_score(y_test, pred_test, zero_division=0)

        lead_mask = y_test.astype(bool) & (test["days_to_failure"].to_numpy() >= MIN_LEAD_DAYS)
        recall_at_lead = float(pred_test[lead_mask].mean()) if lead_mask.sum() else float("nan")

        baseline_precision = precision_score(y_test, baseline_pred, zero_division=0)
        baseline_recall = recall_score(y_test, baseline_pred, zero_division=0)

        n_train_pos, n_test_pos = int(y_train.sum()), int(y_test.sum())
        report_lines.append(
            f"| {name} | {n_train_pos} | {n_test_pos} | {pr_auc:.3f} | {precision:.3f} | {recall:.3f} "
            f"| {recall_at_lead:.3f} | {baseline_precision:.3f} | {baseline_recall:.3f} |"
        )
        print(f"  {name}: train_pos={n_train_pos} test_pos={n_test_pos} pr_auc={pr_auc:.3f} "
              f"model(p={precision:.3f} r={recall:.3f}) baseline(p={baseline_precision:.3f} r={baseline_recall:.3f})")

    # Fleet-wide risk = max across all 8 per-type models, for the "at-risk
    # list" business metrics (precision@100, Rs saved) — a fleet manager
    # cares about "which trucks", not "which trucks for cooling specifically".
    fleet_risk = test_probs.max(axis=1).to_numpy()
    fleet_true = test["any_failure_label"].to_numpy()
    fleet_pred = (test_probs.to_numpy() >= np.array([thresholds[f.value] for f in FailureType])).any(axis=1).astype(int)

    order = np.argsort(-fleet_risk)
    top100 = order[:100]
    precision_at_100 = float(fleet_true[top100].mean()) if len(top100) else float("nan")

    model_saved = _rupees_saved(fleet_true, fleet_pred)
    baseline_saved = _rupees_saved(fleet_true, baseline_pred)

    # Global permutation importance, on a capped sample for runtime, using
    # the failure type with the most test-set positives (most stable signal).
    busiest = max(FailureType, key=lambda f: int((test["failure_type"] == f.value).sum()))
    sample = test.sample(n=min(2000, len(test)), random_state=42)
    y_busiest = (sample["failure_type"] == busiest.value).astype(int)
    importance = permutation_importance(
        models[busiest.value], sample[FEATURE_COLUMNS], y_busiest, n_repeats=5, random_state=42, scoring="average_precision"
    )
    top_features = sorted(zip(FEATURE_COLUMNS, importance.importances_mean), key=lambda x: -x[1])[:10]

    print(f"fleet-wide: precision@100={precision_at_100:.3f} Rs_saved model={model_saved} baseline={baseline_saved}")

    snapshot = full[full["day"] == as_of]
    backtest = _backtest(snapshot, models)
    _write_report(df, train, val, test, report_lines, precision_at_100, model_saved, baseline_saved, top_features,
                  busiest.value, as_of, backtest)
    _score_and_write(snapshot, models, thresholds)


def _backtest(snapshot: pd.DataFrame, models: dict) -> dict:
    """Score the as-of snapshot, then compare with what actually happened afterwards."""
    probs = pd.DataFrame({name: m.predict_proba(snapshot[FEATURE_COLUMNS])[:, 1] for name, m in models.items()},
                         index=snapshot.index)
    fleet_risk = probs.max(axis=1)
    top_type = probs.idxmax(axis=1)
    will_fail = snapshot["days_to_failure"].notna()  # failure_day > as_of by construction
    k = int(will_fail.sum())
    top_k = fleet_risk.sort_values(ascending=False).index[:k]
    hit = will_fail.loc[top_k]
    out = {
        "n_snapshot": len(snapshot), "n_will_fail": k,
        "precision_at_k": float(hit.mean()) if k else float("nan"),
        "type_correct": float((top_type.loc[top_k][hit] == snapshot.loc[top_k][hit]["failure_type"]).mean())
        if hit.any() else float("nan"),
    }
    for cut in (0.5, 0.2):
        flagged = fleet_risk >= cut
        out[f"flagged_{cut}"] = int(flagged.sum())
        out[f"caught_{cut}"] = int((flagged & will_fail).sum())
    # Lead-time accuracy: the linear-extrapolation estimate vs the true days to failure.
    errs = []
    for idx in snapshot.index[will_fail]:
        row = snapshot.loc[idx]
        est = estimate_lead_days(row["failure_type"], row[NUMERIC_FEATURE_COLUMNS].to_dict())
        if est is not None:
            errs.append(abs(est - float(row["days_to_failure"])))
    out["lead_n"] = len(errs)
    out["lead_mae"] = float(np.mean(errs)) if errs else float("nan")
    return out


def _write_report(df, train, val, test, report_lines, precision_at_100, model_saved, baseline_saved, top_features, busiest, as_of, backtest) -> None:
    lines = [
        "# ML report — predictive maintenance (PLAN §6.3 session 5)",
        "",
        f"Generated {datetime.now(timezone.utc).isoformat()}",
        "",
        f"- Dataset: {len(df)} vin-days, {df['vin'].nunique()} vehicles, "
        f"{df['day'].min().date()} to {df['day'].max().date()}.",
        f"- Time-based split: train={len(train)} rows (< {train['day'].max().date() if len(train) else '-'}), "
        f"val={len(val)}, test={len(test)} (>= {test['day'].min().date() if len(test) else '-'}).",
        "- Model: `sklearn.ensemble.HistGradientBoostingClassifier`, one per failure type (1-8), "
        "trained on this failure type's positives vs everything else.",
        "- Baseline: active DTC or threshold breach (`services/ml/src/ml/domain/baseline.py`) — "
        "the same cutoffs as the real-time Flink rules, so it has ~0 lead time by construction.",
        "",
        "## Per-failure-type metrics (test set)",
        "",
        "| failure_type | train positives | test positives | PR-AUC | model precision | model recall "
        "| recall @ >=5d lead | baseline precision | baseline recall |",
        "|---|---|---|---|---|---|---|---|---|",
        *report_lines,
        "",
        "## Fleet-wide (\"at-risk list\") metrics",
        "",
        f"- precision@100 (top 100 highest-risk vehicle-days by max per-type risk score): {precision_at_100:.3f}",
        f"- Rs saved on the test window, model: Rs {model_saved:,}",
        f"- Rs saved on the test window, baseline: Rs {baseline_saved:,}",
        f"  (tp x (breakdown Rs{COST_BREAKDOWN_INR:,} - inspection Rs{COST_INSPECTION_INR:,}) - fp x inspection cost; "
        "a rough POC estimate, not a costed study.)",
        "",
        f"## Backtest: fleet scored as of {as_of.date()} vs what actually happened",
        "",
        f"The model is trained only on data before {as_of.date()}, then scores every vehicle's "
        f"{as_of.date()} snapshot. All planted failures fall inside the 30-day backfill, so the outcome is known.",
        "",
        f"- Vehicles scored: {backtest['n_snapshot']}; of those, {backtest['n_will_fail']} really failed afterwards.",
        f"- Precision in the top {backtest['n_will_fail']} by risk: {backtest['precision_at_k']:.3f}"
        f" (right failure type among the hits: {backtest['type_correct']:.3f}).",
        f"- Risk >= 0.5: {backtest['flagged_0.5']} flagged, {backtest['caught_0.5']} truly failed. "
        f"Risk >= 0.2: {backtest['flagged_0.2']} flagged, {backtest['caught_0.2']} truly failed.",
        f"- Lead-time estimate error (days, {backtest['lead_n']} vehicles with an estimate): "
        f"mean absolute error {backtest['lead_mae']:.1f}.",
        "- Horizon is at most ~10 days: every planted failure sits inside the 30-day backfill, so no vehicle "
        "has a failure further ahead than the end of the history. A true 30-day horizon needs a longer simulation.",
        "",
        f"## Top permutation-importance features (`{busiest}` model, PR-AUC scoring)",
        "",
        "| feature | importance |",
        "|---|---|",
        *[f"| {f} | {v:.4f} |" for f, v in top_features],
        "",
        "## Known limitations / trimmed scope",
        "",
        "- Explanations are global permutation importance, not per-vehicle SHAP — "
        "avoids adding a `shap` dependency for a POC; per-vehicle \"why\" is left to the "
        "copilot's nearest-neighbour lookup against `failure_signature` (session 8), using "
        "each prediction's stored `feature_vector`.",
        "- Embeddings for the pgvector DTC KB use a deterministic hashing trick, not a "
        "sentence-transformer model — see `services/ml/src/ml/domain/embeddings.py` docstring.",
        "- The baseline is type-blind (it flags \"something's wrong\", not which of the 8 "
        "failures) — its per-type precision/recall above is measured against that type's "
        "labels anyway, which understates it slightly; the fleet-wide numbers are the fair "
        "comparison.",
        "- Training data is synthetic (`db/timescale/backfill_history.py`), not the Scania "
        "validation set (parked per PLAN's decisions).",
        f"- This report's backfill window has only {int(df['any_failure_label'].sum())} positive "
        "vin-days before the as-of date, across all 8 failure types, so per-type metrics are noisy "
        "(ev_battery especially). The backfill covers 11,006 of the planned 20,000 vehicles: the run "
        "was stopped for disk space (~57 GB more needed).",
        "- Failures 6-8 (tyre, transmission, EV HV battery — session 10b) are verified end-to-end "
        "through this batch/ML path (backfill -> Spark features -> training -> scored predictions, "
        "same as 1-5) and through their real-time Flink rules, all three confirmed firing live.",
        "",
    ]
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")
    print(f"report -> {REPORT_PATH}")


def _score_and_write(snapshot: pd.DataFrame, models: dict, thresholds: dict) -> None:
    latest = snapshot
    X_latest = latest[FEATURE_COLUMNS]

    model_version = f"hgb-v3-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    scored: list[dict] = []
    feature_rows = latest[NUMERIC_FEATURE_COLUMNS].to_dict("records")
    for ftype, model in models.items():
        prob = model.predict_proba(X_latest)[:, 1]
        for vin, p, feat_row, feature_row in zip(latest["vin"], prob, X_latest.to_numpy(), feature_rows):
            if p < 0.01:
                continue
            vec = feat_row.tolist() + [0.0] * (384 - len(feat_row))
            scored.append({
                "vin": vin, "failure_type": ftype, "risk_score": round(float(p), 5),
                "lead_days": estimate_lead_days(ftype, feature_row),
                "model_version": model_version, "feature_vector": vec,
            })

    scored.sort(key=lambda r: -r["risk_score"])
    scored = scored[:TOP_N_PREDICTIONS_WRITTEN]

    conn = connect()
    try:
        tid = tenant_id(conn, TENANT_NAME)
        set_tenant(conn, tid)
        vids = vehicle_ids_by_vin(conn, TENANT_NAME)
        rows = [{**r, "vehicle_id": vids[r["vin"]]} for r in scored if r["vin"] in vids]
        n = write_predictions(conn, tid, rows)
    finally:
        conn.close()
    print(f"scored {len(scored)} (vin, failure_type) pairs, wrote {n} predictions (model_version={model_version})")


if __name__ == "__main__":
    main()
