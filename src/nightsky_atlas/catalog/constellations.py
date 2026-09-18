"""Constellation line and boundary geometry.

Constellation geometry is observing furniture, not catalogue objects: it is
loaded from documented source fixtures and normalized to straight RA/Dec
segments before projection.

Coordinate fields are ``[ra_deg, dec_deg]`` and RA increases eastward, matching
the internal convention.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from nightsky_atlas.catalog.models import Provenance

__all__ = [
    "CATALOGUE",
    "CONSTELLATION_NAMES",
    "VERSION",
    "ConstellationCatalogue",
    "ConstellationSegment",
    "constellation_name",
    "load_constellations",
]

CATALOGUE = "d3-celestial"
VERSION = "master"
DEFAULT_FIXTURE_DIR = Path("data/fixtures/constellations")
LINES_FILENAME = "constellations.lines.json"
BOUNDARIES_FILENAME = "constellations.bounds.json"

# IAU three-letter abbreviations to full constellation names.  This is factual
# reference data (no creative content) used only to label overview maps. The
# vendored geometry has separate provenance for the IAU/MacRobert stick figures
# and d3-celestial boundary polygons; see the fixture SOURCE.md.
CONSTELLATION_NAMES: dict[str, str] = {
    "And": "Andromeda",
    "Ant": "Antlia",
    "Aps": "Apus",
    "Aqr": "Aquarius",
    "Aql": "Aquila",
    "Ara": "Ara",
    "Ari": "Aries",
    "Aur": "Auriga",
    "Boo": "Boötes",
    "Cae": "Caelum",
    "Cam": "Camelopardalis",
    "Cnc": "Cancer",
    "CVn": "Canes Venatici",
    "CMa": "Canis Major",
    "CMi": "Canis Minor",
    "Cap": "Capricornus",
    "Car": "Carina",
    "Cas": "Cassiopeia",
    "Cen": "Centaurus",
    "Cep": "Cepheus",
    "Cet": "Cetus",
    "Cha": "Chamaeleon",
    "Cir": "Circinus",
    "Col": "Columba",
    "Com": "Coma Berenices",
    "CrA": "Corona Australis",
    "CrB": "Corona Borealis",
    "Crv": "Corvus",
    "Crt": "Crater",
    "Cru": "Crux",
    "Cyg": "Cygnus",
    "Del": "Delphinus",
    "Dor": "Dorado",
    "Dra": "Draco",
    "Equ": "Equuleus",
    "Eri": "Eridanus",
    "For": "Fornax",
    "Gem": "Gemini",
    "Gru": "Grus",
    "Her": "Hercules",
    "Hor": "Horologium",
    "Hya": "Hydra",
    "Hyi": "Hydrus",
    "Ind": "Indus",
    "Lac": "Lacerta",
    "Leo": "Leo",
    "LMi": "Leo Minor",
    "Lep": "Lepus",
    "Lib": "Libra",
    "Lup": "Lupus",
    "Lyn": "Lynx",
    "Lyr": "Lyra",
    "Men": "Mensa",
    "Mic": "Microscopium",
    "Mon": "Monoceros",
    "Mus": "Musca",
    "Nor": "Norma",
    "Oct": "Octans",
    "Oph": "Ophiuchus",
    "Ori": "Orion",
    "Pav": "Pavo",
    "Peg": "Pegasus",
    "Per": "Perseus",
    "Phe": "Phoenix",
    "Pic": "Pictor",
    "Psc": "Pisces",
    "PsA": "Piscis Austrinus",
    "Pup": "Puppis",
    "Pyx": "Pyxis",
    "Ret": "Reticulum",
    "Sge": "Sagitta",
    "Sgr": "Sagittarius",
    "Sco": "Scorpius",
    "Scl": "Sculptor",
    "Sct": "Scutum",
    "Ser": "Serpens",
    "Sex": "Sextans",
    "Tau": "Taurus",
    "Tel": "Telescopium",
    "Tri": "Triangulum",
    "TrA": "Triangulum Australe",
    "Tuc": "Tucana",
    "UMa": "Ursa Major",
    "UMi": "Ursa Minor",
    "Vel": "Vela",
    "Vir": "Virgo",
    "Vol": "Volans",
    "Vul": "Vulpecula",
}


def constellation_name(abbreviation: str) -> str:
    """Return the full IAU name for a constellation abbreviation.

    Unknown abbreviations are returned unchanged so a future fixture addition
    still labels sensibly instead of failing the build.
    """
    return CONSTELLATION_NAMES.get(abbreviation, abbreviation)


@dataclass(frozen=True, slots=True)
class ConstellationSegment:
    """One straight RA/Dec segment of a line or boundary.

    ``constellation_id`` is the source constellation abbreviation (``And``);
    it is kept so overview maps can group segments and place constellation
    names without re-parsing the fixture.
    """

    id: str
    ra1_deg: float
    dec1_deg: float
    ra2_deg: float
    dec2_deg: float
    provenance: Provenance
    constellation_id: str = ""

    def __post_init__(self) -> None:
        for name in ("ra1_deg", "dec1_deg", "ra2_deg", "dec2_deg"):
            if not math.isfinite(getattr(self, name)):
                raise ValueError(f"{name} must be finite")
        if not -90.0 <= self.dec1_deg <= 90.0 or not -90.0 <= self.dec2_deg <= 90.0:
            raise ValueError("declination must be within [-90, 90]")


@dataclass(frozen=True, slots=True)
class ConstellationCatalogue:
    """Normalized constellation stick figures and boundary segments."""

    lines: tuple[ConstellationSegment, ...] = ()
    boundaries: tuple[ConstellationSegment, ...] = ()

    @property
    def line_count(self) -> int:
        """Number of stick-figure segments."""
        return len(self.lines)

    @property
    def boundary_count(self) -> int:
        """Number of deduplicated boundary segments."""
        return len(self.boundaries)


def _load_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid constellation JSON {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"constellation JSON root must be an object: {path}")
    return data


def _vertices(polyline: list[Any], source: str) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for point in polyline:
        if not isinstance(point, (list, tuple)) or len(point) < 2:
            raise ValueError(f"malformed coordinate in {source}: {point!r}")
        ra_deg = float(point[0])
        dec_deg = float(point[1])
        if not math.isfinite(ra_deg) or not math.isfinite(dec_deg):
            raise ValueError(f"non-finite coordinate in {source}: {point!r}")
        points.append((ra_deg, dec_deg))
    return points


def _line_segments(data: dict[str, Any]) -> tuple[ConstellationSegment, ...]:
    segments: list[ConstellationSegment] = []
    for feature_index, feature in enumerate(data.get("features", ())):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "MultiLineString":
            continue
        properties = feature.get("properties", {})
        provenance = Provenance(
            catalogue=str(properties.get("catalogue", CATALOGUE)),
            version=str(properties.get("version", VERSION)),
            source_id=str(properties.get("source_id", "lines")),
        )
        constellation_id = str(feature.get("id", ""))
        for path_index, polyline in enumerate(geometry.get("coordinates", ())):
            vertices = _vertices(polyline, LINES_FILENAME)
            for index in range(len(vertices) - 1):
                (ra1, dec1), (ra2, dec2) = vertices[index], vertices[index + 1]
                if (ra1, dec1) == (ra2, dec2):
                    continue
                segments.append(
                    ConstellationSegment(
                        id=f"constellation-line:{feature_index}:{path_index}:{index}",
                        ra1_deg=ra1,
                        dec1_deg=dec1,
                        ra2_deg=ra2,
                        dec2_deg=dec2,
                        provenance=provenance,
                        constellation_id=constellation_id,
                    )
                )
    return tuple(segments)


def _boundary_segments(data: dict[str, Any]) -> tuple[ConstellationSegment, ...]:
    provenance = Provenance(catalogue=CATALOGUE, version=VERSION, source_id="boundaries")
    seen: set[tuple[tuple[float, float], tuple[float, float]]] = set()
    segments: list[ConstellationSegment] = []
    for feature_index, feature in enumerate(data.get("features", ())):
        geometry = feature.get("geometry", {})
        if geometry.get("type") != "Polygon":
            continue
        constellation_id = str(feature.get("id", ""))
        for ring_index, ring in enumerate(geometry.get("coordinates", ())):
            vertices = _vertices(ring, BOUNDARIES_FILENAME)
            for index in range(len(vertices) - 1):
                start, end = vertices[index], vertices[index + 1]
                if start == end:
                    continue
                key_a = (round(start[0], 3), round(start[1], 3))
                key_b = (round(end[0], 3), round(end[1], 3))
                key = (key_a, key_b) if key_a <= key_b else (key_b, key_a)
                if key in seen:
                    continue
                seen.add(key)
                segments.append(
                    ConstellationSegment(
                        id=f"constellation-boundary:{feature_index}:{ring_index}:{index}",
                        ra1_deg=start[0],
                        dec1_deg=start[1],
                        ra2_deg=end[0],
                        dec2_deg=end[1],
                        provenance=provenance,
                        constellation_id=constellation_id,
                    )
                )
    return tuple(segments)


def load_constellations(
    directory: str | Path = DEFAULT_FIXTURE_DIR,
) -> ConstellationCatalogue:
    """Load the vendored constellation fixture directory."""
    root = Path(directory)
    lines_path = root / LINES_FILENAME
    boundaries_path = root / BOUNDARIES_FILENAME
    lines = _line_segments(_load_json(lines_path)) if lines_path.exists() else ()
    boundaries = _boundary_segments(_load_json(boundaries_path)) if boundaries_path.exists() else ()
    return ConstellationCatalogue(lines=lines, boundaries=boundaries)
