"""Typer run then compare writes an HTML summary banner."""

from pathlib import Path

import yaml
from typer.testing import CliRunner

from evalflow.cli import app

runner = CliRunner()


def test_cli_run_then_compare_writes_summary_banner(tmp_path: Path) -> None:
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    specs = [
        {"id": "night-001", "category": "night", "seed": 1, "depends_on": ["perception"]},
        {"id": "night-002", "category": "night", "seed": 2, "depends_on": ["planner"]},
        {"id": "rain-001", "category": "rain", "seed": 3, "depends_on": ["prediction"]},
    ]
    for spec in specs:
        (scenarios / f"{spec['id']}.yaml").write_text(
            yaml.safe_dump(spec),
            encoding="utf-8",
        )

    def dump_model(path: Path, conservatism: float) -> None:
        path.write_text(
            yaml.safe_dump(
                {
                    "version": path.stem,
                    "components": {
                        "perception": {"noise": 0.02, "range_m": 120.0},
                        "planner": {"conservatism": conservatism, "comfort_weight": 1.2},
                        "prediction": {"horizon_s": 8.0, "uncertainty": 0.15},
                    },
                }
            ),
            encoding="utf-8",
        )

    v1 = tmp_path / "v1.yaml"
    v2 = tmp_path / "v2.yaml"
    dump_model(v1, 0.8)
    dump_model(v2, 0.35)
    out_v1 = tmp_path / "v1.jsonl"
    out_v2 = tmp_path / "v2.jsonl"
    cache = tmp_path / "cache"
    report = tmp_path / "report.html"

    first = runner.invoke(
        app,
        [
            "run",
            "--model",
            str(v1),
            "--scenarios",
            str(scenarios),
            "--workers",
            "2",
            "--out",
            str(out_v1),
            "--cache-dir",
            str(cache),
            "--cost-s",
            "0",
        ],
    )
    assert first.exit_code == 0, first.output
    second = runner.invoke(
        app,
        [
            "run",
            "--model",
            str(v2),
            "--scenarios",
            str(scenarios),
            "--workers",
            "2",
            "--out",
            str(out_v2),
            "--cache-dir",
            str(cache),
            "--cost-s",
            "0",
        ],
    )
    assert second.exit_code == 0, second.output

    compared = runner.invoke(
        app,
        ["compare", str(out_v1), str(out_v2), "--out", str(report)],
    )
    assert compared.exit_code == 0, compared.output
    html = report.read_text(encoding="utf-8")
    assert 'id="summary-banner"' in html
    assert "Regressions" in html
    assert "Improvements" in html
    assert "Unchanged" in html
    assert "not a Nuro system" in html
    assert "not a real autonomy stack" in html
