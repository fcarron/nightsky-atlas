"""Pinned S&T sky-culture parsing and normalized artifact checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nightsky_atlas.catalog import stellarium_figures
from nightsky_atlas.catalog.stellarium_figures import parse_figures, verify_source


def payload(lines: list[list[int | str]]) -> bytes:
    return json.dumps({
        "id": "western_SnT",
        "constellations": [
            {"id": "CON western_SnT Cyg", "iau": "Cyg", "lines": lines}
        ],
    }).encode()


def test_parse_unstyled_bold_and_thin_paths_preserves_order() -> None:
    figures = parse_figures(payload([[1, 3, 2], ["bold", 4, 5], ["thin", 6, 7]]))
    assert figures == (("Cyg", (("normal", (1, 3, 2)), ("bold", (4, 5)), ("thin", (6, 7)))),)


def test_duplicate_consecutive_reference_is_removed() -> None:
    assert parse_figures(payload([[1, 1, 2]]))[0][1][0] == ("normal", (1, 2))


@pytest.mark.parametrize("lines", [[["wide", 1, 2]], [[1]], [[1, "thin", 2]], [[0, 2]]])
def test_malformed_paths_are_diagnosed(lines: list[list[int | str]]) -> None:
    with pytest.raises(ValueError):
        parse_figures(payload(lines))


def test_bad_constellation_id_is_diagnosed() -> None:
    with pytest.raises(ValueError, match="unknown constellation ID"):
        parse_figures(payload([[1, 2]]).replace(b"CON western_SnT Cyg", b"CON western_SnT Foo"))


def test_source_checksum_is_pinned() -> None:
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_source(payload([[1, 2]]))


def test_committed_result_is_stable_and_has_expected_classes() -> None:
    root = Path(__file__).resolve().parents[2] / "data/fixtures/constellations"
    raw = (root / "constellations.lines.json").read_bytes()
    document = json.loads(raw)
    assert len(document["features"]) == 88
    weights = [
        weight
        for feature in document["features"]
        for weight in feature["properties"]["weights"]
    ]
    assert {weight: weights.count(weight) for weight in set(weights)} == {
        "bold": 20, "normal": 165, "thin": 24,
    }
    assert raw == (json.dumps(document, ensure_ascii=False, indent=2) + "\n").encode()


def test_import_is_deterministic_and_reports_unresolved_hip(tmp_path: Path, monkeypatch) -> None:
    source = tmp_path / "index.json"
    source.write_bytes(payload([["bold", 1, 2], ["thin", 2, 3]]))
    monkeypatch.setattr(stellarium_figures, "verify_source", lambda _: None)
    monkeypatch.setattr(
        stellarium_figures, "_positions", lambda *_: {"1": (1.0, 2.0), "2": (3.0, 4.0)}
    )
    with pytest.raises(ValueError, match="unresolved Stellarium HIP IDs: 3"):
        stellarium_figures.import_stellarium_figures(
            source, tmp_path / "stars.db", tmp_path / "out"
        )

    monkeypatch.setattr(
        stellarium_figures,
        "_positions",
        lambda *_: {"1": (1.0, 2.0), "2": (3.0, 4.0), "3": (5.0, 6.0)},
    )
    counts = stellarium_figures.import_stellarium_figures(
        source, tmp_path / "stars.db", tmp_path / "out"
    )
    first = (tmp_path / "out/constellations.lines.json").read_bytes()
    stellarium_figures.import_stellarium_figures(source, tmp_path / "stars.db", tmp_path / "out")
    assert (tmp_path / "out/constellations.lines.json").read_bytes() == first
    assert counts == {"constellations": 1, "bold": 1, "thin": 1}
