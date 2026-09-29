"""Cache keys follow depends_on and ignore unrelated components."""

from evalflow.cache import cache_key
from evalflow.evaluator import EVALUATOR_VERSION
from tests.support import make_model, make_scenario


def test_cache_key_tracks_only_dependencies() -> None:
    planner_case = make_scenario("night-001", "night", ["planner"])
    perception_case = make_scenario("night-002", "night", ["perception"])
    baseline = make_model()
    edited_planner = make_model(conservatism=0.35)
    edited_perception = make_model(noise=0.2)

    planner_baseline = cache_key(planner_case, baseline, EVALUATOR_VERSION)
    assert planner_baseline != cache_key(planner_case, edited_planner, EVALUATOR_VERSION)
    assert planner_baseline == cache_key(planner_case, edited_perception, EVALUATOR_VERSION)

    perception_baseline = cache_key(perception_case, baseline, EVALUATOR_VERSION)
    assert perception_baseline != cache_key(perception_case, edited_perception, EVALUATOR_VERSION)
    assert perception_baseline == cache_key(perception_case, edited_planner, EVALUATOR_VERSION)
