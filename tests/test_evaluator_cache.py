"""Uncached evals agree, and a cache hit matches a fresh eval."""

from pathlib import Path

from evalflow.cache import component_subset
from evalflow.evaluator import evaluate
from evalflow.runner import run
from tests.support import make_model, make_scenario


def test_cache_hit_matches_fresh_eval(tmp_path: Path) -> None:
    scenario = make_scenario("rain-001", "rain", ["perception"], seed=3)
    model = make_model()
    params = component_subset(model, scenario)

    first = evaluate(scenario, params, 0.0)
    second = evaluate(scenario, params, 0.0)
    assert first == second

    cache_dir = tmp_path / "cache"
    missed = run(model, [scenario], workers=2, cache_dir=cache_dir, cache_enabled=True, cost_s=0.0)
    hit = run(model, [scenario], workers=2, cache_dir=cache_dir, cache_enabled=True, cost_s=0.0)

    assert missed.records[0].cache_status == "miss"
    assert missed.records[0].metrics == first
    assert hit.records[0].cache_status == "hit"
    assert hit.records[0].duration_s == 0.0
    assert hit.records[0].metrics == first
