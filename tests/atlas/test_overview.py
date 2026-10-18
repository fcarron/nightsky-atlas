"""Tests for whole-sky overview map construction."""

from __future__ import annotations

import math
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_atlas_config, load_style_config
from nightsky_atlas.atlas.overview import (
    NORTH,
    SOUTH,
    build_overview,
    hemisphere_for,
    overview_centres,
)
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.catalog.constellations import load_constellations

REPO_ROOT = Path(__file__).resolve().parents[2]
ATLAS = REPO_ROOT / "atlas" / "standard.yaml"
CONSTELLATIONS = REPO_ROOT / "data" / "fixtures" / "constellations"


@pytest.fixture(scope="module")
def charts():
    return chart_definitions(load_atlas_config(ATLAS))


@pytest.fixture(scope="module")
def constellations():
    return load_constellations(CONSTELLATIONS)


def test_hemispheres_cover_every_chart(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    north = build_overview(
        charts, hemisphere=NORTH, constellations=constellations, edition=atlas.resolved_edition()
    )
    south = build_overview(
        charts, hemisphere=SOUTH, constellations=constellations, edition=atlas.resolved_edition()
    )
    covered = {cell.chart_id for cell in north.cells}
    covered |= {cell.chart_id for cell in south.cells}
    assert covered == {chart.id for chart in charts}
    equatorial_count = sum(chart.center_dec_deg == 0.0 for chart in charts)
    assert north.chart_count + south.chart_count == len(charts) + equatorial_count


def test_equatorial_pocket_charts_appear_on_both_symmetric_overviews() -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / "pocket.yaml")
    charts = chart_definitions(atlas)
    north = build_overview(charts, hemisphere=NORTH, edition=atlas.resolved_edition())
    south = build_overview(charts, hemisphere=SOUTH, edition=atlas.resolved_edition())
    equatorial_ids = {chart.id for chart in charts if chart.center_dec_deg == 0.0}
    north_ids = {cell.chart_id for cell in north.cells}
    south_ids = {cell.chart_id for cell in south.cells}
    assert len(equatorial_ids) == 9
    assert north.chart_count == south.chart_count == 24
    assert north_ids & south_ids == equatorial_ids
    assert north_ids | south_ids == {chart.id for chart in charts}
    for overview in (north, south):
        assert sum(_polygon_area(cell.polygon) for cell in overview.cells) == pytest.approx(
            math.pi * overview.radius_deg**2, rel=0.01
        )
        for cell in overview.cells:
            assert cell.label_point is not None
            assert _point_in_polygon(cell.label_point, cell.polygon)


@pytest.mark.parametrize("hemisphere", (NORTH, SOUTH))
@pytest.mark.parametrize("color", (False, True))
def test_deep_overview_chart_numbers_stay_inside_their_ring_cells(
    hemisphere: str, color: bool,
) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / "deep.yaml")
    style_dir = REPO_ROOT / "styles"
    if color:
        style_dir /= "color"
    style = load_style_config(style_dir / "deep.yaml")
    overview = build_overview(
        chart_definitions(atlas),
        hemisphere=hemisphere,
        edition=atlas.resolved_edition(),
        equatorial_extension_deg=style.overview.equatorial_extension_deg,
    )
    for cell in overview.cells:
        assert cell.label_point is not None, cell.chart_code
        assert _point_in_polygon(cell.label_point, cell.polygon), cell.chart_code


def test_standard_overviews_show_full_equatorial_chart_row_on_both_hemispheres() -> None:
    atlas = load_atlas_config(ATLAS)
    style_path = REPO_ROOT / "styles" / "standard.yaml"
    style = load_style_config(style_path)
    assert style.overview.equatorial_extension_deg == pytest.approx(9.25)

    charts = chart_definitions(atlas)
    equatorial = [chart for chart in charts if chart.center_dec_deg == 0.0]
    assert len(equatorial) == 15
    assert equatorial[0].center_ra_deg == pytest.approx(12.0)

    for hemisphere in (NORTH, SOUTH):
        overview = build_overview(
            charts,
            hemisphere=hemisphere,
            edition=atlas.resolved_edition(),
            equatorial_extension_deg=style.overview.equatorial_extension_deg,
        )
        assert overview.radius_deg == pytest.approx(99.25)
        equatorial_ids = {chart.id for chart in equatorial}
        equatorial_cells = [
            cell for cell in overview.cells if cell.chart_id in equatorial_ids
        ]
        assert len(equatorial_cells) == len(equatorial)
        central_meridian_chart = next(
            chart for chart in equatorial if chart.center_ra_deg == pytest.approx(180.0)
        )
        central_meridian_cell = next(
            cell for cell in equatorial_cells if cell.chart_id == central_meridian_chart.id
        )
        assert central_meridian_cell.label_point is not None
        assert central_meridian_cell.label_point.xi_deg == pytest.approx(0.0, abs=1e-6)
        assert central_meridian_cell.label_point.eta_deg == pytest.approx(-90.0, abs=1e-6)
        for cell in equatorial_cells:
            radii = [math.hypot(point.xi_deg, point.eta_deg) for point in cell.polygon]
            assert min(radii) < 90.0
            assert max(radii) > 90.0


