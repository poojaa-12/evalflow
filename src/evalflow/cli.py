"""Command line for generate, run, compare, and bench."""

from __future__ import annotations

import json
import logging
import shutil
import statistics
import tempfile
from pathlib import Path
from typing import Annotated, Any

import typer

from evalflow.compare import DEFAULT_DISTANCE_TOL, DEFAULT_JERK_TOL, compare_runs
from evalflow.dashboard import render_dashboard
from evalflow.generate import generate_scenarios, load_scenarios, write_scenarios
from evalflow.models import RunFile, load_model
from evalflow.report import render_report
from evalflow.runner import run

# Sleep dominates process-pool startup on the bench below. Tests pass cost_s=0.
DEFAULT_COST_S = 0.1

app = typer.Typer(add_completion=False, no_args_is_help=True)


def _configure_logging() -> None:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s: %(message)s")


@app.command("generate")
def generate_cmd(
    out: Annotated[Path, typer.Option("--out")] = Path("scenarios"),
    count: Annotated[int, typer.Option("--count")] = 200,
    seed: Annotated[int, typer.Option("--seed")] = 0,
) -> None:
    """Write a deterministic scenario suite grouped by category."""

    _configure_logging()
    try:
        scenarios = generate_scenarios(count, seed)
    except ValueError as exc:
        raise typer.BadParameter(str(exc)) from exc
    write_scenarios(scenarios, out)
    typer.echo(f"wrote {len(scenarios)} scenarios to {out}")


@app.command("run")
def run_cmd(
    model: Annotated[Path, typer.Option("--model", exists=True, dir_okay=False, readable=True)],
    scenarios: Annotated[Path, typer.Option("--scenarios", exists=True)],
    workers: Annotated[int, typer.Option("--workers")] = 8,
    out: Annotated[Path, typer.Option("--out")] = Path("runs/run.jsonl"),
    cache_dir: Annotated[Path, typer.Option("--cache-dir")] = Path(".cache/evalflow"),
    cache: Annotated[bool, typer.Option("--cache/--no-cache")] = True,
    cost_s: Annotated[float, typer.Option("--cost-s")] = DEFAULT_COST_S,
    baseline: Annotated[Path | None, typer.Option("--baseline")] = None,
    report: Annotated[Path, typer.Option("--report")] = Path("report.html"),
) -> None:
    """Evaluate a scenario suite. Exits non-zero if any scenario errored."""

    _configure_logging()
    if workers < 1:
        raise typer.BadParameter("workers must be >= 1")
    if cost_s < 0:
        raise typer.BadParameter("cost_s must be >= 0")
    if baseline is not None and not baseline.is_file():
        raise typer.BadParameter(f"baseline not found: {baseline}")

    result = run(
        load_model(model),
        load_scenarios(scenarios),
        workers,
        cache_dir,
        cache,
        cost_s,
    )
    result.write_jsonl(out)
    header = result.header
    typer.echo(
        f"wrote {out}: hits={header.hits} misses={header.misses} "
        f"wall_clock_s={header.wall_clock_s:.3f}"
    )
    errors = [record for record in result.records if record.error]
    if errors:
        typer.echo(f"{len(errors)} scenario(s) failed", err=True)
        raise typer.Exit(code=1)
    if baseline is not None:
        comparison = compare_runs(RunFile.read_jsonl(baseline), result)
        render_report(comparison, report)
        typer.echo(
            f"regressions={comparison.regressions} improvements={comparison.improvements} "
            f"unchanged={comparison.unchanged} -> {report}"
        )


@app.command("compare")
def compare_cmd(
    baseline: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    candidate: Annotated[Path, typer.Argument(exists=True, dir_okay=False, readable=True)],
    out: Annotated[Path, typer.Option("--out")] = Path("report.html"),
    distance_tol: Annotated[float, typer.Option("--distance-tol")] = DEFAULT_DISTANCE_TOL,
    jerk_tol: Annotated[float, typer.Option("--jerk-tol")] = DEFAULT_JERK_TOL,
) -> None:
    """Turn two run files into one HTML page."""

    _configure_logging()
    comparison = compare_runs(
        RunFile.read_jsonl(baseline),
        RunFile.read_jsonl(candidate),
        distance_tol=distance_tol,
        jerk_tol=jerk_tol,
    )
    render_report(comparison, out)
    typer.echo(
        f"regressions={comparison.regressions} improvements={comparison.improvements} "
        f"unchanged={comparison.unchanged} -> {out}"
    )


