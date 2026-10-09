"""Tests for deterministic atlas-index data and pagination."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.config import EditionConfig, load_atlas_config
from nightsky_atlas.atlas.directory import build_chart_directory, build_detail_chart_directory
from nightsky_atlas.atlas.index import build_atlas_index, natural_designation_key
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.catalog.faint_stars import FaintStar
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.catalog.star_names import StarName
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.render.atlas_index import _chart_lines, index_page_count
from nightsky_atlas.scene.models import SceneDso


def _dso(
    identifier: str,
    *,
    ra_deg: float = 10.0,
    constellation: str = "Com",
    cross_ids: tuple[str, ...] = (),
) -> SceneDso:
    dso = DeepSkyObject(
        id=identifier,
        ra_deg=ra_deg,
        dec_deg=20.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance("test", identifier),
        constellation=constellation,
        cross_ids=cross_ids,
    )
    return SceneDso(dso, ChartPoint(0.0, 0.0))


def _chart(identifier: str, ra_deg: float) -> ChartDefinition:
    return ChartDefinition(
        id=identifier,
        atlas_id="standard",
        center_ra_deg=ra_deg,
        center_dec_deg=20.0,
        width_deg=20.0,
        height_deg=20.0,
    )


def test_dso_designations_are_canonical_and_aliases_do_not_duplicate() -> None:
    charts = (_chart("standard-029", 10.0),)
    index = build_atlas_index(
        {"standard-029": (_dso("NGC6205", cross_ids=("M13",)), _dso("NGC4565"), _dso("IC5070"))},
        {},
        charts,
        EditionConfig(name="Standard", code="S"),
    )
    assert [entry.designation for entry in index.dso_entries] == ["M13", "NGC 4565", "IC 5070"]
    assert len(index.dso_entries) == 3


def test_primary_chart_is_nearest_centre_and_secondaries_are_retained() -> None:
    charts = (_chart("standard-040", 10.0), _chart("standard-041", 18.0))
    dso = _dso("NGC4565", ra_deg=11.0)
    index = build_atlas_index(
        {"standard-040": (dso,), "standard-041": (dso,)},
        {},
        charts,
        EditionConfig(name="Standard", code="S"),
    )
    assert index.dso_entries[0].primary_chart == "S040"
    assert index.dso_entries[0].secondary_charts == ("S041",)


def test_constellation_codes_follow_edition_and_footprint_mapping() -> None:
    charts = (_chart("pocket-001", 10.0), _chart("pocket-002", 20.0))
    index = build_atlas_index(
        {},
        {"pocket-001": frozenset({"Vir"}), "pocket-002": frozenset({"Vir", "Ori"})},
        charts,
        EditionConfig(name="Pocket", code="P"),
    )
    assert [(entry.name, entry.chart_ids) for entry in index.constellation_entries] == [
        ("Orion", ("P002",)),
        ("Virgo", ("P001", "P002")),
    ]


def test_natural_sort_and_pagination_are_stable() -> None:
    assert sorted(["M10", "M2", "M1", "NGC 100", "NGC 2"], key=natural_designation_key) == [
        "M1",
        "M2",
        "M10",
        "NGC 2",
        "NGC 100",
    ]
    charts = (_chart("deep-001", 10.0),)
    index = build_atlas_index(
        {"deep-001": tuple(_dso(f"NGC{number}") for number in range(1, 200))},
        {},
        charts,
        EditionConfig(name="Deep", code="D"),
    )
    assert index_page_count(index, PageGeometry(297.0, 210.0, 12.0)) > 2


def test_constellation_chart_references_wrap_between_complete_codes() -> None:
    lines = _chart_lines(tuple(f"S{number:03d}" for number in range(1, 14)), max_characters=20)
    assert lines == (
        "S001, S002, S003",
        "S004, S005, S006",
        "S007, S008, S009",
        "S010, S011, S012",
        "S013",
    )


def test_named_star_index_uses_visible_stars_and_nearest_chart() -> None:
    charts = (_chart("standard-040", 10.0), _chart("standard-041", 18.0))
    star = Star("HIP 123", 11.0, 20.0, 1.0, Provenance("test", "123"), hip_id="HIP 123")
    index = build_atlas_index(
        {},
        {},
        charts,
        EditionConfig(name="Standard", code="S"),
        chart_stars={"standard-040": (star,), "standard-041": (star,)},
        star_names={123: StarName(123, name="Test Star", bayer="α", constellation="Com")},
    )
    assert len(index.named_star_entries) == 1
    entry = index.named_star_entries[0]
    assert (entry.name, entry.designation, entry.primary_chart, entry.secondary_charts) == (
        "Test Star",
        "α Com",
        "S040",
        ("S041",),
    )


def test_faint_stars_are_excluded_from_named_star_index() -> None:
    primary = Star("HIP 123", 11.0, 20.0, 1.0, Provenance("test", "123"), hip_id="HIP 123")
    faint = FaintStar("UCAC4 1", 11.1, 20.1, 12.0)
    index = build_atlas_index(
        {},
        {},
        (_chart("standard-040", 10.0),),
        EditionConfig(name="Standard", code="S"),
        chart_stars={"standard-040": (primary, faint)},
        star_names={123: StarName(123, name="Test Star", constellation="Com")},
    )
    assert [entry.name for entry in index.named_star_entries] == ["Test Star"]


def test_chart_directory_uses_edition_codes_and_published_neighbours() -> None:
    charts = (
        ChartDefinition("deep-001", 10.0, 20.0, 13.5, 9.0, neighbours=(("E", "deep-002"),)),
        ChartDefinition("deep-002", 20.0, 20.0, 13.5, 9.0),
    )
    entries = build_chart_directory(charts, EditionConfig(name="Deep", code="D"))
    assert entries[0].chart_code == "D001"
    assert entries[0].center_ra == "00h40m"
    assert entries[0].field == "13.5° × 9°"
    assert entries[0].neighbours == ("D002",)


def test_detail_directory_codes_and_parent_codes_are_independent_and_linkable() -> None:
    root = Path(__file__).resolve().parents[2]
    atlas = load_atlas_config(root / "atlas" / "standard.yaml")
    details = build_detail_chart_directory(
        atlas.detail_charts,
        chart_definitions(atlas),
        atlas.resolved_edition(),
    )
    assert [entry.chart_code for entry in details] == [f"SD{i:02d}" for i in range(1, 10)]
    assert details[0].parent_chart_code == "S050"
    assert details[0].name == "Virgo Cluster"
    assert details[0].scale_mm_per_degree == 20.0
    assert details[0].to_dict()["parent_chart_code"] == "S050"
