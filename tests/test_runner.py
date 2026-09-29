"""Worker failures stay isolated, and corrupt cache bytes are recomputed."""

import logging
from pathlib import Path

import pytest

from evalflow.cache import cache_path, component_subset
from evalflow.evaluator import evaluate
from evalflow.runner import run
from tests.support import make_model, make_scenario


def test_runner_isolates_failures_and_repairs_corrupt_cache(
    tmp_path: Path,
    caplog: pytest.LogCaptureFixture,
) -> None:
    model = make_model()
    scenarios = [
        make_scenario("night-001", "night", ["perception"], seed=1),
        make_scenario("night-002", "night", ["planner"], seed=2),
        make_scenario("rain-001", "rain", ["prediction"], seed=3),
    ]
    result = run(
        model,
        scenarios,
        workers=2,
        cache_dir=tmp_path / "cache",
        cache_enabled=True,
        cost_s=0.0,
        _fail_ids={"night-002"},
    )
    by_id = {record.scenario_id: record for record in result.records}
    assert [record.scenario_id for record in result.records] == [
        scenario.id for scenario in scenarios
    ]
    assert by_id["night-002"].error is not None
    assert "injected failure" in by_id["night-002"].error
    assert by_id["night-002"].metrics is None
    assert by_id["night-001"].error is None
    assert by_id["night-001"].metrics == evaluate(
        scenarios[0], component_subset(model, scenarios[0]), 0.0
    )
    assert by_id["rain-001"].error is None
    assert by_id["rain-001"].metrics is not None

    fresh = run(
        model,
        [scenarios[0]],
        workers=1,
        cache_dir=tmp_path / "fresh",
        cache_enabled=True,
        cost_s=0.0,
    )
    assert fresh.records[0].metrics is not None
    corrupt_dir = tmp_path / "corrupt"
    path = cache_path(corrupt_dir, fresh.records[0].cache_key)
    path.parent.mkdir(parents=True)
    path.write_bytes(b"{not-json")

    with caplog.at_level(logging.WARNING):
        repaired = run(
            model,
            [scenarios[0]],
            workers=1,
            cache_dir=corrupt_dir,
            cache_enabled=True,
            cost_s=0.0,
        )

    assert repaired.records[0].error is None
    assert repaired.records[0].cache_status == "miss"
    assert repaired.records[0].metrics == fresh.records[0].metrics
    assert any("unreadable or schema-invalid" in record.message for record in caplog.records)
    stored = path.read_text(encoding="utf-8")
    assert "min_distance_m" in stored
