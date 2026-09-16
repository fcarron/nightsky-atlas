"""Tests for merging a primary star catalogue with a bright-star supplement."""

from __future__ import annotations

from nightsky_atlas.catalog.merge import merge_stars
from nightsky_atlas.catalog.models import Provenance, Star


def make_star(identifier: str, ra: float, dec: float, magnitude: float) -> Star:
    return Star(
        id=identifier,
        ra_deg=ra,
        dec_deg=dec,
        magnitude=magnitude,
        provenance=Provenance(catalogue="TEST", source_id=identifier),
    )


def test_duplicate_supplement_star_is_dropped() -> None:
    primary = [make_star("P1", 100.0, 20.0, 5.0)]
    supplement = [make_star("S1", 100.0001, 20.0, 5.0), make_star("S2", 101.0, 20.0, 4.0)]
    merged = list(merge_stars(primary, supplement))
    assert [star.id for star in merged] == ["P1", "S2"]


def test_primary_order_is_preserved() -> None:
    primary = [make_star("P1", 10.0, 0.0, 5.0), make_star("P2", 10.1, 0.0, 5.0)]
    merged = list(merge_stars(primary, []))
    assert [star.id for star in merged] == ["P1", "P2"]


def test_supplement_star_far_from_primary_is_kept() -> None:
    primary = [make_star("P1", 10.0, 0.0, 5.0)]
    supplement = [make_star("S1", 10.02, 0.0, 5.0)]
    merged = list(merge_stars(primary, supplement))
    assert {star.id for star in merged} == {"P1", "S1"}


def test_match_across_ra_wrap() -> None:
    primary = [make_star("P1", 359.99999, 0.0, 5.0)]
    supplement = [make_star("S1", 0.00001, 0.0, 5.0)]
    merged = list(merge_stars(primary, supplement))
    assert [star.id for star in merged] == ["P1"]


def test_match_exactly_at_radius_boundary() -> None:
    primary = [make_star("P1", 100.0, 0.0, 5.0)]
    supplement = [make_star("S1", 100.0, 3.0 / 3600.0, 5.0)]
    merged = list(merge_stars(primary, supplement))
    assert [star.id for star in merged] == ["P1"]
