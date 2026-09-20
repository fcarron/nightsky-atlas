from __future__ import annotations

import sqlite3
from pathlib import Path

from nightsky_atlas.cli import main

ROOT = Path(__file__).resolve().parents[1]


def test_standard_star_label_report(tmp_path: Path, capsys) -> None:
    store = tmp_path / "stars.sqlite"
    with sqlite3.connect(store) as connection:
        connection.execute("CREATE TABLE stars (magnitude REAL, hip_id TEXT)")
        connection.executemany(
            "INSERT INTO stars VALUES (?, ?)",
            [(1.0, "HIP 32349"), (4.0, "HIP 999"), (8.0, None)],
        )
    assert main([
        "data", "star-label-report", "--edition", "standard",
        "--store", str(store),
        "--star-names", str(ROOT / "data/fixtures/starnames"),
        "--style", str(ROOT / "styles/standard.yaml"),
    ]) == 0
    output = capsys.readouterr().out
    assert "proper: 1" in output
    assert "unlabeled: 2" in output
