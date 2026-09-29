"""Synthetic scenario evaluator.

Evalflow is not a Nuro system and not a real autonomy stack. ``evaluate`` is a
deterministic function of the scenario and the component parameters listed in
``depends_on``. It does not simulate a vehicle. Bumping ``EVALUATOR_VERSION``
changes every cache key.
"""

from __future__ import annotations

import hashlib
import time
from collections.abc import Mapping

from evalflow.models import Metrics, Scenario

EVALUATOR_VERSION = "synthetic-v1"

# Published metrics at or beyond these lines count as a synthetic pass.
_PASS_MIN_DISTANCE_M = 1.5
_PASS_MAX_JERK = 0.8


def evaluate(
    scenario: Scenario,
    components: Mapping[str, Mapping[str, float]],
    cost_s: float,
) -> Metrics:
    """Return synthetic metrics for one scenario.

    ``components`` must be exactly ``scenario.depends_on``. Parameters outside
    that set are rejected so an unrelated edit cannot change the output without
    changing the cache key. ``cost_s`` is simulated work via ``time.sleep``.
    """

    if set(components) != set(scenario.depends_on):
        raise ValueError("evaluate() accepts only the components listed in scenario.depends_on")
    if cost_s < 0:
        raise ValueError("cost_s must be >= 0")
    time.sleep(cost_s)

    unit = _unit(f"{scenario.id}:{scenario.category}:{scenario.seed}")
    min_distance = 2.0 + 0.5 * unit
    jerk = 0.6 - 0.2 * unit

    if "perception" in components:
        perception = components["perception"]
        noise = _param(perception, "noise")
        range_m = _param(perception, "range_m")
        min_distance += 0.001 * (range_m - 100.0) - 0.5 * noise
        jerk += 0.2 * noise

    if "prediction" in components:
        prediction = components["prediction"]
        horizon_s = _param(prediction, "horizon_s")
        uncertainty = _param(prediction, "uncertainty")
        min_distance += 0.005 * (horizon_s - 6.0) - 0.3 * uncertainty
        jerk += 0.15 * uncertainty

    if "planner" in components:
        planner = components["planner"]
        conservatism = _param(planner, "conservatism")
        comfort = _param(planner, "comfort_weight")
        # Higher conservatism holds a larger gap and a calmer profile.
        min_distance += 0.4 * conservatism
        jerk -= 0.3 * conservatism + 0.02 * (comfort - 1.0)
        if scenario.category == "unprotected_left":
            # v1 conservatism sits above this line, v2 sits below it, so only
            # the exposed tail of unprotected-left cases flips pass to fail.
            shortfall = max(0.0, 0.7 - conservatism)
            min_distance -= shortfall * unit * 3.2
            jerk += shortfall * unit * 1.8

    min_distance_m = round(min_distance, 6)
    jerk_value = round(jerk, 6)
    passed = min_distance_m >= _PASS_MIN_DISTANCE_M and jerk_value <= _PASS_MAX_JERK
    return Metrics(passed=passed, min_distance_m=min_distance_m, jerk=jerk_value)


def _unit(text: str) -> float:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    return int.from_bytes(digest[:8], "big") / float(2**64)


def _param(params: Mapping[str, float], name: str) -> float:
    try:
        return float(params[name])
    except KeyError as exc:
        raise KeyError(f"missing component parameter {name}") from exc
