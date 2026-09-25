"""Tests for label construction."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.constellations import ConstellationSegment
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.catalog.outlines import NebulaOutline
from nightsky_atlas.catalog.selection import SelectionPolicy
from nightsky_atlas.catalog.star_names import StarName
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.labels import (
    build_constellation_labels,
    build_dso_labels,
    build_labels,
    build_star_labels,
    constellation_label_anchors,
    label_priority,
)
from nightsky_atlas.layout.selection import select_labels
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test",
    center_ra_deg=187.5,
    center_dec_deg=12.0,
    width_deg=20.0,
    height_deg=14.0,
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)


def make_dso(
    object_id: str,
    *,
    object_type: DsoType = DsoType.GALAXY,
    cross_ids: tuple[str, ...] = (),
    common_name: str | None = None,
    magnitude: float | None = 8.0,
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=187.6,
        dec_deg=12.1,
        object_type=object_type,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=magnitude,
        cross_ids=cross_ids,
        common_name=common_name,
    )


def test_priority_messier_is_mandatory() -> None:
    assert label_priority(make_dso("NGC4486", cross_ids=("M87",))) == (100, True)


def test_priority_bright_dso_high_but_optional() -> None:
    assert label_priority(make_dso("X", magnitude=8.0))[1] is False


def test_contour_alias_keeps_one_catalogue_label() -> None:
    dso = make_dso(
        "NGC7000",
        object_type=DsoType.BRIGHT_NEBULA,
        cross_ids=("C 020",),
    )
    outline = NebulaOutline(
        id="outline:C020",
        dso_id="C020",
        points=((186.5, 11.0), (188.5, 11.0), (188.5, 13.0)),
        provenance=Provenance(catalogue="TEST", source_id="outline:C020"),
    )
    scene = build_scene(CHART, (), (dso,), nebula_outlines=(outline,))
    labels = build_dso_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE)

    assert [label.id for label in labels] == ["label:dso:NGC7000"]
    assert label_priority(make_dso("Y", magnitude=13.0))[1] is False


def test_build_dso_labels() -> None:
    dsos = [
        make_dso("NGC4486", cross_ids=("M87",)),
        make_dso("NGC9999", magnitude=11.0),
    ]
    scene = build_scene(CHART, (), dsos)
    labels = build_dso_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE)
    by_id = {label.id: label for label in labels}
    assert set(by_id) == {"label:dso:NGC4486", "label:dso:NGC9999"}
    messier = by_id["label:dso:NGC4486"]
    assert messier.text == "M87"
    assert messier.mandatory is True
    assert messier.font_weight == "bold"
    assert messier.font_size_pt == pytest.approx(
        STYLE.label.dso_labels.normal_size_pt * STYLE.label.dso_labels.messier.size_factor
    )
    placement = STYLE.label.dso_placement
    near_count = sum(
        gap < placement.outer_candidate_start_gap_mm
        for gap in placement.candidate_edge_gaps_mm
    )
    outer_count = len(placement.candidate_edge_gaps_mm) - near_count
    assert len(messier.candidates) == (
        placement.candidate_directions * near_count
        + placement.outer_candidate_directions * outer_count
    )
    assert messier.candidates[0].id == "label:dso:NGC4486:N"
    assert messier.selected_candidate_id == messier.candidates[0].id
    ordinary = by_id["label:dso:NGC9999"]
    assert ordinary.text == "9999"
    assert ordinary.mandatory is False
    assert ordinary.font_weight == "normal"
    assert ordinary.font_size_pt == pytest.approx(STYLE.label.dso_labels.normal_size_pt)
    assert ordinary.selected_candidate_id == ordinary.candidates[0].id


def make_star(star_id: str, magnitude: float, *, hip_id: str | None) -> Star:
    return Star(
        id=star_id,
        ra_deg=187.6,
        dec_deg=12.1,
        magnitude=magnitude,
        provenance=Provenance(catalogue="TEST", source_id=star_id),
        hip_id=hip_id,
    )


STAR_NAMES = {
    12345: StarName(
        hip_number=12345,
        name="Teststar",
        curated_name="Teststar",
        proper_name_tier="core",
        constellation="Cyg",
    ),
    23456: StarName(hip_number=23456, bayer="α", constellation="Lyr"),
    34567: StarName(hip_number=34567, flamsteed="50", constellation="Cyg"),
}


def test_build_star_labels_uses_common_name() -> None:
    star = make_star("HIP 12345", 2.0, hip_id="HIP 12345")
    scene = build_scene(CHART, [star])
    labels = build_star_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE, STAR_NAMES)
    assert len(labels) == 1
    assert labels[0].id == "label:star:HIP 12345"
    assert labels[0].text == "Teststar"
    assert labels[0].mandatory is True
    assert labels[0].candidates[0].id == "label:star:HIP 12345:N"


def test_build_star_labels_bayer_fallback_and_optional() -> None:
    star = make_star("HIP 23456", 4.5, hip_id="HIP 23456")
    scene = build_scene(CHART, [star])
    labels = build_star_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE, STAR_NAMES)
    assert labels[0].text == "α"
    assert labels[0].mandatory is False


def test_build_star_labels_skips_unnamed_or_faint_or_unmatched() -> None:
    stars = [
        make_star("HIP 12345", STYLE.star.label_magnitude_limit + 1.0, hip_id="HIP 12345"),
        make_star("TYC 1-1-1", 2.0, hip_id=None),
        make_star("HIP 99999", 2.0, hip_id="HIP 99999"),
    ]
    scene = build_scene(CHART, stars)
    labels = build_star_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE, STAR_NAMES)
    assert labels == ()


def test_build_labels_combines_star_and_dso() -> None:
    star = make_star("HIP 34567", 3.0, hip_id="HIP 34567")
    scene = build_scene(CHART, [star], [make_dso("NGC4486", cross_ids=("M87",))])
    labels = build_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE, STAR_NAMES)
    assert {label.id for label in labels} == {
        "label:dso:NGC4486",
        "label:star:HIP 34567",
    }


def test_build_labels_without_names_is_dso_only() -> None:
    scene = build_scene(CHART, [make_star("HIP 12345", 2.0, hip_id="HIP 12345")])
    labels = build_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE, None)
    assert labels == ()


def test_constellation_names_are_optional_layout_labels() -> None:
    segments = [
        ConstellationSegment(
            id=f"ori:{index}",
            ra1_deg=185.0 + index,
            dec1_deg=10.0,
            ra2_deg=186.0 + index,
            dec2_deg=11.0,
            provenance=Provenance(catalogue="TEST", source_id=f"ori:{index}"),
            constellation_id="Ori",
        )
        for index in range(STYLE.constellation.names.min_segments)
    ]
    scene = build_scene(CHART, (), constellation_lines=segments)
    transform = PageTransform(chart=CHART, page=PAGE)

    labels = build_constellation_labels(scene, transform, STYLE)

    assert len(labels) == 1
    label = labels[0]
    assert label.id == "label:constellation:Ori"
    assert label.target_id == "constellation:Ori"
    assert label.text == "ORION"
    assert label.mandatory is False
    assert label.font_size_pt == STYLE.constellation.names.font_size_pt
    assert label.candidates[0].id == "label:constellation:Ori:N"
    anchor = constellation_label_anchors(scene, transform, STYLE)["constellation:Ori"]
    assert transform.chart_rect.left_mm <= anchor.x_mm <= transform.chart_rect.right_mm
    assert transform.chart_rect.top_mm <= anchor.y_mm <= transform.chart_rect.bottom_mm
    assert select_labels(labels, scene, transform, STYLE) == labels


def test_build_dso_labels_uses_metadata_priority() -> None:
    policy = SelectionPolicy(forced_lists=frozenset({"herschel400"}))
    scene = build_scene(
        CHART,
        (),
        [make_dso("NGC0869", magnitude=13.0)],
        observing_index={"NGC869": frozenset({"herschel400"})},
        selection_policy=policy,
    )
    labels = build_dso_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE)
    assert len(labels) == 1
    assert labels[0].priority == scene.deep_sky_objects[0].metadata.label_priority
    assert labels[0].mandatory is False


def test_dso_label_magnitude_limit_omits_faint_object() -> None:
    assert STYLE.label.dso_label_magnitude_limit is not None
    faint = STYLE.label.dso_label_magnitude_limit + 0.5
    scene = build_scene(
        CHART,
        (),
        [replace(make_dso("NGC9999", magnitude=faint), object_type=DsoType.GALAXY_CLUSTER)],
    )
    labels = build_dso_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE)
    assert labels == ()


def test_rendered_faint_galaxy_is_exempt_from_label_magnitude_limit() -> None:
    assert STYLE.label.dso_label_magnitude_limit is not None
    faint = STYLE.label.dso_label_magnitude_limit + 0.5
    scene = build_scene(CHART, (), [make_dso("NGC9999", magnitude=faint)])

    labels = build_dso_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE)

    assert {label.id for label in labels} == {"label:dso:NGC9999"}


def test_dso_label_magnitude_limit_keeps_mandatory_faint_object() -> None:
    faint = (STYLE.label.dso_label_magnitude_limit or 0.0) + 0.5
    dso = make_dso("NGC4486", cross_ids=("M87",), magnitude=faint)
    scene = build_scene(CHART, (), [dso])
    labels = build_dso_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE)
    assert {label.id for label in labels} == {"label:dso:NGC4486"}


def test_dso_label_magnitude_limit_exempts_observing_list_member() -> None:
    policy = SelectionPolicy(forced_lists=frozenset({"herschel400"}))
    faint = (STYLE.label.dso_label_magnitude_limit or 0.0) + 0.5
    scene = build_scene(
        CHART,
        (),
        [make_dso("NGC0869", magnitude=faint)],
        observing_index={"NGC869": frozenset({"herschel400"})},
        selection_policy=policy,
    )
    labels = build_dso_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE)
    assert {label.id for label in labels} == {"label:dso:NGC0869"}
    assert labels[0].text == "869"
    assert labels[0].font_weight == "bold"
