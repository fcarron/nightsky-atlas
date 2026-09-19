"""Publication input and provenance checks."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_atlas_config
from nightsky_atlas.atlas.tiling import chart_definitions
from nightsky_atlas.build.preflight import collect_data_sources, validate_publication_inputs
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.store import build_star_store

REPO_ROOT = Path(__file__).resolve().parents[2]


def _source(path: Path, catalogue: str) -> None:
    path.write_text("[]", encoding="utf-8")
    path.with_suffix(".manifest.json").write_text(
        json.dumps({"processed_file": path.name, "source": catalogue, "license": "test license"}),
        encoding="utf-8",
    )


def test_collect_sources_uses_selected_paths_not_repository_defaults(tmp_path: Path) -> None:
    stars = tmp_path / "sample.csv"
    stars.write_text("id,ra_deg,dec_deg,magnitude\n", encoding="utf-8")
    dsos = tmp_path / "custom.json"
    _source(dsos, "custom source")

    sources = collect_data_sources(
        star_store=None,
        stars_csv=stars,
        dsos_path=dsos,
        double_stars_path=False,
    )

    assert [(item["kind"], item["path"]) for item in sources] == [
        ("stars", str(stars)),
        ("deep_sky", str(dsos)),
    ]
    assert sources[0]["manifest"] is None
    assert sources[1]["manifest"]["source"] == "custom source"


def test_publication_requires_full_sky_and_matching_manifests(tmp_path: Path) -> None:
    atlas = load_atlas_config(REPO_ROOT / "atlas" / "standard.yaml")
    charts = chart_definitions(atlas)
    stars = tmp_path / "stars.sqlite"
    build_star_store(
        stars,
        [
            Star(
                id="test-star",
                ra_deg=0.0,
                dec_deg=0.0,
                magnitude=5.0,
                provenance=Provenance("test", "star"),
            )
        ],
    )
    stars.with_suffix(".manifest.json").write_text(
        json.dumps({"processed_file": stars.name, "source": "stars", "license": "test"}),
        encoding="utf-8",
    )
    dsos = tmp_path / "dsos.json"
    _source(dsos, "dsos")
    sources = collect_data_sources(
        star_store=stars, stars_csv=None, dsos_path=dsos, double_stars_path=False
    )

    validate_publication_inputs(
        atlas, charts, charts, star_store=stars, dso_count=1, data_sources=sources
    )
    with pytest.raises(ValueError, match="every chart"):
        validate_publication_inputs(
            atlas, charts, charts[:1], star_store=stars, dso_count=1, data_sources=sources
        )
    sources[1]["manifest"]["processed_file"] = "wrong.json"
    with pytest.raises(ValueError, match="does not match"):
        validate_publication_inputs(
            atlas, charts, charts, star_store=stars, dso_count=1, data_sources=sources
        )
