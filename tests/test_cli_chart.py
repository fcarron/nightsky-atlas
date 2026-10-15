"""Tests for the chart command-line surface."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock

import pytest

import nightsky_atlas.cli as cli
from nightsky_atlas.cli import main

REPO_ROOT = Path(__file__).resolve().parents[1]
ATLAS = REPO_ROOT / "atlas" / "standard.yaml"
STYLE = REPO_ROOT / "styles" / "standard.yaml"
STARS = REPO_ROOT / "data" / "fixtures" / "stars" / "test_virgo.csv"


def test_chart_render_command_writes_artifacts(tmp_path: Path) -> None:
    code = main(
        [
            "chart",
            "render",
            "--chart",
            "test-virgo",
            "--atlas",
            str(ATLAS),
            "--style",
            str(STYLE),
            "--stars",
            str(STARS),
            "--outdir",
            str(tmp_path),
        ]
    )
    assert code == 0
    chart_dir = tmp_path / "standard" / "charts" / "test-virgo"
    assert (chart_dir / "chart.pdf").read_bytes().startswith(b"%PDF")
    assert (chart_dir / "preview.png").exists()


def test_magnitude_scale_command_writes_artifacts(tmp_path: Path) -> None:
    code = main(
        [
            "chart",
            "magnitude-scale",
            "--atlas",
            str(ATLAS),
            "--style",
            str(STYLE),
            "--outdir",
            str(tmp_path),
        ]
    )
    assert code == 0
    diagnostics = tmp_path / "standard" / "diagnostics"
    assert (diagnostics / "magnitude-scale.pdf").exists()
    assert (diagnostics / "magnitude-scale.png").exists()


def test_edition_magnitude_scale_command_writes_artifacts(tmp_path: Path) -> None:
    code = main(
        [
            "chart",
            "magnitude-scale",
            "--atlas",
            str(ATLAS),
            "--style",
            str(STYLE),
            "--edition-comparison",
            "--outdir",
            str(tmp_path),
        ]
    )
    assert code == 0
    diagnostics = tmp_path / "standard" / "diagnostics"
    assert (diagnostics / "edition-star-curves.pdf").exists()
    assert (diagnostics / "edition-star-curves.png").exists()


@pytest.mark.parametrize(
    ("explicit_paths", "expected_edition"),
    [(False, "pocket"), (True, "standard")],
    ids=["edition-presets", "explicit-paths-override-preset"],
)
def test_edition_resolves_atlas_and_style_before_rendering(
    tmp_path: Path, monkeypatch, explicit_paths: bool, expected_edition: str
) -> None:
    renderer = Mock()
    monkeypatch.setattr(cli, "render_magnitude_scale", renderer)
    arguments = ["chart", "magnitude-scale", "--edition", "pocket", "--outdir", str(tmp_path)]
    if explicit_paths:
        arguments.extend(["--atlas", str(ATLAS), "--style", str(STYLE)])
    assert main(arguments) == 0
    renderer.assert_called_once()
    assert renderer.call_args.args[1].id == expected_edition
    assert renderer.call_args.kwargs["pdf_path"] == (
        tmp_path / expected_edition / "diagnostics" / "magnitude-scale.pdf"
    )


def test_chart_render_accepts_explicit_optional_input_opt_outs(tmp_path: Path) -> None:
    code = main(
        [
            "chart",
            "render",
            "--chart",
            "test-virgo",
            "--atlas",
            str(ATLAS),
            "--style",
            str(STYLE),
            "--stars",
            str(STARS),
            "--no-constellations",
            "--no-outlines",
            "--no-star-names",
            "--no-observing-lists",
            "--no-double-stars",
            "--debug",
            "line_knockouts",
            "--outdir",
            str(tmp_path),
        ]
    )
    assert code == 0
    assert (tmp_path / "standard" / "charts" / "test-virgo" / "chart.pdf").exists()


def test_unknown_chart_reports_error(tmp_path: Path, capsys) -> None:
    code = main(
        [
            "chart",
            "render",
            "--chart",
            "does-not-exist",
            "--atlas",
            str(ATLAS),
            "--style",
            str(STYLE),
            "--stars",
            str(STARS),
            "--outdir",
            str(tmp_path),
        ]
    )
    assert code == 1
    assert "does-not-exist" in capsys.readouterr().err
