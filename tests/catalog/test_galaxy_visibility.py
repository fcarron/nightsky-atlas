"""Tests for the Crumey-based galaxy visibility classification."""

from __future__ import annotations

import math
from collections import Counter
from pathlib import Path

import pytest

from nightsky_atlas.catalog.galaxy_visibility import (
    APERTURES_MM,
    GalaxyContourClass,
    VisibilityConditions,
    classify_galaxy_contour,
    crumey_required_contrast,
    effective_visual_surface_brightness,
    ellipse_area_sr,
    estimate_galaxy_visibility,
    mean_mu_b_within_fraction,
    morphology_priors,
    score_galaxy_at_aperture,
    sky_luminance_cd_m2,
    solve_x25,
    visibility_score,
)
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.openngc import iter_openngc_objects, load_sample_dsos
from nightsky_atlas.catalog.selection import SelectionPolicy, select_dso

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_FIXTURE = REPO_ROOT / "data" / "fixtures" / "openngc" / "visibility_reference.csv"
RAW_NGC = REPO_ROOT / "data" / "raw" / "openngc" / "NGC.csv"
RAW_ADDENDUM = REPO_ROOT / "data" / "raw" / "openngc" / "addendum.csv"


def make_galaxy(object_id: str = "NGC0001", **overrides: object) -> DeepSkyObject:
    fields: dict[str, object] = {
        "id": object_id,
        "ra_deg": 10.0,
        "dec_deg": 20.0,
        "object_type": DsoType.GALAXY,
        "provenance": Provenance(catalogue="TEST", source_id=object_id),
        "magnitude": 12.0,
        "major_axis_arcmin": 2.0,
        "minor_axis_arcmin": 1.0,
        "mean_surface_brightness_mag_arcsec2": 22.5,
        "hubble_type": "Sb",
    }
    fields.update(overrides)
    return DeepSkyObject(**fields)  # type: ignore[arg-type]


def test_sky_luminance_conversion() -> None:
    assert sky_luminance_cd_m2(21.5) == pytest.approx(2.70e-4, rel=0.01)


def test_ellipse_area_and_units() -> None:
    area = ellipse_area_sr(60.0, 60.0)
    expected = (math.pi / 4.0 * 60.0 * 60.0) * (math.pi / (180.0 * 60.0)) ** 2
    assert area == pytest.approx(expected)
    assert ellipse_area_sr(60.0, 60.0, 0.5) == pytest.approx(area * 0.25)
    single = ellipse_area_sr(1.0, 1.0)
    assert single == pytest.approx((math.pi / 4.0) * (math.pi / (180.0 * 60.0)) ** 2)


@pytest.mark.parametrize(
    ("hubble", "n", "b_minus_v"),
    [
        ("E", 4.0, 0.90),
        ("E-S0", 4.0, 0.90),
        ("S0", 3.0, 0.85),
        ("S0-a", 3.0, 0.85),
        ("Sa", 2.5, 0.80),
        ("SABb", 2.0, 0.75),
        ("SBbc", 1.5, 0.65),
        ("Sc", 1.2, 0.55),
        ("Scd", 1.0, 0.45),
        ("IB", 1.0, 0.45),
    ],
)
def test_morphology_priors(hubble: str, n: float, b_minus_v: float) -> None:
    prior = morphology_priors(hubble)
    assert prior.n == pytest.approx(n)
    assert prior.b_minus_v == pytest.approx(b_minus_v)
    assert prior.uncertain is False
    assert prior.missing is False


def test_morphology_uncertain_uses_base_type() -> None:
    uncertain = morphology_priors("S?")
    assert uncertain.uncertain is True
    assert uncertain.missing is True
    assert (uncertain.n, uncertain.b_minus_v) == pytest.approx((1.5, 0.70))

    elliptical = morphology_priors("E?")
    assert elliptical.uncertain is True
    assert elliptical.n == pytest.approx(4.0)


@pytest.mark.parametrize("hubble", [None, "", "   "])
def test_morphology_missing(hubble: str | None) -> None:
    prior = morphology_priors(hubble)
    assert prior.missing is True
    assert prior.uncertain is True
    assert (prior.n, prior.b_minus_v) == pytest.approx((1.5, 0.70))


