"""The committed 200-scenario suite matches the generator and the v1/v2 story."""

from collections import Counter
from pathlib import Path

from evalflow.cache import cache_key, component_subset
from evalflow.evaluator import EVALUATOR_VERSION, evaluate
from evalflow.generate import generate_scenarios, load_scenarios
from evalflow.models import load_model

ROOT = Path(__file__).resolve().parents[1]


def test_committed_scenarios_match_generator() -> None:
    loaded = load_scenarios(ROOT / "scenarios")
    generated = generate_scenarios(200, 0)
    assert [scenario.model_dump() for scenario in loaded] == [
        scenario.model_dump() for scenario in generated
    ]
    counts = Counter(tuple(scenario.depends_on) for scenario in loaded)
    assert counts[("perception",)] == 120
    assert counts[("planner",)] == 40
    assert counts[("perception", "planner")] == 20
    assert counts[("prediction",)] == 10
    assert counts[("planner", "prediction")] == 10
    assert sum(1 for scenario in loaded if scenario.id.startswith("night-")) == 40


def test_planner_edit_invalidates_only_dependents() -> None:
    scenarios = load_scenarios(ROOT / "scenarios")
    baseline = load_model(ROOT / "configs" / "v1.yaml")
    candidate = load_model(ROOT / "configs" / "v2.yaml")

    changed = 0
    flips: list[str] = []
    for scenario in scenarios:
        baseline_key = cache_key(scenario, baseline, EVALUATOR_VERSION)
        candidate_key = cache_key(scenario, candidate, EVALUATOR_VERSION)
        baseline_metrics = evaluate(scenario, component_subset(baseline, scenario), 0.0)
        candidate_metrics = evaluate(scenario, component_subset(candidate, scenario), 0.0)
        if "planner" not in scenario.depends_on:
            assert baseline_key == candidate_key
            assert baseline_metrics == candidate_metrics
            continue
        changed += 1
        assert baseline_key != candidate_key
        assert candidate_metrics.min_distance_m < baseline_metrics.min_distance_m
        assert candidate_metrics.jerk > baseline_metrics.jerk
        if baseline_metrics.passed and not candidate_metrics.passed:
            flips.append(scenario.id)
            assert scenario.category == "unprotected_left"
        else:
            assert baseline_metrics.passed
            assert candidate_metrics.passed

    assert changed == 70
    assert 1 <= len(flips) <= 12
