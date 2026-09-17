"""Tests for the spatial neighbour index used by the label optimizer."""

from __future__ import annotations

from nightsky_atlas.chart.page import PageRect
from nightsky_atlas.layout.spatial import RectIndex


def rect(left: float, top: float, width: float = 2.0, height: float = 2.0) -> PageRect:
    return PageRect(left_mm=left, top_mm=top, width_mm=width, height_mm=height)


def test_query_returns_insertion_order() -> None:
    index: RectIndex[str] = RectIndex(8.0)
    index.set("c", rect(0.0, 0.0), "c")
    index.set("a", rect(1.0, 0.0), "a")
    index.set("b", rect(2.0, 0.0), "b")
    assert index.query(rect(0.0, 0.0, 4.0, 2.0)) == ["c", "a", "b"]


def test_query_filters_distant_rectangles() -> None:
    index: RectIndex[str] = RectIndex(8.0)
    index.set("near", rect(0.0, 0.0), "near")
    index.set("far", rect(500.0, 500.0), "far")
    assert index.query(rect(0.0, 0.0)) == ["near"]


def test_margin_includes_nearby_rectangles() -> None:
    index: RectIndex[str] = RectIndex(8.0)
    index.set("near", rect(10.0, 0.0), "near")
    assert index.query(rect(0.0, 0.0), margin_mm=5.0) == []
    assert index.query(rect(0.0, 0.0), margin_mm=10.0) == ["near"]


def test_exclude_removes_key() -> None:
    index: RectIndex[str] = RectIndex(8.0)
    index.set("a", rect(0.0, 0.0), "a")
    index.set("b", rect(1.0, 0.0), "b")
    assert index.query(rect(0.0, 0.0, 4.0, 2.0), exclude="a") == ["b"]


def test_update_keeps_insertion_order() -> None:
    index: RectIndex[str] = RectIndex(8.0)
    index.set("a", rect(0.0, 0.0), "a")
    index.set("b", rect(1.0, 0.0), "b")
    index.set("a", rect(200.0, 200.0), "a")
    assert index.query(rect(0.0, 0.0, 4.0, 2.0)) == ["b"]
    assert index.query(rect(200.0, 200.0, 4.0, 2.0)) == ["a"]


def test_discard_removes_key() -> None:
    index: RectIndex[str] = RectIndex(8.0)
    index.set("a", rect(0.0, 0.0), "a")
    index.discard("a")
    assert index.query(rect(0.0, 0.0)) == []


def test_touching_rectangles_are_found() -> None:
    index: RectIndex[str] = RectIndex(8.0)
    index.set("right", rect(2.0, 0.0), "right")
    assert index.query(rect(0.0, 0.0)) == ["right"]
