"""Technical dashboard for one baseline/candidate pair.

The page is a single HTML file with the measured rows embedded. It is the
surface to open and share. ``evalflow compare`` still writes the regression
report; this view is the explanation of why those rows moved.
"""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

from jinja2 import Environment, FileSystemLoader, select_autoescape

from evalflow.cache import (
    cache_key,
    component_hash,
    scenario_canonical,
    scenario_fingerprint,
)
from evalflow.compare import ScenarioComparison, compare_runs
from evalflow.evaluator import EVALUATOR_VERSION
from evalflow.models import COMPONENT_NAMES, ModelConfig, RunFile, Scenario


def render_dashboard(
    *,
    scenarios: list[Scenario],
    baseline_model: ModelConfig,
    candidate_model: ModelConfig,
    baseline_run: RunFile,
    candidate_run: RunFile,
    bench: dict[str, Any] | None,
    path: Path,
) -> None:
    comparison = compare_runs(baseline_run, candidate_run)
    payload = _payload(
        scenarios=scenarios,
        baseline_model=baseline_model,
        candidate_model=candidate_model,
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        comparison_rows={row.scenario_id: row for row in comparison.scenarios},
        regressions=comparison.regressions,
        improvements=comparison.improvements,
        unchanged=comparison.unchanged,
        bench=bench,
    )
    blob = json.dumps(payload, separators=(",", ":"), ensure_ascii=True).replace("<", "\\u003c")
    environment = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parent / "templates"),
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default_for_string=True),
    )
    html = environment.get_template("dashboard.html.j2").render(payload_json=blob)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _payload(
    *,
    scenarios: list[Scenario],
    baseline_model: ModelConfig,
    candidate_model: ModelConfig,
    baseline_run: RunFile,
    candidate_run: RunFile,
    comparison_rows: dict[str, ScenarioComparison],
    regressions: int,
    improvements: int,
    unchanged: int,
    bench: dict[str, Any] | None,
) -> dict[str, Any]:
    by_id = {scenario.id: scenario for scenario in scenarios}
    baseline_records = {record.scenario_id: record for record in baseline_run.records}
    candidate_records = {record.scenario_id: record for record in candidate_run.records}
    if set(by_id) != set(baseline_records) or set(by_id) != set(candidate_records):
        raise ValueError("scenarios and run files do not cover the same ids")

    component_params = {
        name: {
            "baseline": baseline_model.components[name],
            "candidate": candidate_model.components[name],
            "changed": baseline_model.components[name] != candidate_model.components[name],
        }
        for name in COMPONENT_NAMES
    }
    rows: list[dict[str, Any]] = []
    invalidated = 0
    for scenario in scenarios:
        base_key = cache_key(scenario, baseline_model, EVALUATOR_VERSION)
        cand_key = cache_key(scenario, candidate_model, EVALUATOR_VERSION)
        changed = base_key != cand_key
        invalidated += int(changed)
        compared = comparison_rows[scenario.id]
        candidate_record = candidate_records[scenario.id]
        components = []
        for name in COMPONENT_NAMES:
            hash_v1 = component_hash(baseline_model.components[name])
            hash_v2 = component_hash(candidate_model.components[name])
            components.append(
                {
                    "name": name,
                    "in_key": name in scenario.depends_on,
                    "hash_v1": hash_v1,
                    "hash_v2": hash_v2,
                    "same": hash_v1 == hash_v2,
                }
            )
        rows.append(
            {
                "id": scenario.id,
                "category": scenario.category,
                "seed": scenario.seed,
                "depends_on": list(scenario.depends_on),
                "depends_label": " + ".join(scenario.depends_on),
                "scenario_json": scenario_canonical(scenario),
                "fingerprint": scenario_fingerprint(scenario),
                "key_v1": base_key,
                "key_v2": cand_key,
                "key_changed": changed,
                "components": components,
                "cache_status": candidate_record.cache_status,
                "duration_s": candidate_record.duration_s,
                "baseline": _metrics(baseline_records[scenario.id].metrics),
                "candidate": _metrics(candidate_record.metrics),
                "status": compared.status,
                "pass_flip": compared.pass_flip,
                "reasons": compared.reasons,
                "min_distance_delta": compared.min_distance_delta,
                "jerk_delta": compared.jerk_delta,
                "worsen_score": compared.worsen_score,
                "identical": baseline_records[scenario.id].metrics == candidate_record.metrics,
            }
        )

    mix_counts: Counter[tuple[str, ...]] = Counter(
        tuple(scenario.depends_on) for scenario in scenarios
    )
    mix = []
    for names, count in mix_counts.most_common():
        group = [row for row in rows if tuple(row["depends_on"]) == names]
        mix.append(
            {
                "depends_on": list(names),
                "label": " + ".join(names),
                "count": count,
                "invalidated": sum(1 for row in group if row["key_changed"]),
                "hits": sum(1 for row in group if row["cache_status"] == "hit"),
                "regressions": sum(1 for row in group if row["status"] == "regression"),
            }
        )
    mix.sort(key=_mix_sort)

    return {
        "evaluator_version": EVALUATOR_VERSION,
        "baseline_version": baseline_model.version,
        "candidate_version": candidate_model.version,
        "components": component_params,
        "baseline_header": baseline_run.header.model_dump(mode="json"),
        "candidate_header": candidate_run.header.model_dump(mode="json"),
        "summary": {
            "scenarios": len(rows),
            "invalidated": invalidated,
            "hits": candidate_run.header.hits,
            "misses": candidate_run.header.misses,
            "regressions": regressions,
            "improvements": improvements,
            "unchanged": unchanged,
            "pass_flips": sum(1 for row in rows if row["pass_flip"] == "regression"),
        },
        "mix": mix,
        "bench": bench,
        "scenarios": rows,
    }


def _mix_sort(item: dict[str, Any]) -> tuple[int, str]:
    count = item["count"]
    if not isinstance(count, int):
        raise TypeError("mix count must be an int")
    return (-count, str(item["label"]))


def _metrics(metrics: Any) -> dict[str, Any] | None:
    if metrics is None:
        return None
    return cast(dict[str, Any], metrics.model_dump(mode="json"))
