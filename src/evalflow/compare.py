"""Join two run files and label each scenario."""

from __future__ import annotations

from typing import Literal, cast

import pandas as pd
from pydantic import BaseModel, ConfigDict

from evalflow.models import CATEGORIES, Category, Metrics, RunFile, RunHeader, ScenarioRecord

Status = Literal["regression", "improvement", "unchanged"]
PassFlip = Literal["regression", "improvement", "none"]

DEFAULT_DISTANCE_TOL = 0.05
DEFAULT_JERK_TOL = 0.10


class ScenarioComparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    category: Category
    status: Status
    pass_flip: PassFlip
    reasons: list[str]
    baseline: Metrics
    candidate: Metrics
    min_distance_delta: float
    jerk_delta: float
    worsen_score: float


class CategorySummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category: Category
    regressions: int
    improvements: int
    unchanged: int


class Comparison(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scenarios: list[ScenarioComparison]
    by_category: list[CategorySummary]
    top_regressions: list[ScenarioComparison]
    regressions: int
    improvements: int
    unchanged: int
    baseline_header: RunHeader
    candidate_header: RunHeader
    distance_tol: float
    jerk_tol: float


def compare_runs(
    baseline: RunFile,
    candidate: RunFile,
    *,
    distance_tol: float = DEFAULT_DISTANCE_TOL,
    jerk_tol: float = DEFAULT_JERK_TOL,
    top_n: int = 10,
) -> Comparison:
    """Join on scenario id and classify each row.

    A pass that flips from true to false is a regression. ``min_distance_m``
    worsens when the candidate is below the baseline by more than
    ``distance_tol``. ``jerk`` worsens when the candidate is above the baseline
    by more than ``jerk_tol``. A row that both improves and regresses counts as
    a regression. Inside both tolerances, with no pass flip, the row is unchanged.
    """

    if distance_tol <= 0 or jerk_tol <= 0:
        raise ValueError("tolerances must be positive")
    if top_n < 1:
        raise ValueError("top_n must be >= 1")

    baseline_rows = {record.scenario_id: record for record in baseline.records}
    candidate_rows = {record.scenario_id: record for record in candidate.records}
    if set(baseline_rows) != set(candidate_rows):
        mismatch = sorted(set(baseline_rows) ^ set(candidate_rows))
        preview = ", ".join(mismatch[:5])
        raise ValueError(f"run files do not cover the same scenarios: {preview}")

    compared = [
        _classify(
            baseline_rows[record.scenario_id],
            candidate_rows[record.scenario_id],
            distance_tol,
            jerk_tol,
        )
        for record in baseline.records
    ]
    regressions = [row for row in compared if row.status == "regression"]
    regressions.sort(key=_regression_sort_key)
    return Comparison(
        scenarios=compared,
        by_category=_by_category(compared),
        top_regressions=regressions[:top_n],
        regressions=sum(1 for row in compared if row.status == "regression"),
        improvements=sum(1 for row in compared if row.status == "improvement"),
        unchanged=sum(1 for row in compared if row.status == "unchanged"),
        baseline_header=baseline.header,
        candidate_header=candidate.header,
        distance_tol=distance_tol,
        jerk_tol=jerk_tol,
    )


def _classify(
    baseline: ScenarioRecord,
    candidate: ScenarioRecord,
    distance_tol: float,
    jerk_tol: float,
) -> ScenarioComparison:
    if baseline.metrics is None or candidate.metrics is None:
        raise ValueError(f"scenario {baseline.scenario_id} is missing metrics")
    if baseline.category != candidate.category:
        raise ValueError(f"scenario {baseline.scenario_id} category differs between runs")

    base = baseline.metrics
    cand = candidate.metrics
    distance_delta = cand.min_distance_m - base.min_distance_m
    jerk_delta = cand.jerk - base.jerk
    distance_worse = distance_delta < -distance_tol
    distance_better = distance_delta > distance_tol
    jerk_worse = jerk_delta > jerk_tol
    jerk_better = jerk_delta < -jerk_tol

    if base.passed and not cand.passed:
        pass_flip: PassFlip = "regression"
    elif (not base.passed) and cand.passed:
        pass_flip = "improvement"
    else:
        pass_flip = "none"

    reasons: list[str] = []
    if pass_flip == "regression":
        reasons.append("pass flipped true to false")
    elif pass_flip == "improvement":
        reasons.append("pass flipped false to true")
    if distance_worse:
        reasons.append("min_distance_m worsened")
    elif distance_better:
        reasons.append("min_distance_m improved")
    if jerk_worse:
        reasons.append("jerk worsened")
    elif jerk_better:
        reasons.append("jerk improved")

    regressed = pass_flip == "regression" or distance_worse or jerk_worse
    improved = pass_flip == "improvement" or distance_better or jerk_better
    if regressed:
        status: Status = "regression"
    elif improved:
        status = "improvement"
    else:
        status = "unchanged"

    worsen_score = max(0.0, -distance_delta / distance_tol) + max(0.0, jerk_delta / jerk_tol)
    return ScenarioComparison(
        scenario_id=baseline.scenario_id,
        category=baseline.category,
        status=status,
        pass_flip=pass_flip,
        reasons=reasons,
        baseline=base,
        candidate=cand,
        min_distance_delta=distance_delta,
        jerk_delta=jerk_delta,
        worsen_score=worsen_score,
    )


def _regression_sort_key(row: ScenarioComparison) -> tuple[int, float, str]:
    # Pass flips (true to false) sort ahead of metric-only regressions.
    flip_rank = 0 if row.pass_flip == "regression" else 1
    return (flip_rank, -row.worsen_score, row.scenario_id)


def _by_category(rows: list[ScenarioComparison]) -> list[CategorySummary]:
    frame = pd.DataFrame(
        {
            "category": [row.category for row in rows],
            "status": [row.status for row in rows],
        }
    )
    totals: dict[str, dict[str, int]] = {}
    if not frame.empty:
        counted = frame.value_counts(["category", "status"]).rename("n").reset_index()
        records = cast(list[dict[str, object]], counted.to_dict(orient="records"))
        for record in records:
            category = str(record["category"])
            status = str(record["status"])
            raw_count = record["n"]
            totals.setdefault(category, {})[status] = int(cast(int, raw_count))

    summaries: list[CategorySummary] = []
    for category in CATEGORIES:
        bucket = totals.get(category)
        if bucket is None:
            continue
        summaries.append(
            CategorySummary(
                category=category,
                regressions=bucket.get("regression", 0),
                improvements=bucket.get("improvement", 0),
                unchanged=bucket.get("unchanged", 0),
            )
        )
    return summaries
