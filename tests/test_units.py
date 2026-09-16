"""Tests for physical unit conversions."""

from __future__ import annotations

import pytest

from nightsky_atlas.units import mm_to_pt, pt_to_mm


def test_mm_to_pt() -> None:
    assert mm_to_pt(25.4) == pytest.approx(72.0)
    assert mm_to_pt(1.0) == pytest.approx(72.0 / 25.4)


def test_pt_to_mm() -> None:
    assert pt_to_mm(72.0) == pytest.approx(25.4)


def test_round_trip() -> None:
    assert pt_to_mm(mm_to_pt(210.0)) == pytest.approx(210.0)
