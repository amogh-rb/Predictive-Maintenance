# ML report — predictive maintenance (PLAN §6.3 session 5)

Generated 2026-10-01T10:14:03.115920+00:00

- Dataset: 215448 vin-days, 10886 vehicles, 2026-08-30 to 2026-09-18.
- Time-based split: train=151333 rows (< 2026-09-12), val=32107, test=32008 (>= 2026-09-16).
- Model: `sklearn.ensemble.HistGradientBoostingClassifier`, one per failure type (1-8), trained on this failure type's positives vs everything else.
- Baseline: active DTC or threshold breach (`services/ml/src/ml/domain/baseline.py`) — the same cutoffs as the real-time Flink rules, so it has ~0 lead time by construction.

## Per-failure-type metrics (test set)

| failure_type | train positives | test positives | PR-AUC | model precision | model recall | recall @ >=5d lead | baseline precision | baseline recall |
|---|---|---|---|---|---|---|---|---|
| cooling | 276 | 8 | 1.000 | 1.000 | 1.000 | nan | 0.001 | 1.000 |
| lubrication | 372 | 13 | 0.923 | 1.000 | 0.923 | nan | 0.002 | 0.923 |
| battery | 411 | 15 | 1.000 | 1.000 | 1.000 | nan | 0.002 | 1.000 |
| misfire | 185 | 5 | 0.794 | 0.571 | 0.800 | nan | 0.001 | 1.000 |
| brake_wear | 257 | 2 | 1.000 | 0.105 | 1.000 | nan | 0.000 | 1.000 |
| tyre | 258 | 4 | 1.000 | 1.000 | 1.000 | nan | 0.001 | 1.000 |
| transmission | 235 | 2 | 1.000 | 1.000 | 0.500 | nan | 0.000 | 1.000 |
| ev_battery | 211 | 3 | 1.000 | 1.000 | 1.000 | nan | 0.000 | 1.000 |

## Fleet-wide ("at-risk list") metrics

- precision@100 (top 100 highest-risk vehicle-days by max per-type risk score): 0.510
- Rs saved on the test window, model: Rs 7,143,000
- Rs saved on the test window, baseline: Rs -10,926,000
  (tp x (breakdown Rs150,000 - inspection Rs3,000) - fp x inspection cost; a rough POC estimate, not a costed study.)

## Backtest: fleet scored as of 2026-09-19 vs what actually happened

The model is trained only on data before 2026-09-19, then scores every vehicle's 2026-09-19 snapshot. All planted failures fall inside the 30-day backfill, so the outcome is known.

- Vehicles scored: 10765; of those, 113 really failed afterwards.
- Precision in the top 113 by risk: 0.628 (right failure type among the hits: 1.000).
- Risk >= 0.5: 61 flagged, 61 truly failed. Risk >= 0.2: 69 flagged, 66 truly failed.
- Lead-time estimate error (days, 39 vehicles with an estimate): mean absolute error 4.6.
- Horizon is at most ~10 days: every planted failure sits inside the 30-day backfill, so no vehicle has a failure further ahead than the end of the history. A true 30-day horizon needs a longer simulation.

## Top permutation-importance features (`battery` model, PR-AUC scoring)

| feature | importance |
|---|---|
| min_charge_v | 0.5044 |
| avg_coolant_c | 0.0000 |
| max_coolant_c | 0.0000 |
| avg_oil_kpa | 0.0000 |
| min_oil_kpa | 0.0000 |
| avg_rpm | 0.0000 |
| avg_load_pct | 0.0000 |
| avg_ambient_c | 0.0000 |
| avg_trans_c | 0.0000 |
| max_trans_c | 0.0000 |

## Known limitations / trimmed scope

- Explanations are global permutation importance, not per-vehicle SHAP — avoids adding a `shap` dependency for a POC; per-vehicle "why" is left to the copilot's nearest-neighbour lookup against `failure_signature` (session 8), using each prediction's stored `feature_vector`.
- Embeddings for the pgvector DTC KB use a deterministic hashing trick, not a sentence-transformer model — see `services/ml/src/ml/domain/embeddings.py` docstring.
- The baseline is type-blind (it flags "something's wrong", not which of the 8 failures) — its per-type precision/recall above is measured against that type's labels anyway, which understates it slightly; the fleet-wide numbers are the fair comparison.
- Training data is synthetic (`db/timescale/backfill_history.py`), not the Scania validation set (parked per PLAN's decisions).
- This report's backfill window has only 1407 positive vin-days before the as-of date, across all 8 failure types, so per-type metrics are noisy (ev_battery especially). The backfill covers 11,006 of the planned 20,000 vehicles: the run was stopped for disk space (~57 GB more needed).
- Failures 6-8 (tyre, transmission, EV HV battery — session 10b) are verified end-to-end through this batch/ML path (backfill -> Spark features -> training -> scored predictions, same as 1-5) and through their real-time Flink rules, all three confirmed firing live.
