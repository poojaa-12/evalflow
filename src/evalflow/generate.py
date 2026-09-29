"""Deterministic scenario generator.

The committed suite is ``generate_scenarios(200, 0)`` written under ``scenarios/``,
grouped by category. A planner-only edit invalidates 70 of those 200.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from pathlib import Path

import yaml

from evalflow.models import CATEGORIES, ComponentName, Scenario

# Per-category mix. Five categories of 40 reproduce the 200-scenario suite:
# 120 perception, 40 planner, 20 perception+planner, 10 prediction, 10 planner+prediction.
_MIX: tuple[tuple[tuple[ComponentName, ...], int], ...] = (
    (("perception",), 24),
    (("planner",), 8),
    (("perception", "planner"), 4),
    (("prediction",), 2),
    (("planner", "prediction"), 2),
)


def generate_scenarios(count: int, seed: int) -> list[Scenario]:
    """Build ``count`` scenarios. ``count`` must be divisible by the category count."""

    if count <= 0:
        raise ValueError("count must be positive")
    if count % len(CATEGORIES) != 0:
        raise ValueError(f"count must be divisible by {len(CATEGORIES)}")
    per_category = count // len(CATEGORIES)
    mix = _mix_for(per_category)
    scenarios: list[Scenario] = []
    next_seed = seed
    for category in CATEGORIES:
        dependencies: list[tuple[ComponentName, ...]] = []
        for names, size in mix:
            dependencies.extend([names] * size)
        for index, names in enumerate(dependencies, start=1):
            scenarios.append(
                Scenario(
                    id=f"{category}-{index:03d}",
                    category=category,
                    seed=next_seed,
                    depends_on=list(names),
                )
            )
            next_seed += 1
    return scenarios


def write_scenarios(scenarios: Sequence[Scenario], out: Path) -> None:
    """Write one YAML file per scenario, grouped in category directories."""

    out.mkdir(parents=True, exist_ok=True)
    for scenario in scenarios:
        directory = out / scenario.category
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / f"{scenario.id}.yaml"
        text = yaml.safe_dump(scenario.model_dump(mode="json"), sort_keys=False)
        path.write_text(text, encoding="utf-8")


def load_scenarios(path: Path) -> list[Scenario]:
    """Load a YAML file or every YAML file under a directory."""

    if path.is_file():
        files = [path]
    elif path.is_dir():
        files = sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file() and candidate.suffix in {".yaml", ".yml"}
        )
    else:
        raise FileNotFoundError(path)
    if not files:
        raise FileNotFoundError(f"no scenario YAML files in {path}")

    scenarios: list[Scenario] = []
    for file in files:
        loaded = yaml.safe_load(file.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            scenarios.extend(Scenario.model_validate(item) for item in loaded)
        else:
            scenarios.append(Scenario.model_validate(loaded))
    ids = [scenario.id for scenario in scenarios]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate scenario ids in {path}")
    order = {category: index for index, category in enumerate(CATEGORIES)}
    scenarios.sort(key=lambda scenario: (order[scenario.category], scenario.id))
    return scenarios


def _mix_for(per_category: int) -> list[tuple[tuple[ComponentName, ...], int]]:
    weights = [count for _, count in _MIX]
    total = sum(weights)
    scaled = [per_category * weight / total for weight in weights]
    floors = [math.floor(value) for value in scaled]
    leftover = per_category - sum(floors)
    ranked = sorted(
        range(len(_MIX)),
        key=lambda index: (scaled[index] - floors[index], -index),
        reverse=True,
    )
    for index in ranked[:leftover]:
        floors[index] += 1
    if sum(floors) != per_category:
        raise RuntimeError("dependency mix does not sum to the category size")
    return [(_MIX[index][0], floors[index]) for index in range(len(_MIX))]
