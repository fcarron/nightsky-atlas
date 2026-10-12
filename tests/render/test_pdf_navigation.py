"""PDF destinations, links, page labels and outline metadata."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import cairo
import pytest

from nightsky_atlas.chart.page import PageRect
from nightsky_atlas.render.pdf_navigation import (
    PdfNavigation,
    chart_destination,
    page_destination,
)


class RecordingContext:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def tag_begin(self, tag: str, attributes: str) -> None:
        self.calls.append((f"begin:{tag}", attributes))

    def tag_end(self, tag: str) -> None:
        self.calls.append((f"end:{tag}", ""))


class RecordingSurface:
    def __init__(self) -> None:
        self.labels: list[str] = []
        self.outlines: list[tuple[int, str, str, object]] = []

    def set_page_label(self, label: str) -> None:
        self.labels.append(label)

    def add_outline(self, parent: int, title: str, target: str, flags: object) -> int:
        self.outlines.append((parent, title, target, flags))
        return len(self.outlines)


def test_destinations_are_stable_and_unique() -> None:
    navigation = PdfNavigation(frozenset({"S031", "S032"}))
    assert chart_destination("S031") == "chart_S031"
    assert {chart_destination(code) for code in navigation.chart_codes} == {
        "chart_S031",
        "chart_S032",
    }
    with pytest.raises(ValueError, match="invalid chart code"):
        chart_destination("S 031")
    assert page_destination("overview-north") == "page_overview-north"
    with pytest.raises(ValueError, match="invalid page id"):
        page_destination("overview north")


def test_reciprocal_links_use_named_destinations() -> None:
    navigation = PdfNavigation(frozenset({"S031", "S032"}))
    cr = RecordingContext()
    rect = PageRect(10.0, 20.0, 8.0, 3.0)
    with navigation.link(cr, "S032", rect) as emitted:
        assert emitted
    with navigation.link(cr, "S031", rect) as emitted:
        assert emitted
    begins = [attributes for kind, attributes in cr.calls if kind == f"begin:{cairo.TAG_LINK}"]
    assert "dest='chart_S032'" in begins[0]
    assert "dest='chart_S031'" in begins[1]
    assert all("rect=[" in attributes for attributes in begins)


def test_missing_chart_does_not_emit_link() -> None:
    navigation = PdfNavigation(frozenset({"S031"}))
    cr = RecordingContext()
    with navigation.link(cr, "S999", PageRect(0.0, 0.0, 1.0, 1.0)) as emitted:
        assert not emitted
    assert cr.calls == []


def test_page_label_destination_and_bookmark_use_chart_id() -> None:
    navigation = PdfNavigation(frozenset({"S031"}))
    surface = RecordingSurface()
    cr = RecordingContext()
    navigation.mark_chart_page(surface, cr, "S031")
    bookmark = navigation.add_outline(surface, 0, "S031", "S031")
    assert surface.labels == ["S031"]
    assert cr.calls == [
        (f"begin:{cairo.TAG_DEST}", "name='chart_S031' x=0 y=0"),
        (f"end:{cairo.TAG_DEST}", ""),
    ]
    assert bookmark == 1
    assert surface.outlines[0][1:3] == ("S031", "dest='chart_S031'")


def test_named_page_destination_and_bookmark() -> None:
    navigation = PdfNavigation(frozenset(), frozenset({"overview-north"}))
    surface = RecordingSurface()
    cr = RecordingContext()
    navigation.mark_page(surface, cr, "overview-north", label="Northern Sky Overview")
    bookmark = navigation.add_page_outline(
        surface, 0, "Northern Sky", "overview-north"
    )
    assert surface.labels == ["Northern Sky Overview"]
    assert cr.calls == [
        (f"begin:{cairo.TAG_DEST}", "name='page_overview-north' x=0 y=0"),
        (f"end:{cairo.TAG_DEST}", ""),
    ]
    assert bookmark == 1
    assert surface.outlines[0][1:3] == ("Northern Sky", "dest='page_overview-north'")


def test_named_page_destination_supports_hyphenated_ids(tmp_path: Path) -> None:
    path = tmp_path / "named-page.pdf"
    surface = cairo.PDFSurface(str(path), 200.0, 200.0)
    cr = cairo.Context(surface)
    navigation = PdfNavigation(frozenset(), frozenset({"overview-north"}))
    navigation.mark_page(surface, cr, "overview-north", label="Northern Sky Overview")
    cr.show_text("Overview")
    surface.show_page()
    surface.finish()
    assert path.exists()


def test_link_attributes_are_deterministic() -> None:
    navigation = PdfNavigation(frozenset({"S031", "S032"}), frozenset({"overview"}))
    rect = PageRect(10.0, 20.0, 8.0, 3.0)
    contexts = [RecordingContext(), RecordingContext()]
    for cr in contexts:
        with navigation.link(cr, "S032", rect):
            pass
    assert contexts[0].calls == contexts[1].calls


@pytest.mark.skipif(shutil.which("mutool") is None, reason="mutool is not installed")
def test_cairo_pdf_contains_navigation_after_front_matter(tmp_path: Path) -> None:
    path = tmp_path / "navigation.pdf"
    surface = cairo.PDFSurface(str(path), 200.0, 200.0)
    cr = cairo.Context(surface)
    navigation = PdfNavigation(frozenset({"S031", "S032"}), frozenset({"overview"}))
    root = navigation.add_outline(
        surface, cairo.PDF_OUTLINE_ROOT, "Standard", "S031", open_item=True
    )
    assert root is not None

    cr.move_to(10.0, 20.0)
    cr.show_text("Front matter")
    surface.show_page()

    navigation.mark_page(surface, cr, "overview", label="Sky Overviews")
    navigation.add_page_outline(surface, root, "Sky Overviews", "overview")
    cr.move_to(10.0, 20.0)
    cr.show_text("Overview")
    surface.show_page()

    for chart_code, target in (("S031", "S032"), ("S032", "S031")):
        navigation.mark_chart_page(surface, cr, chart_code)
        navigation.add_outline(surface, root, chart_code, chart_code)
        with navigation.link(cr, target, PageRect(10.0, 10.0, 20.0, 5.0)):
            cr.move_to(10.0, 20.0)
            cr.show_text(target)
        surface.show_page()
    surface.finish()

    structure = subprocess.run(
        ["mutool", "show", str(path), "grep", "chart_S"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    assert "(chart_S031)" in structure
    assert "(chart_S032)" in structure
    assert "(page_overview)" in structure
    assert "/PageLabels" in structure
    assert "/Outlines" in structure
    assert "/Annots" in structure