def test_chart_codes_are_visible_and_sequential(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    overview = build_overview(
        charts, hemisphere=NORTH, constellations=constellations, edition=atlas.resolved_edition()
    )
    codes = [cell.chart_code for cell in overview.cells]
    assert codes[0] == "S001"
    assert codes[-1] == "S072"
    assert len(set(codes)) == len(codes)


def test_every_cell_has_a_label_point(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    for hemisphere in (NORTH, SOUTH):
        overview = build_overview(
            charts,
            hemisphere=hemisphere,
            constellations=constellations,
            edition=atlas.resolved_edition(),
        )
        assert all(cell.label_point is not None for cell in overview.cells)


def test_cells_stay_inside_the_disk(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    for hemisphere in (NORTH, SOUTH):
        overview = build_overview(
            charts,
            hemisphere=hemisphere,
            constellations=constellations,
            edition=atlas.resolved_edition(),
        )
        for cell in overview.cells:
            assert len(cell.polygon) >= 3
            for point in cell.polygon:
                assert math.hypot(point.xi_deg, point.eta_deg) <= overview.radius_deg + 1e-6


def test_every_chart_centre_lies_in_its_own_cell(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    overview = build_overview(
        charts, hemisphere=NORTH, constellations=constellations, edition=atlas.resolved_edition()
    )
    for cell in overview.cells:
        assert cell.label_point is not None
        assert _point_in_polygon(cell.label_point, cell.polygon)


def test_cells_partition_the_disk_area(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    overview = build_overview(
        charts, hemisphere=NORTH, constellations=constellations, edition=atlas.resolved_edition()
    )
    total = sum(_polygon_area(cell.polygon) for cell in overview.cells)
    assert total == pytest.approx(math.pi * overview.radius_deg**2, rel=0.01)


def test_bright_stars_are_projected_and_limited(charts, constellations) -> None:
    from nightsky_atlas.catalog.models import Provenance, Star

    def star(star_id: str, ra_deg: float, dec_deg: float, magnitude: float) -> Star:
        return Star(
            id=star_id,
            ra_deg=ra_deg,
            dec_deg=dec_deg,
            magnitude=magnitude,
            provenance=Provenance(catalogue="test", source_id=star_id),
        )

    atlas = load_atlas_config(ATLAS)
    stars = [
        star("bright", 180.0, 45.0, 1.0),
        star("faint", 180.0, 45.0, 6.5),
        star("south", 0.0, -45.0, 1.0),
    ]
    overview = build_overview(
        charts,
        hemisphere=NORTH,
        constellations=constellations,
        edition=atlas.resolved_edition(),
        bright_stars=stars,
        star_limit_magnitude=5.0,
    )
    assert len(overview.stars) == 1
    assert overview.stars[0].magnitude == 1.0


def test_constellation_lines_are_straight_chords(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    overview = build_overview(
        charts, hemisphere=NORTH, constellations=constellations, edition=atlas.resolved_edition()
    )
    assert overview.constellation_lines
    assert all(len(segment.points) == 2 for segment in overview.constellation_lines)
    assert all(len(segment.points) == 2 for segment in overview.constellation_boundaries)
    assert "bold" in {segment.weight for segment in overview.constellation_lines}


def _point_in_polygon(point, polygon) -> bool:
    inside = False
    count = len(polygon)
    for index in range(count):
        start = polygon[index]
        end = polygon[(index + 1) % count]
        if (start.eta_deg > point.eta_deg) != (end.eta_deg > point.eta_deg):
            x_at = start.xi_deg + (point.eta_deg - start.eta_deg) * (
                end.xi_deg - start.xi_deg
            ) / (end.eta_deg - start.eta_deg)
            if point.xi_deg < x_at:
                inside = not inside
    return inside


def _polygon_area(polygon) -> float:
    area = 0.0
    count = len(polygon)
    for index in range(count):
        start = polygon[index]
        end = polygon[(index + 1) % count]
        area += start.xi_deg * end.eta_deg - end.xi_deg * start.eta_deg
    return abs(area) / 2.0


def test_constellation_names_use_full_iau_names(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    overview = build_overview(
        charts, hemisphere=NORTH, constellations=constellations, edition=atlas.resolved_edition()
    )
    names = {name.text for name in overview.constellation_names}
    assert "Andromeda" in names
    assert "Ursa Major" in names
    assert overview.constellation_names


def test_constellation_background_is_present(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    overview = build_overview(
        charts, hemisphere=NORTH, constellations=constellations, edition=atlas.resolved_edition()
    )
    assert overview.constellation_lines
    assert overview.constellation_boundaries
    assert overview.grid_segments


def test_polar_cap_cell_is_at_the_centre(charts, constellations) -> None:
    atlas = load_atlas_config(ATLAS)
    overview = build_overview(
        charts, hemisphere=NORTH, constellations=constellations, edition=atlas.resolved_edition()
    )
    cap = overview.cell_for("standard-001")
    assert cap is not None
    assert cap.label_point is not None
    assert math.hypot(cap.label_point.xi_deg, cap.label_point.eta_deg) < 1e-9


def test_hemisphere_for_declination() -> None:
    assert hemisphere_for(45.0) == NORTH
    assert hemisphere_for(0.0) == NORTH
    assert hemisphere_for(-1.0) == SOUTH


def test_overview_centres_reject_unknown() -> None:
    with pytest.raises(ValueError):
        overview_centres("east")


def test_overview_without_constellations_still_builds(charts) -> None:
    atlas = load_atlas_config(ATLAS)
    overview = build_overview(
        charts, hemisphere=NORTH, edition=atlas.resolved_edition()
    )
    assert overview.cells
    assert not overview.constellation_lines
