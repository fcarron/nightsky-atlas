"""Tests for angular helpers."""

from __future__ import annotations

import math

import pytest

from nightsky_atlas.astronomy.angles import (
    angular_separation_deg,
    signed_deg,
    wrap_deg,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, 0.0), (10.0, 10.0), (370.0, 10.0), (-10.0, 350.0), (360.0, 0.0)],
)
def test_wrap_deg(value: float, expected: float) -> None:
    assert wrap_deg(value) == pytest.approx(expected)


def test_wrap_deg_rejects_non_positive_period() -> None:
    with pytest.raises(ValueError):
        wrap_deg(10.0, period_deg=0.0)


@pytest.mark.parametrize(
    ("value", "expected"),
    [(0.0, 0.0), (180.0, -180.0), (190.0, -170.0), (-190.0, 170.0), (540.0, -180.0)],
)
def test_signed_deg(value: float, expected: float) -> None:
    assert signed_deg(value) == pytest.approx(expected)


def test_angular_separation_cardinals() -> None:
    assert angular_separation_deg(0.0, 0.0, 90.0, 0.0) == pytest.approx(90.0)
    assert angular_separation_deg(0.0, 0.0, 0.0, 90.0) == pytest.approx(90.0)
    assert angular_separation_deg(0.0, 0.0, 180.0, 0.0) == pytest.approx(180.0)


def test_angular_separation_identity_is_zero() -> None:
    assert angular_separation_deg(187.5, 12.0, 187.5, 12.0) == pytest.approx(0.0)


def test_angular_separation_is_symmetric_and_small_angle_stable() -> None:
    a = angular_separation_deg(187.5, 12.0, 187.6, 12.0)
    b = angular_separation_deg(187.6, 12.0, 187.5, 12.0)
    assert a == pytest.approx(b)
    assert a == pytest.approx(0.1 * math.cos(math.radians(12.0)), rel=1e-6)
