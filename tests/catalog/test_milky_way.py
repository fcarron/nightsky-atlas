from __future__ import annotations

from pathlib import Path

from nightsky_atlas.catalog.milky_way import load_milky_way_contours

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_vendored_d3_celestial_milky_way_data_loads_all_five_levels() -> None:
    contours = load_milky_way_contours(
        REPO_ROOT / "data" / "third_party" / "d3-celestial" / "mw.json"
    )
    assert len(contours) == 202
    assert {contour.level for contour in contours} == {1, 2, 3, 4, 5}
    assert sum(len(contour.points) for contour in contours) == 30_676
    assert all(contour.points[0] == contour.points[-1] for contour in contours)


def test_geojson_longitudes_are_converted_to_right_ascension() -> None:
    contours = load_milky_way_contours(
        REPO_ROOT / "data" / "third_party" / "d3-celestial" / "mw.json"
    )
    assert all(0.0 <= ra_deg < 360.0 for contour in contours for ra_deg, _ in contour.points)
