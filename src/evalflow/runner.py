"""Dependency-aware runner.

Hits load stored metrics and record ``duration_s`` of 0. Misses go through a
process pool. The worker is a module-level function so it pickles. A worker
exception becomes a record with ``error`` set; the rest of the run finishes.
"""

from __future__ import annotations

import logging
import multiprocessing
import time
from collections.abc import Collection, Sequence
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from evalflow.cache import cache_key, component_subset, read_metrics, write_metrics
from evalflow.evaluator import EVALUATOR_VERSION, evaluate
from evalflow.models import ModelConfig, RunFile, RunHeader, Scenario, ScenarioRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalTask:
    """Work item for one cache miss.

    ``fail`` is a test seam. It is not a field on the public scenario schema.
    """

    scenario: dict[str, Any]
    components: dict[str, dict[str, float]]
    cache_key: str
    cache_dir: str
    cache_enabled: bool
    cost_s: float
    fail: bool = False


def run(
    model: ModelConfig,
    scenarios: Sequence[Scenario],
    workers: int,
    cache_dir: Path,
    cache_enabled: bool,
    cost_s: float,
    *,
    _fail_ids: Collection[str] | None = None,
) -> RunFile:
    """Evaluate ``scenarios`` and return a run file.

    ``_fail_ids`` sets ``EvalTask.fail`` for those ids so the worker raises.
    Callers other than tests should leave it unset.
    """

    if workers < 1:
        raise ValueError("workers must be >= 1")
    if cost_s < 0:
        raise ValueError("cost_s must be >= 0")
    ids = [scenario.id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate scenario ids")

    fail_ids = set(_fail_ids or ())
    started = time.perf_counter()
    records_by_id: dict[str, ScenarioRecord] = {}
    tasks: list[EvalTask] = []
    missing = 0

    for scenario in scenarios:
        key = cache_key(scenario, model, EVALUATOR_VERSION)
        if cache_enabled:
            cached, status = read_metrics(cache_dir, key)
            if cached is not None:
                records_by_id[scenario.id] = ScenarioRecord(
                    scenario_id=scenario.id,
                    category=scenario.category,
                    cache_status="hit",
                    cache_key=key,
                    metrics=cached,
                    duration_s=0.0,
                    error=None,
                )
                continue
            if status == "missing":
                missing += 1
        tasks.append(
            EvalTask(
                scenario=scenario.model_dump(mode="json"),
                components=component_subset(model, scenario),
                cache_key=key,
                cache_dir=str(cache_dir),
                cache_enabled=cache_enabled,
                cost_s=cost_s,
                fail=scenario.id in fail_ids,
            )
        )

    if missing:
        logger.warning("%d cache entries were missing and will be recomputed", missing)

    for record in _run_misses(tasks, workers):
        records_by_id[record.scenario_id] = record

    records = [records_by_id[scenario.id] for scenario in scenarios]
    hits = sum(1 for record in records if record.cache_status == "hit")
    header = RunHeader(
        wall_clock_s=round(time.perf_counter() - started, 6),
        hits=hits,
        misses=len(records) - hits,
        workers=workers,
        cache_enabled=cache_enabled,
        model_version=model.version,
        evaluator_version=EVALUATOR_VERSION,
    )
    return RunFile(header=header, records=records)


def _run_misses(tasks: Sequence[EvalTask], workers: int) -> list[ScenarioRecord]:
    if not tasks:
        return []
    context = multiprocessing.get_context("spawn")
    with ProcessPoolExecutor(
        max_workers=min(workers, len(tasks)),
        mp_context=context,
    ) as pool:
        return list(pool.map(_evaluate_task, tasks, chunksize=1))


def _evaluate_task(task: EvalTask) -> ScenarioRecord:
    started = time.perf_counter()
    scenario = Scenario.model_validate(task.scenario)
    try:
        if task.fail:
            raise RuntimeError(f"injected failure for {scenario.id}")
        metrics = evaluate(scenario, task.components, task.cost_s)
        if task.cache_enabled:
            write_metrics(Path(task.cache_dir), task.cache_key, metrics)
        return ScenarioRecord(
            scenario_id=scenario.id,
            category=scenario.category,
            cache_status="miss",
            cache_key=task.cache_key,
            metrics=metrics,
            duration_s=round(time.perf_counter() - started, 6),
            error=None,
        )
    except Exception as exc:
        return ScenarioRecord(
            scenario_id=scenario.id,
            category=scenario.category,
            cache_status="miss",
            cache_key=task.cache_key,
            metrics=None,
            duration_s=round(time.perf_counter() - started, 6),
            error=f"{type(exc).__name__}: {exc}",
        )
