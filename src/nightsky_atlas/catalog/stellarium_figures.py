"""Pinned import of Stellarium's Western (Sky & Telescope) stick figures."""

from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from collections import Counter
from pathlib import Path
from urllib.request import urlopen

from nightsky_atlas.catalog.constellations import CONSTELLATION_NAMES
from nightsky_atlas.catalog.hipparcos import iter_hipparcos_stars

REVISION = "014fbb5e59233d133c22f9811af96b67d05a95c9"
SHA256 = "7c61c6f88f50b84e43e276c3f9f67422faec63f4a13ca8e60c22bfc3da064340"
SOURCE_URL = (
    "https://raw.githubusercontent.com/Stellarium/stellarium-skycultures/"
    f"{REVISION}/western_SnT/index.json"
)


def fetch_stellarium_figures(destination: str | Path) -> Path:
    """Cache the pinned upstream file, verifying it before reuse or import."""
    path = Path(destination)
    if path.exists():
        verify_source(path.read_bytes())
        return path
    with urlopen(SOURCE_URL, timeout=30) as response:
        payload = response.read()
    verify_source(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(payload)
    return path


def verify_source(payload: bytes) -> None:
    digest = hashlib.sha256(payload).hexdigest()
    if digest != SHA256:
        raise ValueError(f"Stellarium western_SnT checksum mismatch: {digest}")


def parse_figures(
    payload: bytes,
) -> tuple[tuple[str, tuple[tuple[str, tuple[int, ...]], ...]], ...]:
    """Normalize upstream paths, preserving HIP order and semantic weight."""
    data = json.loads(payload)
    if data.get("id") != "western_SnT" or not isinstance(data.get("constellations"), list):
        raise ValueError("not a western_SnT sky-culture index")
    figures = []
    seen = set()
    for figure in data["constellations"]:
        abbreviation = figure.get("iau")
        if (
            abbreviation not in CONSTELLATION_NAMES
            or figure.get("id") != f"CON western_SnT {abbreviation}"
        ):
            raise ValueError(f"unknown constellation ID: {figure.get('id')!r}")
        if abbreviation in seen:
            raise ValueError(f"duplicate constellation ID: {abbreviation}")
        seen.add(abbreviation)
        paths = []
        for path in figure.get("lines", []):
            if not isinstance(path, list) or not path:
                raise ValueError(f"malformed HIP path in {abbreviation}")
            weight = "normal"
            if isinstance(path[0], str):
                weight = path[0]
                path = path[1:]
            if weight not in {"bold", "normal", "thin"}:
                raise ValueError(f"unknown constellation style {weight!r} in {abbreviation}")
            if len(path) < 2 or any(type(hip) is not int or hip <= 0 for hip in path):
                raise ValueError(f"invalid HIP path in {abbreviation}: {path!r}")
            hips = tuple(
                hip for index, hip in enumerate(path) if index == 0 or hip != path[index - 1]
            )
            if len(hips) < 2:
                raise ValueError(f"zero-length HIP path in {abbreviation}: {path!r}")
            paths.append((weight, hips))
        figures.append((abbreviation, tuple(paths)))
    return tuple(figures)


def import_stellarium_figures(
    source: str | Path,
    star_store: str | Path,
    destination: str | Path,
    *,
    hipparcos_raw: str | Path | None = None,
) -> dict[str, int]:
    """Resolve HIP identities via the star catalog and write offline geometry."""
    payload = Path(source).read_bytes()
    verify_source(payload)
    figures = parse_figures(payload)
    positions = _positions(Path(star_store), None if hipparcos_raw is None else Path(hipparcos_raw))
    required = {str(hip) for _, paths in figures for _, hips in paths for hip in hips}
    missing = sorted(required - positions.keys(), key=int)
    if missing:
        raise ValueError(
            f"{len(missing)} unresolved Stellarium HIP IDs: {', '.join(missing[:30])}; "
            "supply --hipparcos-raw to resolve stars missing from the Tycho store"
        )
    features = []
    counts: Counter[str] = Counter()
    for abbreviation, paths in figures:
        coordinates = []
        weights = []
        hip_paths = []
        for weight, hips in paths:
            coordinates.append([list(positions[str(hip)]) for hip in hips])
            weights.append(weight)
            hip_paths.append(list(hips))
            counts[weight] += 1
        features.append({
            "type": "Feature",
            "id": abbreviation,
            "properties": {
                "catalogue": "Stellarium Western (Sky & Telescope)",
                "version": REVISION,
                "source_id": "western_SnT/index.json",
                "weights": weights,
                "hip_paths": hip_paths,
            },
            "geometry": {"type": "MultiLineString", "coordinates": coordinates},
        })
    root = Path(destination)
    root.mkdir(parents=True, exist_ok=True)
    output = {"type": "FeatureCollection", "features": features}
    (root / "constellations.lines.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return {"constellations": len(features), **dict(sorted(counts.items()))}


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
