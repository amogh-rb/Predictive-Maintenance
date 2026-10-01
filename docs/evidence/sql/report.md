# EXPLAIN ANALYZE — before / after (PLAN §2 SQL optimisation)

## 1. At-risk vehicle list

**Before** (OFFSET pagination directly over the raw, ever-growing `prediction` table — the N+1 "latest prediction per vehicle" lookup this replaced can't even be expressed as a single plan, so this shows just the listing half of it):

```
Limit  (cost=88.29..88.34 rows=20 width=30) (actual time=0.563..0.565 rows=20 loops=1)
  Buffers: shared hit=76
  ->  Sort  (cost=88.04..88.76 rows=289 width=30) (actual time=0.557..0.561 rows=120 loops=1)
        Sort Key: risk_score DESC
        Sort Method: top-N heapsort  Memory: 37kB
        Buffers: shared hit=76
        ->  Seq Scan on prediction  (cost=0.00..76.61 rows=289 width=30) (actual time=0.007..0.415 rows=289 loops=1)
              Filter: (tenant_id = '6fce1e9a-406c-4a3d-92d6-076de1e80b5e'::uuid)
              Buffers: shared hit=73
Planning:
  Buffers: shared hit=103
Planning Time: 0.259 ms
Execution Time: 0.817 ms
```

**After** (migration 007's `vehicle_latest_risk` materialized view + composite index, keyset — no OFFSET, no per-row lookup):

```
Limit  (cost=0.14..2.86 rows=20 width=30) (actual time=0.435..0.441 rows=20 loops=1)
  Buffers: shared hit=2 read=1
  ->  Index Scan using idx_vehicle_latest_risk_keyset on vehicle_latest_risk  (cost=0.14..16.57 rows=121 width=30) (actual time=0.434..0.439 rows=20 loops=1)
        Index Cond: (tenant_id = '6fce1e9a-406c-4a3d-92d6-076de1e80b5e'::uuid)
        Buffers: shared hit=2 read=1
Planning:
  Buffers: shared hit=59
Planning Time: 0.102 ms
Execution Time: 0.448 ms
```

## 2. Open alerts per fleet

**Before** (same query, migration 007's partial index disabled for this plan):

```
Limit  (cost=82.52..82.65 rows=50 width=51) (actual time=5.317..5.322 rows=50 loops=1)
  Buffers: shared hit=27
  ->  Sort  (cost=82.52..85.72 rows=1280 width=51) (actual time=5.317..5.319 rows=50 loops=1)
        Sort Key: opened_at DESC
        Sort Method: top-N heapsort  Memory: 36kB
        Buffers: shared hit=27
        ->  Seq Scan on alert  (cost=0.00..40.00 rows=1280 width=51) (actual time=0.008..5.092 rows=1210 loops=1)
              Filter: ((closed_at IS NULL) AND (tenant_id = '6fce1e9a-406c-4a3d-92d6-076de1e80b5e'::uuid))
              Rows Removed by Filter: 82
              Buffers: shared hit=24
Planning:
  Buffers: shared hit=89
Planning Time: 0.397 ms
Execution Time: 5.333 ms
```

**After** (`idx_alert_open_by_tenant` partial index, WHERE closed_at IS NULL):

```
Limit  (cost=0.28..4.17 rows=50 width=51) (actual time=0.009..0.032 rows=50 loops=1)
  Buffers: shared hit=4
  ->  Index Scan using idx_alert_open_by_tenant on alert  (cost=0.28..99.86 rows=1280 width=51) (actual time=0.009..0.030 rows=50 loops=1)
        Index Cond: (tenant_id = '6fce1e9a-406c-4a3d-92d6-076de1e80b5e'::uuid)
        Buffers: shared hit=4
Planning Time: 0.039 ms
Execution Time: 0.040 ms
```

## 3. Fleet daily summary

**Before** (raw GROUP BY over the `telemetry_fast` hypertable, every query):

```
Limit  (cost=12005.66..12019.07 rows=50 width=42) (actual time=43.004..47.517 rows=50 loops=1)
  Buffers: shared hit=5682
  ->  Finalize GroupAggregate  (cost=12005.66..17582.23 rows=20781 width=42) (actual time=43.002..47.507 rows=50 loops=1)
        Group Key: (time_bucket('1 day'::interval, _hyper_1_192_chunk.ts)), _hyper_1_192_chunk.vin
        Buffers: shared hit=5682
        ->  Gather Merge  (cost=12005.66..16854.90 rows=41562 width=66) (actual time=42.993..47.465 rows=58 loops=1)
              Workers Planned: 2
              Workers Launched: 2
              Buffers: shared hit=5682
              ->  Sort  (cost=11005.63..11057.59 rows=20781 width=66) (actual time=38.919..38.937 rows=403 loops=3)
                    Sort Key: (time_bucket('1 day'::interval, _hyper_1_192_chunk.ts)) DESC, _hyper_1_192_chunk.vin
                    Sort Method: quicksort  Memory: 127kB
                    Buffers: shared hit=5682
                    Worker 0:  Sort Method: quicksort  Memory: 134kB
                    Worker 1:  Sort Method: quicksort  Memory: 107kB
                    ->  Partial HashAggregate  (cost=9255.56..9515.33 rows=20781 width=66) (actual time=37.452..37.752 rows=911 loops=3)
                          Group Key: time_bucket('1 day'::interval, _hyper_1_192_chunk.ts), _hyper_1_192_chunk.vin
                          Batches: 1  Memory Usage: 1041kB
                          Buffers: shared hit=5652
                          Worker 0:  Batches: 1  Memory Usage: 1041kB
                          Worker 1:  Batches: 1  Memory Usage: 1041kB
                          ->  Result  (cost=0.00..8389.68 rows=86588 width=34) (actual time=0.006..23.617 rows=69273 loops=3)
                                Buffers: shared hit=5652
                                ->  Parallel Append  (cost=0.00..7307.33 rows=86588 width=34) (actual time=0.005..17.602 rows=69273 loops=3)
                                      Buffers: shared hit=5652
                                      ->  Parallel Seq Scan on _hyper_1_192_chunk  (cost=0.00..919.38 rows=16338 width=34) (actual time=0.005..6.046 rows=27775 loops=1)
                                            Buffers: shared hit=756
                                      ->  Parallel Seq Scan on _hyper_1_194_chunk  (cost=0.00..911.61 rows=16061 width=34) (actual time=0.005..6.049 rows=27317 loops=1)
                                            Buffers: shared hit=751
                                      ->  Parallel Seq Scan on _hyper_1_201_chunk  (cost=0.00..901.11 rows=16111 width=34) (actual time=0.005..5.461 rows=27388 loops=1)
                                            Buffers: shared hit=740
                                      ->  Parallel Seq Scan on _hyper_1_196_chunk  (cost=0.00..877.88 rows=15588 width=34) (actual time=0.006..5.295 rows=26499 loops=1)
                                            Buffers: shared hit=722
                                      ->  Parallel Seq Scan on _hyper_1_199_chunk  (cost=0.00..836.85 rows=14985 width=34) (actual time=0.003..1.776 rows=8491 loops=3)
                                            Buffers: shared hit=687
                                      ->  Parallel Seq Scan on _hyper_1_205_chunk  (cost=0.00..833.78 rows=14878 width=34) (actual time=0.003..2.533 rows=12646 loops=2)
                                            Buffers: shared hit=685
                                      ->  Parallel Seq Scan on _hyper_1_198_chunk  (cost=0.00..815.16 rows=14416 width=34) (actual time=0.002..4.674 rows=24507 loops=1)
                                            Buffers: shared hit=671
                                      ->  Parallel Seq Scan on _hyper_1_203_chunk  (cost=0.00..778.64 rows=13864 width=34) (actual time=0.004..5.371 rows=23568 loops=1)
                                            Buffers: shared hit=640
Planning:
  Buffers: shared hit=1460
Planning Time: 5.298 ms
Execution Time: 47.972 ms
```

**After** (`telemetry_fast_daily` continuous aggregate, pre-computed):

```
Limit  (cost=0.28..2.50 rows=50 width=42) (actual time=0.020..0.029 rows=50 loops=1)
  Buffers: shared hit=3
  ->  Index Scan using _hyper_5_77_chunk__materialized_hypertable_5_day_idx on _hyper_5_77_chunk  (cost=0.28..89.28 rows=2000 width=42) (actual time=0.019..0.026 rows=50 loops=1)
        Buffers: shared hit=3
Planning:
  Buffers: shared hit=152 dirtied=2
Planning Time: 0.878 ms
Execution Time: 0.056 ms
```
