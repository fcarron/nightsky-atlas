"""Tests for Pango text metrics."""

from __future__ import annotations

import cairo
import pytest

from nightsky_atlas.render.text import TextMeasurer, measure_point_size
from nightsky_atlas.units import mm_to_pt


def test_measure_is_positive() -> None:
    metrics = TextMeasurer("DejaVu Sans", 6.0).measure_mm("M31")
    assert metrics.width_mm > 0.0
    assert metrics.height_mm > 0.0


def test_longer_text_is_wider() -> None:
    measurer = TextMeasurer("DejaVu Sans", 6.0)
    assert measurer.measure_mm("NGC4486").width_mm > measurer.measure_mm("M87").width_mm


def test_larger_font_is_larger() -> None:
    small = TextMeasurer("DejaVu Sans", 6.0).measure_mm("M31")
    large = TextMeasurer("DejaVu Sans", 12.0).measure_mm("M31")
    assert large.width_mm > small.width_mm
    assert large.height_mm > small.height_mm


def test_measurer_matches_render_context() -> None:
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 8, 8)
    context = cairo.Context(surface)
    width_pt, height_pt = measure_point_size(context, "M31", "DejaVu Sans", 10.0)
    metrics = TextMeasurer("DejaVu Sans", 10.0).measure_mm("M31")
    assert mm_to_pt(metrics.width_mm) == pytest.approx(width_pt)
    assert mm_to_pt(metrics.height_mm) == pytest.approx(height_pt)


def test_expected_size_at_72_dpi() -> None:
    metrics = TextMeasurer("DejaVu Sans", 10.0).measure_mm("M31")
    assert metrics.width_mm == pytest.approx(7.4, abs=0.5)
    assert metrics.height_mm == pytest.approx(4.6, abs=0.5)


def test_bold_is_at_least_as_wide_as_normal() -> None:
    normal = TextMeasurer("DejaVu Sans", 8.0, "normal").measure_mm("M87")
    bold = TextMeasurer("DejaVu Sans", 8.0, "bold").measure_mm("M87")
    assert bold.width_mm >= normal.width_mm


def test_unknown_weight_is_rejected() -> None:
    with pytest.raises(ValueError):
        TextMeasurer("DejaVu Sans", 8.0, "heavy")