def test_bar_forms_follow_base_class() -> None:
    assert morphology_priors("SBb").n == pytest.approx(2.0)
    assert morphology_priors("SABb").n == pytest.approx(2.0)
    assert morphology_priors("SBbc").n == pytest.approx(1.5)
    assert morphology_priors("SBc").n == pytest.approx(1.2)
    # Sbc and SBc must stay distinct despite looking similar when uppercased.
    assert morphology_priors("Sbc").n == pytest.approx(1.5)


def test_effective_visual_surface_brightness_formula() -> None:
    assert effective_visual_surface_brightness(23.0, 0.7) == pytest.approx(22.3)
    assert effective_visual_surface_brightness(23.0, 1.0) == pytest.approx(
        23.0 - 1.0 + 0.27 * 0.3
    )


def test_colour_validation_accepts_and_rejects() -> None:
    from nightsky_atlas.catalog.galaxy_visibility import _resolve_profile

    accepted = _resolve_profile(
        make_galaxy(b_magnitude=13.0, v_magnitude=12.0, hubble_type="Sb")
    )
    assert accepted is not None
    assert accepted.colour_derived is False
    assert accepted.b_minus_v == pytest.approx(1.0)

    rejected = _resolve_profile(
        make_galaxy(b_magnitude=13.5, v_magnitude=12.0, hubble_type="Sb")
    )
    assert rejected is not None
    assert rejected.colour_derived is True
    assert rejected.b_minus_v == pytest.approx(0.75)

    out_of_range = _resolve_profile(
        make_galaxy(b_magnitude=11.0, v_magnitude=12.0, hubble_type="Sb")
    )
    assert out_of_range is not None
    assert out_of_range.colour_derived is True


def test_solve_x25_boundaries_and_roundtrip() -> None:
    assert solve_x25(1.0, 25.0) is None
    assert solve_x25(1.0, 26.0) is None
    x25 = solve_x25(1.5, 22.5)
    assert x25 is not None and x25 > 0.0
    assert mean_mu_b_within_fraction(22.5, 1.5, x25, 1.0) == pytest.approx(22.5)


def test_fraction_one_returns_mean_surface_brightness() -> None:
    x25 = solve_x25(1.2, 22.0)
    assert x25 is not None
    for fraction in (0.25, 0.5):
        value = mean_mu_b_within_fraction(22.0, 1.2, x25, fraction)
        assert value <= 22.0  # a peaked inner aperture is brighter or equal
    assert mean_mu_b_within_fraction(22.0, 1.2, x25, 1.0) == pytest.approx(22.0)


def test_zero_background_clamp() -> None:
    area = ellipse_area_sr(1.0, 1.0)
    very_dark = crumey_required_contrast(
        area, 100.0, 1.0, VisibilityConditions(sky_mag_arcsec2=30.0)
    )
    darker = crumey_required_contrast(
        area, 100.0, 1.0, VisibilityConditions(sky_mag_arcsec2=40.0)
    )
    assert very_dark == pytest.approx(darker)


def test_classification_boundaries_are_exact() -> None:
    assert (
        classify_galaxy_contour({100: -0.25, 200: -5.0, 400: -5.0})
        == GalaxyContourClass.BOLD
    )
    assert (
        classify_galaxy_contour({100: -0.250001, 200: -0.25, 400: -5.0})
        == GalaxyContourClass.NORMAL
    )
    assert (
        classify_galaxy_contour({100: -1.0, 200: -0.250001, 400: -0.25})
        == GalaxyContourClass.FINE
    )
    assert (
        classify_galaxy_contour({100: -1.0, 200: -1.0, 400: -0.250001})
        == GalaxyContourClass.DOTTED
    )
    assert classify_galaxy_contour({}) == GalaxyContourClass.UNCLASSIFIED


def test_visibility_score_is_magnitude_difference() -> None:
    assert visibility_score(1.0, 1.0) == pytest.approx(0.0)
    assert visibility_score(2.0, 1.0) == pytest.approx(2.5 * math.log10(2.0))


def test_missing_photometry_is_unclassified() -> None:
    galaxy = make_galaxy(
        mean_surface_brightness_mag_arcsec2=None, b_magnitude=None, v_magnitude=None
    )
    result = estimate_galaxy_visibility(galaxy)
    assert result.contour_class == GalaxyContourClass.UNCLASSIFIED
    assert result.surface_brightness_source == "unavailable"
    assert "missing_photometry" in result.confidence_reasons
    assert score_galaxy_at_aperture(galaxy, 100.0) is None


