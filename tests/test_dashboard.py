"""The technical dashboard embeds the measured rows and the cache-key formula."""

from pathlib import Path

import yaml

from evalflow.dashboard import render_dashboard
from evalflow.generate import load_scenarios
from evalflow.models import load_model
from evalflow.runner import run


def test_dashboard_embeds_cache_key_and_rows(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    specs = [
        {"id": "night-001", "category": "night", "seed": 1, "depends_on": ["perception"]},
        {"id": "night-002", "category": "night", "seed": 2, "depends_on": ["planner"]},
    ]
    for spec in specs:
        (scenarios / f"{spec['id']}.yaml").write_text(yaml.safe_dump(spec), encoding="utf-8")

    def write_model(path: Path, conservatism: float) -> None:
        path.write_text(
            yaml.safe_dump(
                {
                    "version": path.stem,
                    "components": {
                        "perception": {"noise": 0.02, "range_m": 120.0},
                        "planner": {"conservatism": conservatism, "comfort_weight": 1.2},
                        "prediction": {"horizon_s": 8.0, "uncertainty": 0.15},
                    },
                }
            ),
            encoding="utf-8",
        )

    v1 = tmp_path / "v1.yaml"
    v2 = tmp_path / "v2.yaml"
    write_model(v1, 0.8)
    write_model(v2, 0.35)
    loaded = load_scenarios(scenarios)
    cache = tmp_path / "cache"
    baseline_run = run(load_model(v1), loaded, 2, cache, True, 0.0)
    candidate_run = run(load_model(v2), loaded, 2, cache, True, 0.0)
    out = tmp_path / "index.html"
    render_dashboard(
        scenarios=loaded,
        baseline_model=load_model(v1),
        candidate_model=load_model(v2),
        baseline_run=baseline_run,
        candidate_run=candidate_run,
        bench={
            "median_naive_s": 1.0,
            "median_incremental_s": 0.5,
            "speedup": 2.0,
            "incremental_hit_rate": 0.5,
            "naive_s": [1.0],
            "incremental_s": [0.5],
        },
        path=out,
    )
    html = out.read_text(encoding="utf-8")
    assert "sha256(evaluator_version + scenario_fingerprint" in html
    assert 'href="./project.html"' in html
    assert "night-001" in html
    assert "not a Nuro system" in html
    assert candidate_run.header.hits == 1
