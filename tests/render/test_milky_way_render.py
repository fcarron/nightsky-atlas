from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

from nightsky_atlas.atlas.config import MilkyWayStyle, load_style_config
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.cairo import _draw_milky_way_contours
from nightsky_atlas.scene.models import ChartScene, SceneMilkyWayContour

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("edition", "levels", "line_width_mm"),
    (
        ("pocket", (1,), 0.095),
        ("standard", (1, 3), 0.09),
        ("deep", (1, 3, 5), 0.085),
        ("eyepiece", (1, 3), 0.07),
    ),
)
def test_edition_milky_way_level_mapping(
    edition: str, levels: tuple[int, ...], line_width_mm: float
) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    assert style.milky_way.enabled is True
    assert style.milky_way.levels == levels
    assert style.milky_way.line_width_mm == pytest.approx(line_width_mm)
    assert style.milky_way.line_width_mm < style.constellation.boundaries.line_width_mm
    boundary_strength = style.constellation.boundaries.line_width_mm * (
        1.0 - style.constellation.boundaries.gray
    )
    assert all(
        style.milky_way.line_width_mm * (1.0 - style.milky_way.level_gray[level])
        < boundary_strength
        for level in levels
    )
    grays = tuple(style.milky_way.level_gray[level] for level in levels)
    assert grays == tuple(sorted(grays, reverse=True))


def test_main_edition_milky_way_contrast_steps_down_with_chart_scale() -> None:
    strengths = []
    for edition in ("pocket", "standard", "deep"):
        style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
        strengths.append(
            max(
                style.milky_way.line_width_mm * (1.0 - style.milky_way.level_gray[level])
                for level in style.milky_way.levels
            )
        )
    assert strengths[0] > strengths[1] > strengths[2]


def test_disabled_layer_does_not_touch_the_renderer() -> None:
    style = load_style_config(REPO_ROOT / "styles" / "standard.yaml").model_copy(
        update={"milky_way": MilkyWayStyle(enabled=False, levels=())}
    )
    scene = ChartScene(
        definition=ChartDefinition("off", 0.0, 0.0, 4.0, 4.0),
        milky_way_contours=(
            SceneMilkyWayContour(
                "milky-way:1:test", 1, (ChartPoint(0.0, 0.0), ChartPoint(1.0, 1.0))
            ),
        ),
    )
    context = Mock()
    _draw_milky_way_contours(context, Mock(), scene, style)
    context.assert_not_called()
