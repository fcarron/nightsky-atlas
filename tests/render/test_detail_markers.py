"""Subtle, unobstructive linked markers for detail charts."""

from __future__ import annotations

from pathlib import Path

import pytest

import nightsky_atlas.render.detail_markers as detail_markers
from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PagePoint, PageRect, PageTransform
from nightsky_atlas.render.detail_markers import (
    DetailMapMarker,
    _marker_tag_rect,
    draw_detail_markers,
)
from nightsky_atlas.render.pdf_navigation import PdfNavigation

ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(ROOT / "styles" / "standard.yaml")


class RecordingContext:
    def __init__(self) -> None:
        self.tags: list[tuple[str, str]] = []
        self.events: list[tuple[str, object]] = []

    def save(self) -> None:
        pass

    def restore(self) -> None:
        pass

    def rectangle(self, *args: float) -> None:
        pass

    def clip(self) -> None:
        pass

    def set_source_rgb(self, *args: float) -> None:
        self.events.append(("source_rgb", args))

    def set_source_rgba(self, *args: float) -> None:
        pass

    def set_line_width(self, *args: float) -> None:
        pass

    def set_dash(self, *args: object) -> None:
        pass

    def move_to(self, *args: float) -> None:
        pass

    def line_to(self, *args: float) -> None:
        pass

    def close_path(self) -> None:
        pass

    def stroke(self) -> None:
        pass

    def fill(self) -> None:
        self.events.append(("fill", None))

    def tag_begin(self, tag: str, attributes: str) -> None:
        self.tags.append((f"begin:{tag}", attributes))

    def tag_end(self, tag: str) -> None:
        self.tags.append((f"end:{tag}", ""))


def test_detail_tag_chooses_a_clear_deterministic_frame_corner() -> None:
    chart = PageRect(0.0, 0.0, 100.0, 80.0)
    occupied = (PageRect(10.5, 10.5, 12.0, 3.0),)
    selected = _marker_tag_rect(
        min_x=10.0,
        min_y=10.0,
        max_x=50.0,
        max_y=50.0,
        tag_width=12.0,
        tag_height=3.0,
        chart_rect=chart,
        occupied_bounds=occupied,
    )
    assert selected.left_mm == pytest.approx(37.5)
    assert selected.top_mm == pytest.approx(10.5)
    assert all(
        selected.right_mm <= obstacle.left_mm
        or selected.left_mm >= obstacle.right_mm
        or selected.bottom_mm <= obstacle.top_mm
        or selected.top_mm >= obstacle.bottom_mm
        for obstacle in occupied
    )


def test_detail_tag_keeps_a_small_gap_from_nearby_labels() -> None:
    selected = _marker_tag_rect(
        min_x=10.0,
        min_y=10.0,
        max_x=50.0,
        max_y=50.0,
        tag_width=12.0,
        tag_height=3.0,
        chart_rect=PageRect(0.0, 0.0, 100.0, 80.0),
        occupied_bounds=(PageRect(22.7, 10.5, 4.0, 3.0),),
    )
    assert selected.left_mm == pytest.approx(37.5)
    assert selected.top_mm == pytest.approx(10.5)


def test_detail_tag_keeps_named_pdf_link(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(detail_markers, "draw_text", lambda *args, **kwargs: None)
    chart = ChartDefinition(
        id="standard-031",
        center_ra_deg=300.0,
        center_dec_deg=40.0,
        width_deg=25.0,
        height_deg=17.0,
    )
    transform = PageTransform(chart=chart, page=PageGeometry(297.0, 210.0, 12.0))
    marker = DetailMapMarker(
        chart_code="SD031",
        label="Cygnus nebula field",
        boundary=(
            PagePoint(70.0, 60.0),
            PagePoint(100.0, 60.0),
            PagePoint(100.0, 90.0),
            PagePoint(70.0, 90.0),
        ),
    )
    cr = RecordingContext()
    draw_detail_markers(
        cr,
        (marker,),
        transform,
        STYLE,
        PdfNavigation(frozenset({"SD031"})),
        draw_frames=False,
    )
    links = [
        attributes for kind, attributes in cr.tags if kind == "begin:Link"
    ]
    assert len(links) == 1
    assert "dest='chart_SD031'" in links[0]
    fill_index = next(index for index, event in enumerate(cr.events) if event[0] == "fill")
    assert cr.events[fill_index + 1] == ("source_rgb", (0.0, 0.0, 0.0))
