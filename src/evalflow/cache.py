"""Content-addressed cache keys and atomic JSON payloads."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from pathlib import Path
from typing import Literal

from pydantic import ValidationError

from evalflow.models import Metrics, ModelConfig, Scenario

logger = logging.getLogger(__name__)

CacheReadStatus = Literal["hit", "missing", "invalid"]


def canonical_json(payload: object) -> str:
    """Serialize with sorted keys and compact separators."""

    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def scenario_fingerprint(scenario: Scenario) -> str:
    """sha256 of the scenario's canonical JSON."""

    return _sha256(
        canonical_json(
            {
                "id": scenario.id,
                "category": scenario.category,
                "seed": scenario.seed,
                "depends_on": list(scenario.depends_on),
            }
        )
    )


def scenario_canonical(scenario: Scenario) -> str:
    return canonical_json(
        {
            "id": scenario.id,
            "category": scenario.category,
            "seed": scenario.seed,
            "depends_on": list(scenario.depends_on),
        }
    )


def component_hash(params: dict[str, float]) -> str:
    """sha256 of one component's canonical parameter JSON."""

    return _sha256(canonical_json(dict(params)))


def cache_key(scenario: Scenario, model: ModelConfig, evaluator_version: str) -> str:
    """Hash the evaluator version, the scenario, and only ``depends_on`` components."""

    fingerprint = scenario_fingerprint(scenario)
    component_hashes = [component_hash(model.components[name]) for name in scenario.depends_on]
    material = evaluator_version + fingerprint + "".join(component_hashes)
    return _sha256(material)


def cache_path(cache_dir: Path, key: str) -> Path:
    if len(key) < 2:
        raise ValueError("cache key must be at least 2 characters")
    return cache_dir / key[:2] / f"{key}.json"


def read_metrics(cache_dir: Path, key: str) -> tuple[Metrics | None, CacheReadStatus]:
    """Load a payload. Missing, unreadable, and schema-invalid entries are misses."""

    path = cache_path(cache_dir, key)
    if not path.exists():
        logger.debug("cache miss (missing) %s", key)
        return None, "missing"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return Metrics.model_validate(payload), "hit"
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError) as exc:
        logger.warning(
            "cache entry %s is unreadable or schema-invalid (%s); recomputing",
            key,
            exc,
        )
        return None, "invalid"


def write_metrics(cache_dir: Path, key: str, metrics: Metrics) -> None:
    """Write a payload via a temp file in the destination directory, then ``os.replace``."""

    path = cache_path(cache_dir, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=".tmp-", suffix=".json", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            handle.write(metrics.model_dump_json())
        os.replace(temporary_name, path)
    except Exception:
        if os.path.exists(temporary_name):
            os.unlink(temporary_name)
        raise


def component_subset(model: ModelConfig, scenario: Scenario) -> dict[str, dict[str, float]]:
    """Copy only the parameters the scenario is allowed to read."""

    return {
        name: {key: float(value) for key, value in model.components[name].items()}
        for name in scenario.depends_on
    }


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
