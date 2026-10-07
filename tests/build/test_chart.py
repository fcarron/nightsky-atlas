from __future__ import annotations

from nightsky_atlas.build.chart import _primary_star_query_limit


def test_primary_query_stays_at_configured_limit_without_faint_supplement() -> None:
    assert _primary_star_query_limit(11.5, None) == 11.5


def test_primary_query_reaches_faint_supplement_limit() -> None:
    assert _primary_star_query_limit(11.5, 13.0) == 13.0


def test_higher_primary_limit_is_preserved() -> None:
    assert _primary_star_query_limit(14.0, 13.0) == 14.0
