"""Import IAU stick figures defined as Hipparcos star sequences."""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from pathlib import Path
from shutil import copy2

from nightsky_atlas.catalog.constellations import CONSTELLATION_NAMES
from nightsky_atlas.catalog.hipparcos import iter_hipparcos_stars

__all__ = ["import_iau_stick_figures"]


def _key(value: str) -> str:
    return "".join(
        character for character in unicodedata.normalize("NFKD", value) if character.isalpha()
    ).casefold()


def _constellation_ids(source: Path) -> list[tuple[str, list[list[str]]]]:
    names = {_key(name): abbreviation for abbreviation, name in CONSTELLATION_NAMES.items()}
    current: str | None = None
    figures: list[tuple[str, list[list[str]]]] = []
    for raw_line in source.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("* "):
            source_name = line[2:]
            current = names.get(_key(source_name))
            if current is None and source_name[-1:] in {"A", "B"}:
                current = names.get(_key(source_name[:-1]))
            if current is None:
                raise ValueError(f"unknown IAU constellation name: {source_name!r}")
            figures.append((current, []))
        elif line.startswith("["):
            if current is None:
                raise ValueError("stick figure appears before a constellation heading")
            values = json.loads(line)
            if not isinstance(values, list) or len(values) < 2:
                raise ValueError(f"invalid Hipparcos path: {line!r}")
            figures[-1][1].append([str(value).rstrip("*") for value in values])
    return figures


def _positions(store_path: Path, hipparcos_raw: Path | None) -> dict[str, tuple[float, float]]:
    connection = sqlite3.connect(store_path)
    try:
        rows = connection.execute(
            "SELECT hip_id, ra_deg, dec_deg FROM stars WHERE hip_id IS NOT NULL"
        ).fetchall()
    finally:
        connection.close()
    positions = {
        str(hip_id).removeprefix("HIP "): (float(ra), float(dec)) for hip_id, ra, dec in rows
    }
    if hipparcos_raw is not None:
        for star in iter_hipparcos_stars(hipparcos_raw):
            if star.hip_id is not None:
                positions.setdefault(star.hip_id.removeprefix("HIP "), (star.ra_deg, star.dec_deg))
        for line in hipparcos_raw.read_text(encoding="ascii").splitlines():
            fields = line.split("|")
            if len(fields) < 5 or not fields[1].strip() or not fields[3].strip():
                continue
            match = re.fullmatch(r"(\d{1,2}) (\d{1,2}) ([\d.]+)", fields[3].strip())
            dec_match = re.fullmatch(r"([+-])(\d{1,2}) (\d{1,2}) ([\d.]+)", fields[4].strip())
            if match is None or dec_match is None:
                continue
            hours, minutes, seconds = map(float, match.groups())
            degrees, arcminutes, arcseconds = map(float, dec_match.groups()[1:])
            dec = degrees + arcminutes / 60.0 + arcseconds / 3600.0
            positions.setdefault(
                fields[1].strip(),
                (
                    15.0 * (hours + minutes / 60.0 + seconds / 3600.0),
                    -dec if dec_match.group(1) == "-" else dec,
                ),
            )
    return positions


def import_iau_stick_figures(
    source: str | Path,
    star_store: str | Path,
    destination: str | Path,
    *,
    hipparcos_raw: str | Path | None = None,
) -> int:
    """Write loader-compatible line geometry; boundaries remain the existing IAU boundaries."""
    source_path, destination_path = Path(source), Path(destination)
    positions = _positions(Path(star_store), None if hipparcos_raw is None else Path(hipparcos_raw))
    features = []
    missing: set[str] = set()
    for abbreviation, paths in _constellation_ids(source_path):
        coordinates = []
        for path in paths:
            try:
                coordinates.append([[*positions[hip]] for hip in path])
            except KeyError:
                missing.update(hip for hip in path if hip not in positions)
        features.append(
            {
                "type": "Feature",
                "id": abbreviation,
                "properties": {
                    "catalogue": "IAU/MacRobert",
                    "version": "CC-BY-4.0",
                    "source_id": "constellation_lines_iau.dat",
                },
                "geometry": {"type": "MultiLineString", "coordinates": coordinates},
            }
        )
    if missing:
        raise ValueError(f"missing Hipparcos positions: {', '.join(sorted(missing))}")
    destination_path.mkdir(parents=True, exist_ok=True)
    payload = {"type": "FeatureCollection", "features": features}
    (destination_path / "constellations.lines.json").write_text(
        json.dumps(payload, indent=2) + "\n", encoding="utf-8"
    )
    boundaries = Path("data/fixtures/constellations/constellations.bounds.json")
    if boundaries.resolve() != (destination_path / boundaries.name).resolve():
        copy2(boundaries, destination_path / boundaries.name)
    (destination_path / "SOURCE.md").write_text(
        "# IAU stick figures\n\n"
        "Source: dcf21/constellation-stick-figures, constellation_lines_iau.dat, "
        "commit 75d29c207bbd752023c447ddd1f9f4ff0eb47538.\n\n"
        "Licence decision: CC-BY 4.0, following the upstream README's explicit "
        "statement for the IAU/MacRobert design.\n",
        encoding="utf-8",
    )
    return len(features)
