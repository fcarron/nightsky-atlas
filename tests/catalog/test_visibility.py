"""Tests for per-type deep-sky visibility evaluation."""

from __future__ import annotations

from dataclasses import replace

from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.selection import SelectionPolicy, select_dso
from nightsky_atlas.catalog.visibility import (
    DEFAULT_LIMITS,
    VisibilityAssessment,
    evaluate_visibility,
    evaluator_for,
)


def make_dso(
    object_id: str = "TEST",
    *,
    object_type: DsoType = DsoType.GALAXY,
    magnitude: float | None = None,
    major_axis_arcmin: float | None = None,
    minor_axis_arcmin: float | None = None,
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=object_type,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=magnitude,
        major_axis_arcmin=major_axis_arcmin,
        minor_axis_arcmin=minor_axis_arcmin,
    )


def test_every_object_type_has_an_evaluator() -> None:
    for object_type in DsoType:
        assessment = evaluator_for(object_type).evaluate(
            make_dso(object_type=object_type), DEFAULT_LIMITS
        )
        assert isinstance(assessment, VisibilityAssessment)


def test_galaxy_visible_by_surface_brightness() -> None:
    galaxy = make_dso(
        magnitude=13.8,
        major_axis_arcmin=1.5,
        minor_axis_arcmin=1.5,
    )
    assert galaxy.surface_brightness_mag_arcsec2() < DEFAULT_LIMITS.surface_brightness_limit
    assessment = evaluate_visibility(galaxy)
    assert assessment.visible is True
    assert "too-faint" not in assessment.reasons


def test_galaxy_rejected_when_faint_and_low_surface_brightness() -> None:
    galaxy = make_dso(
        magnitude=15.0,
        major_axis_arcmin=3.0,
        minor_axis_arcmin=3.0,
    )
    assert galaxy.surface_brightness_mag_arcsec2() > DEFAULT_LIMITS.surface_brightness_limit
    assessment = evaluate_visibility(galaxy)
    assert assessment.visible is False
    assert "too-faint" in assessment.reasons


def test_galaxy_tiny_and_faint_is_dropped() -> None:
    galaxy = make_dso(
        magnitude=13.0,
        major_axis_arcmin=0.4,
        minor_axis_arcmin=0.4,
    )
    assessment = evaluate_visibility(galaxy)
    assert assessment.visible is False
    assert "below-minimum-size" in assessment.reasons


def test_galaxy_tiny_but_bright_is_kept() -> None:
    galaxy = make_dso(
        magnitude=10.0,
        major_axis_arcmin=0.4,
        minor_axis_arcmin=0.4,
    )
    assessment = evaluate_visibility(galaxy)
    assert assessment.visible is True


def test_galaxy_without_photometry_is_not_visible() -> None:
    galaxy = make_dso(major_axis_arcmin=2.0, minor_axis_arcmin=2.0)
    assert galaxy.surface_brightness_mag_arcsec2() is None
    assessment = evaluate_visibility(galaxy)
    assert assessment.visible is False
    assert "too-faint" in assessment.reasons


def test_galaxy_without_any_data_reports_no_photometry() -> None:
    assessment = evaluate_visibility(make_dso())
    assert assessment.visible is False
    assert "no-photometry" in assessment.reasons


def test_open_cluster_uses_size_when_magnitude_missing() -> None:
    large = make_dso(object_type=DsoType.OPEN_CLUSTER, major_axis_arcmin=15.0)
    small = make_dso(object_type=DsoType.OPEN_CLUSTER, major_axis_arcmin=0.3)
    assert evaluate_visibility(large).visible is True
    assert evaluate_visibility(small).visible is False


def test_planetary_nebula_has_no_minimum_size_penalty() -> None:
    tiny = make_dso(object_type=DsoType.PLANETARY_NEBULA, magnitude=12.0)
    assert evaluate_visibility(tiny).visible is True


def test_globular_cluster_kept_by_magnitude_without_size() -> None:
    globular = make_dso(object_type=DsoType.GLOBULAR_CLUSTER, magnitude=9.0)
    assert evaluate_visibility(globular).visible is True


def test_star_and_double_star_are_excluded() -> None:
    for object_type in (DsoType.STAR, DsoType.DOUBLE_STAR):
        assessment = evaluate_visibility(
            make_dso(object_type=object_type, magnitude=5.0)
        )
        assert assessment.visible is False
        assert "excluded-type" in assessment.reasons


def test_brighter_galaxy_scores_higher() -> None:
    bright = make_dso(
        magnitude=10.0, major_axis_arcmin=2.0, minor_axis_arcmin=2.0
    )
    faint = make_dso(
        magnitude=13.5, major_axis_arcmin=2.0, minor_axis_arcmin=2.0
    )
    assert evaluate_visibility(bright).score > evaluate_visibility(faint).score


def test_forced_object_is_rendered_despite_invisible_assessment() -> None:
    galaxy = make_dso(
        "NGC9999",
        magnitude=15.0,
        major_axis_arcmin=0.3,
        minor_axis_arcmin=0.3,
    )
    policy = SelectionPolicy(forced_lists=frozenset({"herschel400"}))
    index = {"NGC9999": frozenset({"herschel400"})}
    metadata = select_dso(galaxy, index=index, policy=policy)
    assert metadata.visible is False
    assert metadata.forced is True
    assert metadata.visual_score >= 0.0


def test_include_all_renders_every_dso_type() -> None:
    limits = replace(DEFAULT_LIMITS, include_all=True)
    faint = make_dso(
        object_type=DsoType.GALAXY,
        magnitude=18.0,
        major_axis_arcmin=0.2,
        minor_axis_arcmin=0.2,
    )
    no_photometry = make_dso(object_type=DsoType.GALAXY)
    for dso in (faint, no_photometry):
        assessment = evaluate_visibility(dso, limits)
        assert assessment.visible is True
        assert assessment.reasons == ("include-all",)


def test_include_all_keeps_star_entries_excluded() -> None:
    limits = replace(DEFAULT_LIMITS, include_all=True)
    for object_type in (DsoType.STAR, DsoType.DOUBLE_STAR):
        assessment = evaluate_visibility(
            make_dso(object_type=object_type, magnitude=5.0), limits
        )
        assert assessment.visible is False
        assert "excluded-type" in assessment.reasons