def test_missing_major_axis_is_unclassified() -> None:
    result = estimate_galaxy_visibility(make_galaxy(major_axis_arcmin=None))
    assert result.contour_class == GalaxyContourClass.UNCLASSIFIED
    assert "missing_major_axis" in result.confidence_reasons


def test_missing_minor_axis_uses_major_and_reduces_confidence() -> None:
    result = estimate_galaxy_visibility(make_galaxy(minor_axis_arcmin=None))
    assert result.contour_class != GalaxyContourClass.UNCLASSIFIED
    assert "missing_minor_axis" in result.confidence_reasons


def test_surface_brightness_fallbacks() -> None:
    from_b = estimate_galaxy_visibility(
        make_galaxy(mean_surface_brightness_mag_arcsec2=None, b_magnitude=13.0)
    )
    assert from_b.surface_brightness_source == "derived_from_b_mag"

    from_v = estimate_galaxy_visibility(
        make_galaxy(
            mean_surface_brightness_mag_arcsec2=None,
            b_magnitude=None,
            v_magnitude=13.0,
        )
    )
    assert from_v.surface_brightness_source == "derived_from_v_mag_and_colour_prior"


def test_contour_class_is_independent_of_label_priority() -> None:
    bright = make_galaxy(
        "NGC0001",
        hubble_type="E",
        magnitude=12.0,
        major_axis_arcmin=3.0,
        minor_axis_arcmin=2.0,
        mean_surface_brightness_mag_arcsec2=21.0,
    )
    faint = make_galaxy(
        "NGC0002",
        hubble_type="E",
        magnitude=12.0,
        major_axis_arcmin=0.6,
        minor_axis_arcmin=0.5,
        mean_surface_brightness_mag_arcsec2=24.8,
    )
    policy = SelectionPolicy()
    first = select_dso(bright, policy=policy)
    second = select_dso(faint, policy=policy)
    assert first.galaxy_contour_class == GalaxyContourClass.BOLD
    assert second.galaxy_contour_class == GalaxyContourClass.DOTTED
    assert first.label_priority == second.label_priority


def test_non_galaxy_has_no_contour_class() -> None:
    globular = make_galaxy(
        "NGC0003",
        object_type=DsoType.GLOBULAR_CLUSTER,
        magnitude=8.0,
        mean_surface_brightness_mag_arcsec2=None,
    )
    assert select_dso(globular, policy=SelectionPolicy()).galaxy_contour_class is None


REFERENCE_OBJECTS: dict[str, tuple[tuple[float, float, float], str]] = {
    "NGC6207": ((0.49, 1.25, 1.62), "bold"),
    "IC4617": ((-2.56, -1.53, -1.00), "dotted"),
    "NGC7331": ((1.15, 1.73, 2.01), "bold"),
    "NGC7317": ((-1.14, -0.03, 0.57), "normal"),
    "NGC7319": ((-1.30, -0.47, -0.06), "fine"),
    "NGC7320": ((-1.06, -0.37, -0.04), "fine"),
    "NGC7320C": ((-3.11, -2.17, -1.74), "dotted"),
}


def test_reference_objects_match_openngc() -> None:
    by_id = {obj.id: obj for obj in load_sample_dsos(REFERENCE_FIXTURE)}
    for name, (expected_scores, expected_class) in REFERENCE_OBJECTS.items():
        result = estimate_galaxy_visibility(by_id[name])
        for aperture, expected in zip(APERTURES_MM, expected_scores, strict=True):
            score = result.by_aperture[int(aperture)].score
            assert score == pytest.approx(expected, abs=0.03), name
        assert result.contour_class.value == expected_class, name


@pytest.mark.skipif(
    not (RAW_NGC.exists() and RAW_ADDENDUM.exists()),
    reason="raw OpenNGC catalogue not available",
)
@pytest.mark.integration
def test_full_catalogue_counts() -> None:
    objects = [
        obj
        for obj in iter_openngc_objects([RAW_NGC, RAW_ADDENDUM])
        if obj.object_type == DsoType.GALAXY
    ]
    counts: Counter[str] = Counter(
        estimate_galaxy_visibility(obj).contour_class.value for obj in objects
    )
    classified = sum(counts[value] for value in ("bold", "normal", "fine", "dotted"))
    assert counts["unclassified"] == len(objects) - classified
    assert classified > 10_000
    assert counts["unclassified"] < 100
    assert all(counts[value] > 0 for value in ("bold", "normal", "fine", "dotted"))
