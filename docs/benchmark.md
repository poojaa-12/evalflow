# Benchmark

Bench stays out of CI. One command reproduces the numbers below. Do not replace them with a guessed speedup.

## Method

Implemented inside `evalflow bench`:

1. Start from a fresh cache. Run `configs/v1.yaml` once to populate it.
2. For each of 3 repeats, copy that cache, time one incremental `configs/v2.yaml` run, and time one v2 run with the cache disabled.
3. Repeats do not reuse a cache that already holds v2 keys. A later repeat would otherwise become all hits.
4. Print the median wall clock for the naive run and the incremental run, the incremental hit rate, and speedup defined as median naive / median incremental.

Wall clock is the run header's `wall_clock_s`: end to end, including cache lookups. The copy of the seed cache is outside that timer.

`--cost-s` defaults to `0.1`. Each miss sleeps that long inside the worker, so the sleep dominates process-pool startup on this suite. Tests call the runner with `cost_s=0` and do not run the bench.

## Command

```bash
uv run evalflow bench --model configs/v2.yaml --baseline-model configs/v1.yaml --scenarios scenarios/ --workers 4 --repeats 3
```

## Results

Copied from the command output:

```
scenarios: 200
workers: 4
repeats: 3
cost_s: 0.1
warmup_baseline_s: 5.5369
naive_s: 5.4697 5.4764 5.4991
incremental_s: 2.2466 2.2991 2.2846
median_naive_s: 5.4764
median_incremental_s: 2.2846
incremental_hits: 130
incremental_misses: 70
incremental_hit_rate_repeats: 0.6500 0.6500 0.6500
incremental_hit_rate: 0.6500
speedup: 2.3971
```

Median naive wall clock is 5.4764 s. Median incremental wall clock is 2.2846 s. The incremental run hit 130 of 200 scenarios (hit rate 0.6500) on every repeat. Speedup is 2.3971.
