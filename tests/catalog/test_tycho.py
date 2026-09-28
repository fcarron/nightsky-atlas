"""Tests for the Tycho-2 importer."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.astronomy.angles import angular_separation_deg
from nightsky_atlas.catalog.systems import MatchStatus, match_star_systems
from nightsky_atlas.catalog.tycho import (
    CATALOGUE,
    VERSION,
    iter_tycho2_stars,
    parse_tycho2_record,
    raw_part_paths,
)
from nightsky_atlas.catalog.wds import iter_wds_systems

REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE = REPO_ROOT / "data" / "fixtures" / "tycho2" / "sample.dat"
EPSILON_FIXTURE = REPO_ROOT / "data" / "fixtures" / "tycho2" / "epsilon_lyrae.dat"


def first_line() -> str:
    return FIXTURE.read_text(encoding="ascii").splitlines()[0]


def test_parse_first_record() -> None:
    star = parse_tycho2_record(first_line())
    assert star is not None
    assert star.id == "TYC 1-8-1"
    assert star.ra_deg == pytest.approx(2.31750494)
    assert star.dec_deg == pytest.approx(2.23184345)
    assert star.magnitude == pytest.approx(12.146)
    assert star.provenance.catalogue == CATALOGUE
    assert star.provenance.source_id == "0001-00008-1"
    assert star.provenance.version == VERSION


def test_magnitude_uses_johnson_v_conversion() -> None:
    line = first_line()
    star = parse_tycho2_record(line)
    bt = float(line[110:116])
    vt = float(line[123:129])
    assert star is not None
    assert star.magnitude == pytest.approx(vt - 0.090 * (bt - vt))


def test_falls_back_to_observed_position() -> None:
    line = first_line()
    blanked = line[:15] + " " * 12 + line[27:28] + " " * 12 + line[40:]
    star = parse_tycho2_record(blanked)
    assert star is not None
    assert star.ra_deg == pytest.approx(float(line[152:164]))
    assert star.dec_deg == pytest.approx(float(line[165:177]))


def test_record_without_magnitude_is_skipped() -> None:
    line = first_line()
    blanked = line[:110] + " " * 6 + line[116:123] + " " * 6 + line[129:]
    assert parse_tycho2_record(blanked) is None


def test_iterates_committed_fixture() -> None:
    stars = list(iter_tycho2_stars([FIXTURE]))
    assert len(stars) == 6
    assert stars[0].id == "TYC 1-8-1"


def test_fixture_records_have_no_hip_cross_id() -> None:
    assert parse_tycho2_record(first_line()).hip_id is None


def test_hip_column_is_parsed() -> None:
    line = first_line()
    with_hip = line[:142] + "   565" + line[148:]
    star = parse_tycho2_record(with_hip)
    assert star is not None
    assert star.hip_id == "HIP 565"


def test_raw_part_paths_are_deterministic() -> None:
    paths = raw_part_paths("data/raw/tycho2")
    assert len(paths) == 20
    assert paths[0].name == "tyc2.dat.00.gz"
    assert paths[-1].name == "tyc2.dat.19.gz"


def test_photocentre_records_keep_distinct_component_positions_at_j2000() -> None:
    raw = EPSILON_FIXTURE.read_text(encoding="ascii").splitlines()
    c, d = (parse_tycho2_record(line) for line in raw[2:])
    assert c is not None and d is not None
    assert raw[2][15:40] == raw[3][15:40]
    assert c.ra_deg != d.ra_deg
    assert c.dec_deg != d.dec_deg
    assert angular_separation_deg(c.ra_deg, c.dec_deg, d.ra_deg, d.dec_deg) * 3600 == (
        pytest.approx(2.34, abs=0.03)
    )
    assert c.dec_deg == pytest.approx(39.6127302, abs=0.00001)


def test_real_epsilon_lyrae_southern_pair_matches_both_components() -> None:
    stars = list(iter_tycho2_stars([EPSILON_FIXTURE]))
    wds_fixture = REPO_ROOT / "data" / "fixtures" / "double_stars" / "wds_subset.dat"
    systems = [
        system
        for system in iter_wds_systems(wds_fixture)
        if system.source_id == "STF2383:CD"
    ]
    (matched,) = match_star_systems(systems, stars)
    assert matched.match_status is MatchStatus.POSITIONAL
    assert matched.primary_star_id == "TYC 3122-3439-1"
    assert matched.component_star_ids == ("TYC 3122-3439-2",)
