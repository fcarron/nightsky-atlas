from __future__ import annotations

import math
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.systems import StarSystem
from nightsky_atlas.catalog.wds_selection import pair_passes_profile

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
        ("pocket", 0.5, 10.5, True),
        ("pocket", 0.49, 8.0, False),
        ("pocket", 20.0, 10.5, True),
        ("pocket", 20.0, 10.6, False),
        ("pocket", 30.0, 10.5, True),
        ("pocket", 30.01, 8.5, True),
        ("pocket", 100.0, 8.5, True),
        ("pocket", 100.0, 8.6, False),
        ("pocket", 180.0, 8.5, True),
        ("pocket", 200.0, 8.5, True),
        ("pocket", 201.0, 8.0, False),
        ("standard", 0.5, 11.5, True),
        ("standard", 20.0, 11.5, True),
        ("standard", 20.0, 11.6, False),
        ("standard", 30.0, 11.5, True),
        ("standard", 100.0, 9.5, True),
        ("standard", 100.0, 9.6, False),
        ("standard", 150.0, 9.0, True),
        ("standard", 150.0, 9.1, False),
        ("standard", 200.0, 9.0, True),
        ("standard", 200.1, 8.0, False),
        ("deep", 0.5, 12.5, True),
        ("deep", 20.0, 12.5, True),
        ("deep", 20.0, 12.6, False),
        ("deep", 30.0, 12.5, True),
        ("deep", 100.0, 10.5, True),
        ("deep", 100.0, 10.6, False),
        ("deep", 150.0, 10.0, True),
        ("deep", 150.0, 10.1, False),
        ("deep", 200.0, 10.0, True),
        ("deep", 250.0, 9.0, True),
        ("deep", 250.0, 9.1, False),
        ("deep", 300.0, 9.0, True),
        ("deep", 301.0, 8.0, False),
    ],
)
def test_edition_selection_limits(
    edition: str, separation: float, secondary: float, expected: bool
) -> None:
    style = load_style_config(ROOT / "styles" / f"{edition}.yaml")
    assert pair_passes_profile(pair(separation, 6.0, secondary), style.double_stars) is expected


def test_high_delta_magnitude_pair_is_not_excluded() -> None:
    style = load_style_config(ROOT / "styles" / "standard.yaml")
    high_delta_pair = pair(1.0, 2.0, 11.0)
    assert high_delta_pair.delta_magnitude == pytest.approx(9.0)
    assert pair_passes_profile(high_delta_pair, style.double_stars)


def test_selection_hierarchy_is_nested_across_all_configured_bands() -> None:
    profiles = {
        edition: load_style_config(ROOT / "styles" / f"{edition}.yaml").double_stars
        for edition in ("pocket", "standard", "deep", "eyepiece", "eyepiece_deep")
    }
    bounds = sorted(
        {limit.max_sep_arcsec for profile in profiles.values() for limit in profile.limits}
    )
    separations = {0.49, 0.5}
    lower = 0.5
    for bound in bounds:
        if bound > lower:
            separations.add((lower + bound) / 2.0)
        separations.update((bound, math.nextafter(bound, math.inf)))
        lower = bound
    separations.add(lower + 1.0)

    magnitude_limits = {
        limit.max_secondary_mag for profile in profiles.values() for limit in profile.limits
    }
    magnitudes = {7.0, 14.0}
    for limit in magnitude_limits:
        magnitudes.update((limit, math.nextafter(limit, math.inf)))

    for separation in sorted(separations):
        for magnitude in sorted(magnitudes):
            selected = {
                edition: pair_passes_profile(pair(separation, 4.0, magnitude), profile)
                for edition, profile in profiles.items()
            }
            assert not selected["pocket"] or selected["standard"]
            assert not selected["standard"] or selected["deep"]
            assert selected["eyepiece"] == selected["deep"]
            assert selected["eyepiece_deep"] == selected["deep"]
