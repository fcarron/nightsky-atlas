"""Tests for label construction."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.labels import build_dso_labels, display_name, label_priority
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
    cross_ids: tuple[str, ...] = (),
    common_name: str | None = None,
    magnitude: float | None = 8.0,
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=187.6,
        dec_deg=12.1,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=magnitude,
        cross_ids=cross_ids,
        common_name=common_name,
    )


def test_display_name_prefers_messier() -> None:
    dso = make_dso("NGC4486", cross_ids=("M87",), common_name="Virgo A")
    assert display_name(dso) == "M87"


def test_display_name_prefers_common_name_over_id() -> None:
    dso = make_dso("NGC0001", common_name="Something")
    assert display_name(dso) == "Something"


def test_display_name_falls_back_to_id() -> None:
    assert display_name(make_dso("NGC0001")) == "NGC0001"


def test_priority_messier_is_mandatory() -> None:
    assert label_priority(make_dso("NGC4486", cross_ids=("M87",))) == (100, True)


def test_priority_bright_dso_mandatory_ordinary_optional() -> None:
    assert label_priority(make_dso("X", magnitude=8.0))[1] is True
    assert label_priority(make_dso("Y", magnitude=13.0))[1] is False


def test_build_dso_labels() -> None:
    dsos = [
        make_dso("NGC4486", cross_ids=("M87",)),
        make_dso("NGC9999", magnitude=14.0),
    ]
    scene = build_scene(CHART, (), dsos)
    labels = build_dso_labels(scene, PageTransform(chart=CHART, page=PAGE), STYLE)
    by_id = {label.id: label for label in labels}
    assert set(by_id) == {"label:dso:NGC4486", "label:dso:NGC9999"}
    assert by_id["label:dso:NGC4486"].text == "M87"
    assert by_id["label:dso:NGC4486"].mandatory is True
    assert len(by_id["label:dso:NGC4486"].candidates) == 8 * STYLE.label.candidate_rings
    assert by_id["label:dso:NGC4486"].candidates[0].id == "label:dso:NGC4486:N"
    assert by_id["label:dso:NGC9999"].mandatory is False
