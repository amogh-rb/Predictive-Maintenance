# ML report — predictive maintenance (PLAN §6.3 session 5)

Generated 2026-09-28T14:37:47.633517+00:00

- Dataset: 25920 vin-days, 1199 vehicles, 2026-09-07 to 2026-09-28.
- Time-based split: train=17755 rows (< 2026-09-21), val=3506, test=4659 (>= 2026-09-25).
- Model: `sklearn.ensemble.HistGradientBoostingClassifier`, one per Must-failure type (1-5), trained on this failure type's positives vs everything else.
- Baseline: active DTC or threshold breach (`services/ml/src/ml/domain/baseline.py`) — the same cutoffs as the real-time Flink rules, so it has ~0 lead time by construction.

## Per-failure-type metrics (test set)

| failure_type | train positives | test positives | PR-AUC | model precision | model recall | recall @ >=5d lead | baseline precision | baseline recall |
|---|---|---|---|---|---|---|---|---|
| cooling | 88 | 2 | 0.080 | 0.080 | 1.000 | nan | 0.002 | 1.000 |
| lubrication | 64 | 0 | nan | 0.000 | 0.000 | nan | 0.000 | 0.000 |
| battery | 63 | 4 | 1.000 | 1.000 | 1.000 | nan | 0.005 | 1.000 |
| misfire | 40 | 0 | nan | 0.000 | 0.000 | nan | 0.000 | 0.000 |
| brake_wear | 55 | 1 | 0.000 | 0.000 | 1.000 | nan | 0.001 | 1.000 |

## Fleet-wide ("at-risk list") metrics

- precision@100 (top 100 highest-risk vehicle-days by max per-type risk score): 0.060
- Rs saved on the test window, model: Rs -12,900,000
- Rs saved on the test window, baseline: Rs -1,548,000
  (tp x (breakdown Rs150,000 - inspection Rs3,000) - fp x inspection cost; a rough POC estimate, not a costed study.)

## Top permutation-importance features (`battery` model, PR-AUC scoring)

| feature | importance |
|---|---|
| avg_coolant_c | 0.0000 |
| max_coolant_c | 0.0000 |
| avg_oil_kpa | 0.0000 |
| min_oil_kpa | 0.0000 |
| avg_rpm | 0.0000 |
| avg_load_pct | 0.0000 |
| avg_ambient_c | 0.0000 |
| avg_trans_c | 0.0000 |
| max_trans_c | 0.0000 |
| avg_fuel_rate_lph | 0.0000 |

## Known limitations / trimmed scope

- Explanations are global permutation importance, not per-vehicle SHAP — avoids adding a `shap` dependency for a POC; per-vehicle "why" is left to the copilot's nearest-neighbour lookup against `failure_signature` (session 8), using each prediction's stored `feature_vector`.
- Embeddings for the pgvector DTC KB use a deterministic hashing trick, not a sentence-transformer model — see `services/ml/src/ml/domain/embeddings.py` docstring.
- The baseline is type-blind (it flags "something's wrong", not which of the 5 failures) — its per-type precision/recall above is measured against that type's labels anyway, which understates it slightly; the fleet-wide numbers are the fair comparison.
- Training data is synthetic (`db/timescale/backfill_history.py`), not the Scania validation set (parked per PLAN's decisions).
- This report's backfill window has only 200 total positive vin-days across all 5 failure types — enough to prove the pipeline end-to-end, not enough for stable per-type metrics (0-4 test positives per type here). PLAN §6.3 session 5's real dataset is the overnight run (`make backfill VEHICLES=20000 DAYS=30`); rerun `make batch && make train` afterward to regenerate this report against it.
