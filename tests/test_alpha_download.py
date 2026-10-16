from __future__ import annotations

import json
from pathlib import Path

import pytest

from nightsky_atlas.build.preflight import collect_build_inputs
from nightsky_atlas.catalog.magellanic_clouds import DEFAULT_DATA_PATH
from nightsky_atlas.catalog.manifest import file_sha256, write_manifest
from tools.prepare_alpha_download import prepare_alpha_download


@pytest.fixture
def atlas_output(tmp_path: Path) -> Path:
    root = tmp_path / "atlas"
    chart = root / "charts/test-001"
    chart.mkdir(parents=True)
    for pdf in (root / "atlas.pdf", chart / "chart.pdf"):
        pdf.write_bytes(b"%PDF-1.4\nfixture output\n")
    input_file = tmp_path / "input.txt"
    input_file.write_text("unchanged input")
    write_manifest(root / "manifest.json", {
        "atlas_id": "test", "chart_count": 1, "main_chart_count": 1,
        "detail_chart_count": 0, "main_chart_ids": ["test-001"], "detail_chart_ids": [],
        "total_hard_issues": 1,
        "pages": [{"chart_id": "test-001", "hard_issues": 1, "layout_issues": [{
            "severity": "hard", "type": "label_label", "affected_ids": ["a", "b"],
        }]}],
        "input_fingerprints": collect_build_inputs({
            "example": input_file, "magellanic_clouds": DEFAULT_DATA_PATH,
        }),
        "geometry_catalogues": {"magellanic_clouds": ["Gaia DR3"]},
        "output_artifacts": {
            name: file_sha256(root / name)
            for name in ("atlas.pdf", "charts/test-001/chart.pdf")
        },
    })
    return root


def test_alpha_download_keeps_issues_exact_data_notices_and_determinism(
    atlas_output: Path, tmp_path: Path,
) -> None:
    outputs = [prepare_alpha_download(atlas_output, tmp_path / name) for name in ("a", "b")]
    first = outputs[0]
    checksums = json.loads((first / "checksums.json").read_text())
    for name, checksum in checksums.items():
        assert file_sha256(first / name) == checksum
    assert (first / "atlas.pdf").read_bytes() == (atlas_output / "atlas.pdf").read_bytes()
    assert (first / DEFAULT_DATA_PATH).read_bytes() == DEFAULT_DATA_PATH.read_bytes()
    for name in (
        "THIRD_PARTY_LICENSES.md", "docs/ATLAS_DISTRIBUTION.md",
        "data/third_party/d3-celestial/LICENSE",
        "src/nightsky_atlas/assets/fonts/OFL-Lato.txt",
        "src/nightsky_atlas/assets/fonts/OFL-SourceSans3.txt",
    ):
        assert name in checksums
    inventory = json.loads((first / "release.json").read_text())
    assert inventory["hard_issues"] == 1
    assert "packaging_environment" in inventory
    assert "path" not in inventory["input_fingerprints"]["example"]
    assert str(tmp_path) not in (first / "release.json").read_text()
    assert json.loads((first / "layout-issues.json").read_text())[0]["affected_ids"] == ["a", "b"]
    assert "Known hard layout findings: 1" in (first / "README.txt").read_text()
    assert (first / "checksums.json").read_bytes() == (outputs[1] / "checksums.json").read_bytes()
    assert not list(first.rglob("*.sqlite"))
    with pytest.raises(FileExistsError):
        prepare_alpha_download(atlas_output, first)


@pytest.mark.parametrize("changed", ["pdf", "input", "gaia"])
def test_alpha_download_rejects_invalid_or_stale_inputs_before_writing(
    atlas_output: Path, tmp_path: Path, changed: str,
) -> None:
    if changed == "pdf":
        (atlas_output / "atlas.pdf").write_bytes(b"corrupt")
    elif changed == "input":
        (tmp_path / "input.txt").write_text("changed")
    else:
        path = atlas_output / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["input_fingerprints"]["magellanic_clouds"] = None
        write_manifest(path, manifest)
    output = tmp_path / "download"
    with pytest.raises(ValueError):
        prepare_alpha_download(atlas_output, output)
    assert not output.exists()
