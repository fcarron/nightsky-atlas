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
    ("edition", "levels"),
    (
        ("pocket", (1,)),
        ("standard", (1, 3)),
        ("deep", (1, 3, 5)),
        ("eyepiece", (1, 3)),
    ),
)
def test_edition_milky_way_level_mapping(edition: str, levels: tuple[int, ...]) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    assert style.milky_way.enabled is True
    assert style.milky_way.levels == levels
    assert style.milky_way.line_width_mm < style.constellation.boundaries.line_width_mm
    boundary_strength = style.constellation.boundaries.line_width_mm * (
        1.0 - style.constellation.boundaries.gray
    )
    assert all(
        style.milky_way.line_width_mm * (1.0 - style.milky_way.level_gray[level])
        < boundary_strength
        for level in levels
    )


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
