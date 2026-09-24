"""Chart regression for the Crumey galaxy contour classes.

Builds two real fields from the committed OpenNGC reference fixture (M13 with
NGC 6207 / IC 4617, and the NGC 7331 / Stephan's Quintet group), checks the
classified contour class on the scene metadata and renders a valid PDF.
"""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.galaxy_visibility import GalaxyContourClass
from nightsky_atlas.catalog.openngc import load_sample_dsos
from nightsky_atlas.catalog.selection import SelectionPolicy
from nightsky_atlas.catalog.visibility import VisibilityLimits
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.render.cairo import render_chart
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
REFERENCE_FIXTURE = REPO_ROOT / "data" / "fixtures" / "openngc" / "visibility_reference.csv"
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
POLICY = SelectionPolicy(visibility=VisibilityLimits(include_all=True))


def _field(center_ra_deg: float, center_dec_deg: float, size_deg: float = 4.0):
    definition = ChartDefinition(
        id="regression",
        center_ra_deg=center_ra_deg,
        center_dec_deg=center_dec_deg,
        width_deg=size_deg,
        height_deg=size_deg,
    )
    scene = build_scene(
        definition,
        deep_sky_objects=load_sample_dsos(REFERENCE_FIXTURE),
        selection_policy=POLICY,
    )
    return scene, PageTransform(chart=definition, page=PAGE)


def _contours(scene) -> dict[str, GalaxyContourClass]:
    return {
        item.dso.id: item.metadata.galaxy_contour_class
        for item in scene.deep_sky_objects
        if item.metadata is not None
    }


def test_m13_field_contours_and_render(tmp_path: Path) -> None:
    scene, transform = _field(250.42, 36.5)
    contours = _contours(scene)
    assert contours["NGC6207"] == GalaxyContourClass.BOLD
    assert contours["IC4617"] == GalaxyContourClass.DOTTED

    pdf_path = tmp_path / "m13.pdf"
    render_chart(scene, transform, STYLE, pdf_path=pdf_path)
    assert pdf_path.read_bytes().startswith(b"%PDF")


def test_ngc7331_group_contours_and_render(tmp_path: Path) -> None:
    scene, transform = _field(339.0, 34.0, size_deg=3.0)
    contours = _contours(scene)
    assert contours["NGC7331"] == GalaxyContourClass.BOLD
    assert contours["NGC7317"] == GalaxyContourClass.NORMAL
    assert contours["NGC7319"] == GalaxyContourClass.FINE
    assert contours["NGC7320"] == GalaxyContourClass.FINE
    assert contours["NGC7320C"] == GalaxyContourClass.DOTTED

    pdf_path = tmp_path / "ngc7331.pdf"
    render_chart(scene, transform, STYLE, pdf_path=pdf_path)
    assert pdf_path.read_bytes().startswith(b"%PDF")
