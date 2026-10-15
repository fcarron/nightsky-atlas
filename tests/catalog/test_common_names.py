from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

import nightsky_atlas.cli as cli
import nightsky_atlas.cli_data as cli_data
from nightsky_atlas.atlas.config import EditionConfig, load_style_config
from nightsky_atlas.atlas.index import build_atlas_index
from nightsky_atlas.catalog.common_names import curated_common_name, load_curated_common_names
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.selection_analysis import find_object
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.dso_labels import format_dso_label, primary_designation
from nightsky_atlas.layout.labels import build_dso_labels
from nightsky_atlas.projection.base import ChartPoint
from nightsky_atlas.scene.builder import build_scene
from nightsky_atlas.scene.models import SceneDso

ROOT = Path(__file__).resolve().parents[2]


def _dso(identifier: str, *aliases: str, ra_deg: float = 83.82) -> DeepSkyObject:
    return DeepSkyObject(
        id=identifier,
        ra_deg=ra_deg,
        dec_deg=-5.4,
        object_type=DsoType.BRIGHT_NEBULA,
        provenance=Provenance("test", identifier),
        magnitude=4.0,
        cross_ids=aliases,
        common_name="Uncurated raw nickname",
    )


def test_curated_registry_is_small_provenanced_and_keyed_by_physical_id() -> None:
    names = load_curated_common_names()
    assert 50 <= len(names) <= 100
    assert names["NGC1976"].name == "Orion Nebula"
    assert all(len(row.sources) >= 2 for row in names.values())
    assert curated_common_name(_dso("NGC1976", "M42")).name == "Orion Nebula"
    assert curated_common_name(_dso("NGC9999", "M42")) is None


def test_common_name_is_secondary_to_canonical_designation() -> None:
    orion = _dso("NGC1976", "M42", "Caldwell 100")
    assert primary_designation(orion) == "M42"
    assert format_dso_label(orion).text == "M42"
    assert format_dso_label(orion, include_common_name=True).text == "M42 · Orion Nebula"
    assert "Caldwell" not in format_dso_label(orion, include_common_name=True).text


def test_common_name_is_searchable_and_indexed_as_cross_reference() -> None:
    orion = _dso("NGC1976", "M42")
    assert find_object([orion], "Orion Nebula") is orion
    chart = ChartDefinition("test-001", 83.8, -5.4, 20.0, 14.0)
    index = build_atlas_index(
        {chart.id: (SceneDso(orion, ChartPoint(0.0, 0.0)),)},
        {},
        (chart,),
        EditionConfig(name="Pocket", code="P"),
    )
    assert index.dso_entries[0].designation == "M42"
    assert index.dso_entries[0].common_names == ("Orion Nebula",)
    assert index.aliases == (("Orion Nebula", "M42"),)


def test_pocket_iconic_label_is_density_sensitive() -> None:
    pocket = load_style_config(ROOT / "styles/pocket.yaml")
    standard = load_style_config(ROOT / "styles/standard.yaml")
    chart = ChartDefinition("test-001", 83.8, -5.4, 20.0, 14.0)
    transform = PageTransform(chart, PageGeometry(297.0, 210.0, 12.0))
    orion = _dso("NGC1976", "M42")
    sparse = build_scene(chart, (), (orion,))
    assert build_dso_labels(sparse, transform, pocket)[0].text == "M42 · Orion Nebula"
    assert build_dso_labels(sparse, transform, standard)[0].text == "M42"
    crowded_objects = [orion]
    for number in range(pocket.label.dso_labels.common_name_max_neighbors + 1):
        crowded_objects.append(
            replace(_dso(f"NGC{9000 + number}"), ra_deg=83.82 + 0.01 * (number + 1))
        )
    crowded = build_scene(chart, (), crowded_objects)
    by_id = {label.target_id: label for label in build_dso_labels(crowded, transform, pocket)}
    assert by_id[orion.id].text == "M42"


def test_duplicate_name_or_missing_provenance_is_rejected(tmp_path: Path) -> None:
    path = tmp_path / "names.json"
    path.write_text(
        '{"sources":{"a":"url","b":"url"},"objects":['
        '{"id":"NGC1976","name":"Orion Nebula","sources":["a","b"]},'
        '{"id":"NGC1977","name":"Orion Nebula","sources":["a","b"]}]}'
    )
    with pytest.raises(ValueError, match="duplicate"):
        load_curated_common_names(path)


def test_why_object_and_dso_info_accept_curated_name(monkeypatch, capsys) -> None:
    orion = _dso("NGC1976", "M42")
    monkeypatch.setattr(cli, "load_dso_catalog", lambda path: [orion])
    parser = cli.build_parser()
    why = parser.parse_args(["atlas", "why-object", "Orion Nebula"])
    assert why.handler(why) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["canonical_designation"] == "NGC1976"
    assert payload["display_designation"] == "M42"
    assert payload["curated_common_name"] == "Orion Nebula"
    monkeypatch.setattr(cli_data, "load_dso_catalog", lambda path: [orion])
    info = parser.parse_args(["data", "dso-info", "Orion Nebula"])
    assert info.handler(info) == 0
    result = json.loads(capsys.readouterr().out)
    assert result[0]["curated_common_name"] == "Orion Nebula"
