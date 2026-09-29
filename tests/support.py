"""Shared fixtures for the evalflow tests."""

from evalflow.models import (
    ComponentName,
    Metrics,
    ModelConfig,
    RunFile,
    RunHeader,
    Scenario,
    ScenarioRecord,
)


def make_model(
    version: str = "test",
    *,
    conservatism: float = 0.8,
    noise: float = 0.02,
) -> ModelConfig:
    return ModelConfig(
        version=version,
        components={
            "perception": {"noise": noise, "range_m": 120.0},
            "planner": {"conservatism": conservatism, "comfort_weight": 1.2},
            "prediction": {"horizon_s": 8.0, "uncertainty": 0.15},
        },
    )


def make_scenario(
    scenario_id: str,
    category: str,
    depends_on: list[ComponentName],
    seed: int = 1,
) -> Scenario:
    return Scenario(id=scenario_id, category=category, seed=seed, depends_on=depends_on)  # type: ignore[arg-type]


def make_record(
    scenario_id: str,
    category: str,
    *,
    passed: bool,
    min_distance_m: float,
    jerk: float,
) -> ScenarioRecord:
    return ScenarioRecord(
        scenario_id=scenario_id,
        category=category,  # type: ignore[arg-type]
        cache_status="miss",
        cache_key="a" * 64,
        metrics=Metrics(passed=passed, min_distance_m=min_distance_m, jerk=jerk),
        duration_s=0.01,
    )


def make_run(records: list[ScenarioRecord], *, version: str = "test") -> RunFile:
    return RunFile(
        header=RunHeader(
            wall_clock_s=1.0,
            hits=0,
            misses=len(records),
            workers=1,
            cache_enabled=False,
            model_version=version,
            evaluator_version="synthetic-v1",
        ),
        records=records,
    )
