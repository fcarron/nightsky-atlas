"""Tests for the central label-priority scale and tiers."""

from __future__ import annotations

from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.catalog.priority import (
    BRIGHT_DSO_PRIORITY,
    COMMON_NAME_PRIORITY,
    HERSCHEL_PRIORITY,
    HIGH_TIER_MIN,
    IMPORTANT_HERSCHEL_PRIORITY,
    MEDIUM_TIER_MIN,
    MESSIER_PRIORITY,
    ORDINARY_DSO_PRIORITY,
    STAR_BAYER_PRIORITY,
    STAR_DESIGNATION_PRIORITY,
    STAR_FLAMSTEED_PRIORITY,
    STAR_MAIN_BAYER_PRIORITY,
    STAR_NAME_PRIORITY,
    LabelPriorityTier,
    base_label_priority,
    dso_label_priority,
    star_label_priority,
    tier_for,
)
from nightsky_atlas.catalog.star_names import StarName


def make_dso(
    object_id: str,
    *,
    magnitude: float | None = 12.0,
    cross_ids: tuple[str, ...] = (),
    common_name: str | None = None,
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=magnitude,
        cross_ids=cross_ids,
        common_name=common_name,
    )


def make_star(magnitude: float) -> Star:
    return Star(
        id="X",
        ra_deg=187.5,
        dec_deg=12.0,
        magnitude=magnitude,
        provenance=Provenance(catalogue="TEST", source_id="X"),
    )


def test_tier_boundaries() -> None:
    assert tier_for(HIGH_TIER_MIN) is LabelPriorityTier.HIGH
    assert tier_for(HIGH_TIER_MIN - 1) is LabelPriorityTier.MEDIUM
    assert tier_for(MEDIUM_TIER_MIN) is LabelPriorityTier.MEDIUM
    assert tier_for(MEDIUM_TIER_MIN - 1) is LabelPriorityTier.LOW


def test_base_label_priority_unchanged() -> None:
    assert base_label_priority(make_dso("NGC4486", cross_ids=("M87",))) == (
        MESSIER_PRIORITY,
        True,
    )
    assert base_label_priority(make_dso("X", common_name="Named")) == (
        COMMON_NAME_PRIORITY,
        True,
    )
    assert base_label_priority(make_dso("Y", magnitude=8.0)) == (
        BRIGHT_DSO_PRIORITY,
        False,
    )
    assert base_label_priority(make_dso("Z", magnitude=13.0)) == (
        ORDINARY_DSO_PRIORITY,
        False,
    )


def test_dso_label_priority_ranks_by_importance() -> None:
    assert dso_label_priority(make_dso("NGC4486", cross_ids=("M87",))) == MESSIER_PRIORITY
    assert (
        dso_label_priority(make_dso("NGC0224", common_name="Andromeda Galaxy"))
        == COMMON_NAME_PRIORITY
    )
    # A forced Herschel 400 object is split by its visual score.
    assert (
        dso_label_priority(
            make_dso("NGC4472"), forced=True, visual_score=80.0
        )
        == IMPORTANT_HERSCHEL_PRIORITY
    )
    assert (
        dso_label_priority(
            make_dso("NGC4472"), forced=True, visual_score=30.0
        )
        == HERSCHEL_PRIORITY
    )
    # An ordinary bright object is still medium; a faint one is low.
    assert (
        dso_label_priority(make_dso("NGC4565", magnitude=9.0))
        == BRIGHT_DSO_PRIORITY
    )
    assert (
        dso_label_priority(make_dso("NGC4565", magnitude=13.0))
        == ORDINARY_DSO_PRIORITY
    )


def test_star_label_priority_prefers_name_then_bayer() -> None:
    name = StarName(hip_number=1, name="Vega")
    bayer = StarName(hip_number=2, bayer="α", constellation="Lyr")
    flamsteed = StarName(hip_number=3, flamsteed="50", constellation="Cyg")
    variable = StarName(hip_number=4, variable="RR", constellation="Lyr")

    assert star_label_priority(make_star(2.0), name) == (STAR_NAME_PRIORITY, True)
    # A bright Bayer star is a constellation main star.
    assert star_label_priority(make_star(2.5), bayer) == (
        STAR_MAIN_BAYER_PRIORITY,
        False,
    )
    assert star_label_priority(make_star(4.5), bayer) == (STAR_BAYER_PRIORITY, False)
    assert star_label_priority(make_star(4.5), flamsteed) == (
        STAR_FLAMSTEED_PRIORITY,
        False,
    )
    assert star_label_priority(make_star(4.5), variable) == (
        STAR_DESIGNATION_PRIORITY,
        False,
    )