from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.systems import StarSystem
from nightsky_atlas.catalog.wds_selection import pair_passes_delta_magnitude, pair_passes_profile

ROOT = Path(__file__).resolve().parents[2]


def pair(separation: float, primary: float | None, secondary: float | None) -> StarSystem:
    return StarSystem(
        id="system:wds:test",
        source="WDS",
        source_id="TEST:AB",
        component_designation="AB",
        separation_arcsec=separation,
        component_magnitudes=(primary, secondary),
    )


@pytest.mark.parametrize(
    ("edition", "separation", "secondary", "expected"),
    [
        ("pocket", 30.0, 10.5, True),
        ("pocket", 30.1, 10.5, False),
        ("pocket", 200.0, 8.5, True),
        ("standard", 30.0, 11.5, True),
        ("standard", 120.0, 10.0, True),
        ("standard", 200.0, 9.0, True),
        ("standard", 200.1, 8.0, False),
        ("deep", 30.0, 13.0, True),
        ("deep", 120.0, 11.5, True),
        ("deep", 300.0, 10.0, True),
        ("deep", 300.1, 8.0, False),
    ],
)
def test_profile_limits(edition: str, separation: float, secondary: float, expected: bool) -> None:
    style = load_style_config(ROOT / "styles" / f"{edition}.yaml")
    assert pair_passes_profile(pair(separation, 6.0, secondary), style.double_stars) is expected


def test_delta_magnitude_filter_uses_separation_bands_and_allows_unknown() -> None:
    style = load_style_config(ROOT / "styles" / "standard.yaml").double_stars
    assert pair_passes_delta_magnitude(pair(1.9, 5.0, 8.0), style)
    assert not pair_passes_delta_magnitude(pair(1.9, 5.0, 8.1), style)
    assert pair_passes_delta_magnitude(pair(2.0, 5.0, 10.0), style)
    assert not pair_passes_delta_magnitude(pair(4.9, 5.0, 10.1), style)
    assert pair_passes_delta_magnitude(pair(1.0, None, 11.0), style)
    assert pair_passes_delta_magnitude(pair(1.0, 5.0, None), style)
