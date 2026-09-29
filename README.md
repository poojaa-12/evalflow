# Evalflow

Synthetic incremental evaluation runner. This prototype is not a Nuro system and not a real autonomy stack. The evaluator is a deterministic stand-in, not a vehicle and not a real autonomy stack.

A scenario depends on a subset of model components. The cache key hashes the evaluator version, the scenario, and only those components. Changing the planner recomputes planner-dependent scenarios and leaves the rest as cache hits. `compare` turns two run files into one HTML page.

## Dashboard

Live page: https://evalflow-demo.vercel.app

Project write-up (architecture, what, how, why, and why this is the fit): https://evalflow-demo.vercel.app/project.html

It shows the component diff, the cache-key preimage, which dependency groups invalidate, and every scenario row from the measured runs. Regenerate the static file after a new pair of runs:

```bash
uv run evalflow dashboard \
  --baseline runs/v1.jsonl \
  --candidate runs/v2.jsonl \
  --baseline-model configs/v1.yaml \
  --model configs/v2.yaml \
  --scenarios scenarios/ \
  --bench docs/bench.json \
  --out dashboard/index.html
```

`dashboard/index.html` and `dashboard/project.html` are static files. `vercel.json` publishes that directory on the connected Vercel project, with no install and no build. A push to `main` updates the production site.

## Quickstart

Install, then run the conservative model, the planner edit, and the report:

```bash
uv sync
uv run evalflow run --model configs/v1.yaml --scenarios scenarios/ --workers 8 --out runs/v1.jsonl
uv run evalflow run --model configs/v2.yaml --scenarios scenarios/ --workers 8 --out runs/v2.jsonl
uv run evalflow compare runs/v1.jsonl runs/v2.jsonl --out report.html
```

The fourth command is the bench. It is not part of CI. The numbers in [Benchmark](#benchmark) are copied from its output.

```bash
uv run evalflow bench --model configs/v2.yaml --baseline-model configs/v1.yaml --scenarios scenarios/ --workers 4 --repeats 3
```

Default `--cost-s` is `0.1`, so the simulated eval sleep dominates process-pool startup. Regenerate the committed suite with:

```bash
uv run evalflow generate --out scenarios/ --count 200 --seed 0
```

## What the suite does

`scenarios/` is the generated YAML, grouped by category (`night-001` and so on). The dependency mix is:

| depends_on | scenarios |
| --- | ---: |
| perception | 120 |
| planner | 40 |
| perception + planner | 20 |
| prediction | 10 |
| planner + prediction | 10 |

A planner-only edit invalidates 70 of 200. Perception-only and prediction-only stay hits, and their metrics stay the same. `configs/v2.yaml` lowers planner conservatism only. Planner-dependent scenarios move `min_distance_m` down and `jerk` up. A few `unprotected_left` cases flip from pass to fail.

## Benchmark

Method and command: [docs/benchmark.md](docs/benchmark.md). Figures below are the medians printed by the bench command, not estimates.

| | |
| --- | ---: |
| scenarios | 200 |
| workers | 4 |
| repeats | 3 |
| cost_s | 0.1 |
| median naive wall clock | 5.4764 s |
| median incremental wall clock | 2.2846 s |
| incremental hit rate | 0.6500 (130 hits, 70 misses) |
| speedup (median naive / median incremental) | 2.3971 |

Repeat samples from that run: naive `5.4697 5.4764 5.4991`, incremental `2.2466 2.2991 2.2846`. Hit rate was `0.6500` on every repeat.

## Layout

- `src/evalflow/` — models, generator, synthetic evaluator, cache, runner, compare, report, CLI
- `configs/v1.yaml`, `configs/v2.yaml` — same components; v2 changes only the planner
- `scenarios/` — committed generated YAML
- `tests/` — cache key, cache hit, comparator, runner failure and corrupt cache, CLI report
- `docs/architecture.md`, `docs/benchmark.md`, `docs/video-script.md`

Out of scope: Ray, Parquet, bootstrap confidence intervals, and `--watch`.

## Checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy src/evalflow
uv run pytest
```
