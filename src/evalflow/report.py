"""Render a comparison to one static HTML file."""

from __future__ import annotations

from pathlib import Path
from typing import TypedDict

from jinja2 import Environment, FileSystemLoader, select_autoescape

from evalflow.compare import Comparison

_TRACK_WIDTH = 360.0


class _Bar(TypedDict):
    name: str
    count: int
    color: str
    x: float
    width: float


def render_report(comparison: Comparison, path: Path) -> None:
    template_dir = Path(__file__).resolve().parent / "templates"
    environment = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=select_autoescape(enabled_extensions=("html", "j2"), default_for_string=True),
    )
    html = environment.get_template("report.html.j2").render(
        comparison=comparison,
        bars=_bars(comparison),
        top_shown=len(comparison.top_regressions),
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(html, encoding="utf-8")


def _bars(comparison: Comparison) -> list[_Bar]:
    segments: tuple[tuple[str, int, str], ...] = (
        ("regression", comparison.regressions, "#9f1239"),
        ("improvement", comparison.improvements, "#047857"),
        ("unchanged", comparison.unchanged, "#475569"),
    )
    total = sum(count for _, count, _ in segments)
    bars: list[_Bar] = []
    cursor = 0.0
    for name, count, color in segments:
        width = 0.0 if total == 0 else _TRACK_WIDTH * count / total
        bars.append(
            {
                "name": name,
                "count": count,
                "color": color,
                "x": round(cursor, 2),
                "width": round(width, 2),
            }
        )
        cursor += width
    return bars
