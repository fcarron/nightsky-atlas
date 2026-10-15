from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from nightsky_atlas.catalog.magellanic_clouds import (
    DEFAULT_DATA_PATH,
    MagellanicContour,
    load_magellanic_contours,
)
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.chart.models import ChartDefinition
from nightsky_atlas.scene.builder import build_scene


def _dso(object_id: str, ra_deg: float, dec_deg: float, object_type: DsoType) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        object_type=object_type,
        provenance=Provenance("test", object_id),
    )


def test_distributed_contours_are_complete_and_in_icrs_bounds() -> None:
    contours = load_magellanic_contours()
    assert len(contours) == 6
    assert {(item.cloud_id, item.level) for item in contours} == {
        (cloud, level) for cloud in ("LMC", "SMC") for level in (1, 2, 3)
    }
    for contour in contours:
        assert contour.points[0] == contour.points[-1]
        assert len(set(contour.points[:-1])) >= 3
        assert all(0.0 <= ra < 360.0 and -90.0 <= dec <= 90.0 for ra, dec in contour.points)


def test_loader_rejects_self_intersecting_polygon(tmp_path: Path) -> None:
    data = json.loads(DEFAULT_DATA_PATH.read_text(encoding="utf-8"))
    data["features"][0]["geometry"]["coordinates"] = [
        [[80.0, -70.0], [81.0, -69.0], [80.0, -69.0], [81.0, -70.0], [80.0, -70.0]]
    ]
    path = tmp_path / "invalid.geojson"
    path.write_text(json.dumps(data), encoding="utf-8")
    with pytest.raises(ValueError, match="self-intersects"):
        load_magellanic_contours(path)


def test_cloud_ellipses_are_replaced_but_other_dsos_remain() -> None:
    contours = load_magellanic_contours()
    chart = ChartDefinition("lmc", 80.9, -69.75, 18.0, 14.0)
    dsos = (
        _dso("ESO056-115", 80.89375, -69.7561, DsoType.GALAXY),
        _dso("NGC0292", 13.18658, -72.8286, DsoType.GALAXY),
        _dso("NGC2070", 84.675, -69.1, DsoType.BRIGHT_NEBULA),
        _dso("unrelated-galaxy", 80.0, -69.0, DsoType.GALAXY),
    )
    scene = build_scene(chart, deep_sky_objects=dsos, magellanic_contours=contours)
    by_id = {item.dso.id: item for item in scene.deep_sky_objects}
    assert by_id["ESO056-115"].symbol_visible is False
    assert by_id["NGC2070"].symbol_visible is True
    assert by_id["unrelated-galaxy"].symbol_visible is True
    assert {item.cloud_id for item in scene.magellanic_polygons} == {"LMC"}
    assert all(
        abs(point.xi_deg) <= chart.width_deg / 2 + 1e-9
        and abs(point.eta_deg) <= chart.height_deg / 2 + 1e-9
        for item in scene.magellanic_polygons
        for point in item.fill_points
    )
    smc_scene = build_scene(
        ChartDefinition("smc", 13.2, -72.8, 12.0, 9.0),
        deep_sky_objects=(dsos[1],),
        magellanic_contours=contours,
    )
    assert len(smc_scene.deep_sky_objects) == 1
    assert smc_scene.deep_sky_objects[0].symbol_visible is False
    assert {item.cloud_id for item in smc_scene.magellanic_polygons} == {"SMC"}


def test_fully_contained_cloud_clips_as_a_full_chart_field() -> None:
    chart = ChartDefinition("contained", 0.0, 0.0, 4.0, 4.0)
    contour = MagellanicContour(
        id="magellanic:lmc:synthetic",
        cloud_id="LMC",
        dso_id="ESO056-115",
        level=1,
        points=((355.0, -5.0), (5.0, -5.0), (5.0, 5.0), (355.0, 5.0), (355.0, -5.0)),
    )
    scene = build_scene(chart, magellanic_contours=(contour,))
    assert len(scene.magellanic_polygons) == 1
    fill = scene.magellanic_polygons[0].fill_points
    assert min(point.xi_deg for point in fill) == pytest.approx(-2.0)
    assert max(point.xi_deg for point in fill) == pytest.approx(2.0)
    assert min(point.eta_deg for point in fill) == pytest.approx(-2.0)
    assert max(point.eta_deg for point in fill) == pytest.approx(2.0)


def test_contour_generator_is_deterministic(tmp_path: Path) -> None:
    sys.path.insert(0, str(Path("scripts").resolve()))
    try:
        import generate_magellanic_cloud_contours as generator
    finally:
        sys.path.pop(0)
    first, second = tmp_path / "first.geojson", tmp_path / "second.geojson"
    cutouts = {
        "LMC": Path("data/third_party/gaia_dr3_magellanic/LMC-density.fits"),
        "SMC": Path("data/third_party/gaia_dr3_magellanic/SMC-density.fits"),
    }
    flux_cutouts = {
        "LMC": Path("data/third_party/gaia_dr3_magellanic/LMC-gflux.fits"),
        "SMC": Path("data/third_party/gaia_dr3_magellanic/SMC-gflux.fits"),
    }
    generator.generate(first, cutouts, sigma_px=5.0, simplify_px=1.0, flux_cutouts=flux_cutouts)
    generator.generate(second, cutouts, sigma_px=5.0, simplify_px=1.0, flux_cutouts=flux_cutouts)
    assert first.read_bytes() == second.read_bytes()
    features = json.loads(first.read_text(encoding="utf-8"))["features"]
    sources = [(item["properties"]["level"], item["properties"]["source_map"]) for item in features]
    assert sources == [
        (1, "density"),
        (2, "density"),
        (3, "flux"),
        (1, "density"),
        (2, "density"),
        (3, "density"),
    ]
