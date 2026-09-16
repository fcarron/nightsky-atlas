"""Tests for the chart command-line surface."""

from __future__ import annotations

from pathlib import Path

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