@app.command("bench")
def bench_cmd(
    model: Annotated[Path, typer.Option("--model", exists=True, dir_okay=False, readable=True)],
    baseline_model: Annotated[
        Path,
        typer.Option("--baseline-model", exists=True, dir_okay=False, readable=True),
    ],
    scenarios: Annotated[Path, typer.Option("--scenarios", exists=True)],
    workers: Annotated[int, typer.Option("--workers")] = 4,
    repeats: Annotated[int, typer.Option("--repeats")] = 3,
    cost_s: Annotated[float, typer.Option("--cost-s")] = DEFAULT_COST_S,
) -> None:
    """Time a cached incremental run against a cache-disabled run.

    Starts from a fresh cache, populates it with the baseline model, then for
    each repeat copies that cache and times one incremental candidate run plus
    one candidate run with the cache disabled. Repeats do not reuse a cache
    that already holds candidate keys.
    """

    _configure_logging()
    if workers < 1 or repeats < 1:
        raise typer.BadParameter("workers and repeats must be >= 1")
    if cost_s < 0:
        raise typer.BadParameter("cost_s must be >= 0")

    loaded = load_scenarios(scenarios)
    baseline = load_model(baseline_model)
    candidate = load_model(model)
    naive_times: list[float] = []
    incremental_times: list[float] = []
    hit_rates: list[float] = []
    hit_counts: list[int] = []
    miss_counts: list[int] = []

    with tempfile.TemporaryDirectory(prefix="evalflow-bench-") as temporary:
        root = Path(temporary)
        seed_cache = root / "seed"
        seed_cache.mkdir()
        warmup = run(baseline, loaded, workers, seed_cache, True, cost_s)
        for index in range(repeats):
            incremental_cache = root / f"incremental-{index}"
            shutil.copytree(seed_cache, incremental_cache)
            incremental = run(candidate, loaded, workers, incremental_cache, True, cost_s)
            incremental_times.append(incremental.header.wall_clock_s)
            total = incremental.header.hits + incremental.header.misses
            hit_rates.append(0.0 if total == 0 else incremental.header.hits / total)
            hit_counts.append(incremental.header.hits)
            miss_counts.append(incremental.header.misses)
            naive = run(
                candidate,
                loaded,
                workers,
                root / f"naive-{index}",
                False,
                cost_s,
            )
            naive_times.append(naive.header.wall_clock_s)
        warmup_s = warmup.header.wall_clock_s

    median_naive = float(statistics.median(naive_times))
    median_incremental = float(statistics.median(incremental_times))
    if median_incremental <= 0:
        raise typer.BadParameter("incremental median wall clock was 0")
    median_hit_rate = float(statistics.median(hit_rates))
    speedup = median_naive / median_incremental

    typer.echo(f"scenarios: {len(loaded)}")
    typer.echo(f"workers: {workers}")
    typer.echo(f"repeats: {repeats}")
    typer.echo(f"cost_s: {cost_s}")
    typer.echo(f"warmup_baseline_s: {warmup_s:.4f}")
    typer.echo("naive_s: " + " ".join(f"{value:.4f}" for value in naive_times))
    typer.echo("incremental_s: " + " ".join(f"{value:.4f}" for value in incremental_times))
    typer.echo(f"median_naive_s: {median_naive:.4f}")
    typer.echo(f"median_incremental_s: {median_incremental:.4f}")
    typer.echo(f"incremental_hits: {hit_counts[0]}")
    typer.echo(f"incremental_misses: {miss_counts[0]}")
    typer.echo("incremental_hit_rate_repeats: " + " ".join(f"{value:.4f}" for value in hit_rates))
    typer.echo(f"incremental_hit_rate: {median_hit_rate:.4f}")
    typer.echo(f"speedup: {speedup:.4f}")


@app.command("dashboard")
def dashboard_cmd(
    baseline: Annotated[
        Path, typer.Option("--baseline", exists=True, dir_okay=False, readable=True)
    ],
    candidate: Annotated[
        Path, typer.Option("--candidate", exists=True, dir_okay=False, readable=True)
    ],
    baseline_model: Annotated[
        Path, typer.Option("--baseline-model", exists=True, dir_okay=False, readable=True)
    ],
    model: Annotated[Path, typer.Option("--model", exists=True, dir_okay=False, readable=True)],
    scenarios: Annotated[Path, typer.Option("--scenarios", exists=True)],
    out: Annotated[Path, typer.Option("--out")] = Path("dashboard/index.html"),
    bench: Annotated[Path | None, typer.Option("--bench")] = None,
) -> None:
    """Write the technical dashboard as one HTML file."""

    _configure_logging()
    bench_payload: dict[str, Any] | None = None
    if bench is not None:
        if not bench.is_file():
            raise typer.BadParameter(f"bench file not found: {bench}")
        loaded_bench = json.loads(bench.read_text(encoding="utf-8"))
        if not isinstance(loaded_bench, dict):
            raise typer.BadParameter("bench file must be a JSON object")
        bench_payload = loaded_bench
    render_dashboard(
        scenarios=load_scenarios(scenarios),
        baseline_model=load_model(baseline_model),
        candidate_model=load_model(model),
        baseline_run=RunFile.read_jsonl(baseline),
        candidate_run=RunFile.read_jsonl(candidate),
        bench=bench_payload,
        path=out,
    )
    typer.echo(f"wrote {out}")
