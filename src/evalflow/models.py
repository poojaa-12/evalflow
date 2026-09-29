"""Pydantic contracts for scenarios, model configs, metrics, and run files."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

Category = Literal[
    "night",
    "rain",
    "unprotected_left",
    "highway_merge",
    "construction",
]
ComponentName = Literal["perception", "planner", "prediction"]
CacheStatus = Literal["hit", "miss"]

CATEGORIES: tuple[Category, ...] = (
    "night",
    "rain",
    "unprotected_left",
    "highway_merge",
    "construction",
)
COMPONENT_NAMES: tuple[ComponentName, ...] = ("perception", "planner", "prediction")


class Scenario(BaseModel):
    """One eval case and the model components it is allowed to read."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1)
    category: Category
    seed: int
    depends_on: list[ComponentName]

    @field_validator("depends_on")
    @classmethod
    def _normalize_depends_on(cls, value: list[ComponentName]) -> list[ComponentName]:
        if not value:
            raise ValueError("depends_on must not be empty")
        if len(set(value)) != len(value):
            raise ValueError("depends_on contains duplicates")
        unknown = set(value) - set(COMPONENT_NAMES)
        if unknown:
            raise ValueError(f"unknown components: {sorted(unknown)}")
        return [name for name in COMPONENT_NAMES if name in value]


class ModelConfig(BaseModel):
    """Named component parameters for one model version."""

    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    components: dict[ComponentName, dict[str, float]]

    @model_validator(mode="after")
    def _require_components(self) -> Self:
        found = set(self.components)
        expected = set(COMPONENT_NAMES)
        if found != expected:
            raise ValueError(
                f"components must be exactly {list(COMPONENT_NAMES)}, got {sorted(found)}"
            )
        return self


class Metrics(BaseModel):
    """Synthetic stand-in metrics. Not measurements from a real autonomy stack."""

    model_config = ConfigDict(extra="forbid")

    passed: bool = Field(description="Synthetic pass/fail. Not a real autonomy result.")
    min_distance_m: float = Field(
        description="Synthetic minimum distance in meters. Higher is better."
    )
    jerk: float = Field(
        description="Synthetic jerk. Lower is better. Not a real vehicle measurement."
    )


class ScenarioRecord(BaseModel):
    """One scenario row inside a run file."""

    model_config = ConfigDict(extra="forbid")

    scenario_id: str
    category: Category
    cache_status: CacheStatus
    cache_key: str
    metrics: Metrics | None = None
    duration_s: float
    error: str | None = None


class RunHeader(BaseModel):
    """First JSONL line. Describes the run, not a scenario."""

    model_config = ConfigDict(extra="forbid")

    wall_clock_s: float
    hits: int
    misses: int
    workers: int
    cache_enabled: bool
    model_version: str
    evaluator_version: str


class RunFile(BaseModel):
    """A JSONL run: one header line, then one scenario record per line."""

    model_config = ConfigDict(extra="forbid")

    header: RunHeader
    records: list[ScenarioRecord]

    def write_jsonl(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        lines = [self.header.model_dump_json()]
        lines.extend(record.model_dump_json() for record in self.records)
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    @classmethod
    def read_jsonl(cls, path: Path) -> RunFile:
        lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if not lines:
            raise ValueError(f"run file is empty: {path}")
        try:
            header = RunHeader.model_validate_json(lines[0])
            records = [ScenarioRecord.model_validate_json(line) for line in lines[1:]]
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(f"invalid run file {path}: {exc}") from exc
        return cls(header=header, records=records)


def load_model(path: Path) -> ModelConfig:
    payload = yaml.safe_load(path.read_text(encoding="utf-8"))
    return ModelConfig.model_validate(payload)
