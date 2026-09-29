"""Comparator pass flips, jerk jumps, and in-tolerance noise."""

from evalflow.compare import compare_runs
from tests.support import make_record, make_run


def test_comparator_tolerances_and_pass_flip() -> None:
    baseline = make_run(
        [
            make_record("flip", "night", passed=True, min_distance_m=2.0, jerk=0.4),
            make_record("jerk", "rain", passed=True, min_distance_m=2.0, jerk=0.4),
            make_record("noise", "construction", passed=True, min_distance_m=2.0, jerk=0.4),
            make_record("mixed", "highway_merge", passed=True, min_distance_m=1.5, jerk=0.3),
        ]
    )
    candidate = make_run(
        [
            make_record("flip", "night", passed=False, min_distance_m=2.0, jerk=0.4),
            make_record("jerk", "rain", passed=True, min_distance_m=2.0, jerk=0.8),
            make_record("noise", "construction", passed=True, min_distance_m=1.96, jerk=0.49),
            make_record("mixed", "highway_merge", passed=True, min_distance_m=2.2, jerk=0.6),
        ]
    )

    report = compare_runs(baseline, candidate)
    by_id = {row.scenario_id: row for row in report.scenarios}

    assert by_id["flip"].status == "regression"
    assert by_id["flip"].pass_flip == "regression"
    assert by_id["jerk"].status == "regression"
    assert "jerk worsened" in by_id["jerk"].reasons
    assert by_id["noise"].status == "unchanged"
    assert by_id["mixed"].status == "regression"
    assert report.top_regressions[0].scenario_id == "flip"
    assert report.regressions == 3
    assert report.unchanged == 1
