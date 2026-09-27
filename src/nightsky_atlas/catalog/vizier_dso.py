"""Deterministic VizieR ingestion and conservative DSO cross-matching."""

from __future__ import annotations

import csv
import hashlib
import json
import math
import re
import urllib.parse
import urllib.request
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

from nightsky_atlas.catalog.models import CatalogSourceRecord, DeepSkyObject, DsoType, Provenance
from nightsky_atlas.catalog.observing_lists import canonical_designation

__all__ = [
    "VIZIER_CATALOGUES",
    "VizierImportResult",
    "crossmatch_vizier_objects",
    "download_vizier_catalogues",
    "format_vizier_designation",
    "import_vizier_catalogues",
    "iter_vizier_objects",
    "parse_vizier_table",
]

VIZIER_BASE_URL = "https://vizier.cds.unistra.fr/viz-bin/asu-tsv"
VIZIER_ACKNOWLEDGEMENT = (
    "This research has made use of the VizieR catalogue access tool, CDS, Strasbourg, France "
    "(DOI: 10.26093/cds/vizier)."
)


@dataclass(frozen=True, slots=True)
class VizierCatalogueSpec:
    catalogue_id: str
    table: str
    name: str
    reference: str
    coordinate_frame: str
    designation_field: str
    ra_field: str
    dec_field: str
    normalized_ra_field: str
    normalized_dec_field: str
    object_type: DsoType
    subtype: str
    major_field: str | None = None
    minor_field: str | None = None
    raw_alias_fields: tuple[str, ...] = ()
    metadata_fields: tuple[str, ...] = ()
    area_field_deg2: str | None = None
    position_angle_field: str | None = None
    major_field_scale: float = 1.0
    minor_field_scale: float = 1.0
    vizier_id: str | None = None
    query_filters: tuple[tuple[str, str], ...] = ()
    row_filter_field: str | None = None
    row_filter_values: tuple[str, ...] = ()
    prefix_filter: str | None = None
    designation_pattern: str | None = None
    magnitude_field: str | None = None
    member_count_field: str | None = None
    members_table: str | None = None
    group_field: str | None = None
    member_designation_field: str | None = None
    member_component_field: str | None = None
    alias_only: bool = False
    version_note: str = "Current VizieR table; exact retrieval is recorded in the manifest."
    license_or_usage: str = (
        "No blanket redistribution licence asserted; consult the original "
        "publication/rights holder."
    )

    @property
    def source_url(self) -> str:
        source_id = self.vizier_id or self.catalogue_id
        return f"https://vizier.cds.unistra.fr/viz-bin/VizieR?-source={source_id}"


VIZIER_CATALOGUES: tuple[VizierCatalogueSpec, ...] = (
    VizierCatalogueSpec(
        "VII/20",
        "VII/20/catalog",
        "Catalogue of HII Regions (Sharpless 1959)",
        "1959ApJS....4..257S",
        "FK4, equinox/epoch B1900.0",
        "Sh2",
        "RA1900",
        "DE1900",
        "_RAJ2000",
        "_DEJ2000",
        DsoType.BRIGHT_NEBULA,
        "HII region",
        major_field="Diam",
        raw_alias_fields=("Name",),
    ),
    VizierCatalogueSpec(
        "VII/7A",
        "VII/7A/ldn",
        "Lynds' Catalogue of Dark Nebulae (LDN)",
        "1962ApJS....7....1L",
        "FK4, equinox/epoch B1950.0",
        "LDN",
        "RA1950",
        "DE1950",
        "_RAJ2000",
        "_DEJ2000",
        DsoType.DARK_NEBULA,
        "dark nebula",
        # Lynds2 is an update-sequence number, not a stable cross-catalogue ID.
        # Bare numbers can collide with unrelated catalogue designations.
        raw_alias_fields=("Barn",),
        area_field_deg2="Area",
    ),
    VizierCatalogueSpec(
        "VII/9",
        "VII/9/catalog",
        "Lynds' Catalogue of Bright Nebulae (LBN)",
        "1965ApJS...12..163L",
        "FK4, equinox/epoch B1950.0",
        "Seq",
        "RA1950",
        "DE1950",
        "_RAJ2000",
        "_DEJ2000",
        DsoType.BRIGHT_NEBULA,
        "bright nebula",
        major_field="Diam1",
        minor_field="Diam2",
        raw_alias_fields=("Name",),
    ),
    VizierCatalogueSpec(
        "VII/21",
        "VII/21/catalog",
        "Catalogue of Reflection Nebulae (van den Bergh 1966)",
        "1966AJ.....71..990V",
        "J2000.0 position from SIMBAD; original catalogue also records Galactic coordinates",
        "VdB",
        "_RA",
        "_DE",
        "_RAJ2000",
        "_DEJ2000",
        DsoType.BRIGHT_NEBULA,
        "reflection nebula",
        major_field="BRadMax",
        minor_field="RRadMax",
        major_field_scale=2.0,
        minor_field_scale=2.0,
        version_note="Corrected VizieR version dated 2022-11-13.",
    ),
    VizierCatalogueSpec(
        "VII/220A",
        "VII/220A/barnard",
        "Barnard's Catalogue of 349 Dark Objects in the Sky (Barnard 1927)",
        "1927cdos.book.....B",
        "FK4, equinox/epoch B1875.0",
        "Barn",
        "RA1875",
        "DE1875",
        "_RAJ2000",
        "_DEJ2000",
        DsoType.DARK_NEBULA,
        "dark nebula",
        major_field="Diam",
    ),
    VizierCatalogueSpec(
        "VII/92A:Collinder",
        "VII/92A/catalog",
        "Collinder open clusters",
        "Lynga 1987, Catalogue of Open Cluster Data (5th ed.), VII/92A",
        "FK4, equinox/epoch B1950.0",
        "ClNum",
        "RA1950",
        "DE1950",
        "_RA.icrs",
        "_DE.icrs",
        DsoType.OPEN_CLUSTER,
        "open cluster; Lynga sequence 6",
        major_field="Diam",
        raw_alias_fields=("OCL",),
        vizier_id="VII/92A",
        metadata_fields=("ClTyp", "Members.320", "TrRich", "totMag.422"),
        query_filters=(("ClSeq", "6"),),
        row_filter_field="ClSeq",
        row_filter_values=("6",),
    ),
    VizierCatalogueSpec(
        "VII/92A:Melotte",
        "VII/92A/catalog",
        "Melotte open clusters",
        "Lynga 1987, Catalogue of Open Cluster Data (5th ed.), VII/92A",
        "FK4, equinox/epoch B1950.0",
        "ClNum",
        "RA1950",
        "DE1950",
        "_RA.icrs",
        "_DE.icrs",
        DsoType.OPEN_CLUSTER,
        "open cluster; Lynga sequence 27",
        major_field="Diam",
        raw_alias_fields=("OCL",),
        vizier_id="VII/92A",
        metadata_fields=("ClTyp", "Members.320", "TrRich", "totMag.422"),
        query_filters=(("ClSeq", "27"),),
        row_filter_field="ClSeq",
        row_filter_values=("27",),
    ),
    VizierCatalogueSpec(
        "VII/92A:Stock",
        "VII/92A/catalog",
        "Stock open clusters",
        "Lynga 1987, Catalogue of Open Cluster Data (5th ed.), VII/92A",
        "FK4, equinox/epoch B1950.0",
        "ClNum",
        "RA1950",
        "DE1950",
        "_RA.icrs",
        "_DE.icrs",
        DsoType.OPEN_CLUSTER,
        "open cluster; Lynga sequence 11",
        major_field="Diam",
        raw_alias_fields=("OCL",),
        vizier_id="VII/92A",
        metadata_fields=("ClTyp", "Members.320", "TrRich", "totMag.422"),
        query_filters=(("ClSeq", "11"),),
        row_filter_field="ClSeq",
        row_filter_values=("11",),
    ),
    VizierCatalogueSpec(
        "IV/24:AbellPN",
        "IV/24/table1",
        "Abell planetary nebulae in Kohoutek CGPN",
        "2001A&A...378..843K",
        "FK4, equinox/epoch B1950.0; ICRS computed by VizieR",
        "Name",
        "RAB1950",
        "DEB1950",
        "_RAJ2000",
        "_DEJ2000",
        DsoType.PLANETARY_NEBULA,
        "Abell planetary nebula",
        raw_alias_fields=("PK",),
        vizier_id="IV/24",
        designation_pattern=r"^A\s*\d+$",
        row_filter_field="f_PK",
        row_filter_values=("", "*"),
    ),
    VizierCatalogueSpec(
        "VII/202:Palomar",
        "VII/202/catalog",
        "Palomar globular clusters (Harris catalogue)",
        "1996AJ....112.1487H",
        "J2000.0, FK5/ICRS-compatible coordinates computed by VizieR",
        "ID",
        "RAJ2000",
        "DEJ2000",
        "_RAJ2000",
        "_DEJ2000",
        DsoType.GLOBULAR_CLUSTER,
        "Palomar globular cluster",
        vizier_id="VII/202",
        prefix_filter="Pal",
        magnitude_field="Vt",
        raw_alias_fields=("Name",),
        metadata_fields=("MVt", "Rh", "Rc", "muV", "[Fe/H]"),
    ),
    VizierCatalogueSpec(
        "VII/202:Terzan",
        "VII/202/catalog",
        "Terzan globular clusters (Harris catalogue)",
        "1996AJ....112.1487H",
        "J2000.0, FK5/ICRS-compatible coordinates computed by VizieR",
        "ID",
        "RAJ2000",
        "DEJ2000",
        "_RAJ2000",
        "_DEJ2000",
        DsoType.GLOBULAR_CLUSTER,
        "Terzan globular cluster",
        vizier_id="VII/202",
        prefix_filter="Ter",
        magnitude_field="Vt",
        raw_alias_fields=("Name",),
        metadata_fields=("MVt", "Rh", "Rc", "muV", "[Fe/H]"),
    ),
    VizierCatalogueSpec(
        "VII/213",
        "VII/213/groups",
        "Hickson Compact Groups (Hickson 1982-1994)",
        "1982ApJ...255..382H",
        "FK4, equinox/epoch B1950.0; ICRS computed by VizieR",
        "HCG",
        "RA1950",
        "DE1950",
        "_RAJ2000",
        "_DEJ2000",
        DsoType.GALAXY_CLUSTER,
        "Hickson compact galaxy group",
        major_field="AngSize",
        magnitude_field="Totmag",
        member_count_field="MCount",
        vizier_id="VII/213",
        members_table="VII/213/galaxies",
        group_field="HCG",
        member_designation_field="Names",
        member_component_field="m_HCG",
    ),
    VizierCatalogueSpec(
        "VII/74A",
        "VII/74A/table2",
        "Arp Atlas of Peculiar Galaxies (Arp 1966)",
        "1966ApJS....14....1A",
        "FK4, equinox/epoch B1970.0; ICRS computed by VizieR",
        "APG",
        "RA1970",
        "DE1970",
        "_RA.icrs",
        "_DE.icrs",
        DsoType.GALAXY,
        "Arp peculiar-galaxy identifier",
        raw_alias_fields=("Name",),
        vizier_id="VII/74A",
        alias_only=True,
    ),
)

_SPEC_BY_ID = {spec.catalogue_id: spec for spec in VIZIER_CATALOGUES}
_NUMBER = re.compile(r"\d+[A-Za-z]?")
_BARNARD_IDS = re.compile(r"(?:B\s*)?\d+[A-Za-z]?", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class VizierImportResult:
    objects: tuple[DeepSkyObject, ...]
    decisions: tuple[dict[str, object], ...]
    counts: dict[str, dict[str, int]]


def _field_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.casefold())


def _field(row: Mapping[str, str], name: str | None) -> str | None:
    if name is None:
        return None
    key = _field_key(name)
    for candidate, value in row.items():
        if _field_key(candidate) == key:
            text = (value or "").strip()
            if text and text not in {"~", "---", "null", "NULL"}:
                return text
    return None


def _float(row: Mapping[str, str], name: str | None) -> float | None:
    value = _field(row, name)
    if value is None:
        return None
    try:
        number = float(value)
    except ValueError:
        return None
    return number if math.isfinite(number) else None


def _coordinate(value: str | None, *, ra: bool) -> float | None:
    if value is None:
        return None
    text = value.strip()
    try:
        if ":" not in text and len(text.split()) != 3:
            number = float(text)
            return number % 360.0 if ra else number
        parts = text.replace(":", " ").split()
        first = float(parts[0])
        sign = -1.0 if first < 0.0 or text.startswith("-") else 1.0
        absolute = [abs(first), float(parts[1]), float(parts[2])]
        result = sign * (absolute[0] + absolute[1] / 60.0 + absolute[2] / 3600.0)
        return result * 15.0 if ra else result
    except (ValueError, IndexError):
        return None


def format_vizier_designation(catalogue_id: str, value: str) -> str:
    """Format a catalogue number without changing its source identity."""
    if catalogue_id not in _SPEC_BY_ID:
        raise ValueError(f"unsupported VizieR catalogue {catalogue_id}")
    token = value.strip()
    if not token:
        raise ValueError(f"empty designation for {catalogue_id}")
    match = _NUMBER.search(token)
    if match is None:
        raise ValueError(f"malformed {catalogue_id} designation: {value!r}")
    number = match.group(0)
    prefix = {
        "VII/20": "Sh2-",
        "VII/7A": "LDN ",
        "VII/9": "LBN ",
        "VII/21": "vdB ",
        "VII/220A": "B ",
        "VII/92A:Collinder": "Cr ",
        "VII/92A:Melotte": "Mel ",
        "VII/92A:Stock": "Stock ",
        "IV/24:AbellPN": "Abell ",
        "VII/202:Palomar": "Pal ",
        "VII/202:Terzan": "Ter ",
        "VII/213": "HCG ",
        "VII/74A": "Arp ",
    }[catalogue_id]
    return f"{prefix}{number}"


def _aliases(
    row: Mapping[str, str], spec: VizierCatalogueSpec, designation: str
) -> tuple[str, ...]:
    found: list[str] = []
    for field_name in spec.raw_alias_fields:
        value = _field(row, field_name)
        if value is None:
            continue
        if field_name == "Barn":
            found.extend(
                f"B {match.group(0).lstrip('B').strip()}" for match in _BARNARD_IDS.finditer(value)
            )
        elif field_name == "PK" and spec.catalogue_id == "IV/24:AbellPN":
            found.append(f"PK {value.strip()}")
        elif field_name == "OCL":
            found.append(f"OCL {value.strip()}")
        else:
            found.extend(part.strip() for part in re.split(r"[,;/]", value) if part.strip())
    if spec.catalogue_id == "VII/213":
        number = _NUMBER.search(designation)
        if number is not None and number.group(0).isdigit():
            found.append(f"HCG{int(number.group(0)):03d}")
    unique: list[str] = []
    for alias in found:
        if (
            alias
            and canonical_designation(alias) != canonical_designation(designation)
            and alias not in unique
        ):
            unique.append(alias)
    return tuple(unique)


def _group_members(
    text: str,
    group_field: str,
    designation_field: str,
    component_field: str | None = None,
) -> dict[str, tuple[str, ...]]:
    lines = [
        line.rstrip("\r\n")
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    header_index = next(
        (
            i
            for i, line in enumerate(lines)
            if _field_key(group_field) in {_field_key(v) for v in line.split("\t")}
        ),
        None,
    )
    if header_index is None:
        raise ValueError(f"VizieR group-member table has no {group_field!r} header")
    header = [item.strip() for item in lines[header_index].split("\t")]
    members: dict[str, list[str]] = {}
    for values in csv.reader(lines[header_index + 1 :], delimiter="\t"):
        if not values or all(not value.strip() for value in values):
            continue
        values += [""] * max(0, len(header) - len(values))
        row = dict(zip(header, values, strict=False))
        group = _field(row, group_field)
        designation = _field(row, designation_field)
        component = _field(row, component_field)
        if group:
            member_id = designation or (
                f"HCG {int(group)}{component.lower()}" if component else None
            )
            if member_id:
                members.setdefault(group, []).append(member_id)
    return {key: tuple(sorted(set(value))) for key, value in members.items()}


def _source_table_rows(text: str) -> int:
    lines = [
        line for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")
    ]
    header = next((index for index, line in enumerate(lines) if "\t" in line), None)
    if header is None:
        return 0
    return sum(
        1
        for row in csv.reader(lines[header + 3 :], delimiter="\t")
        if row and not all(not value.strip() or set(value.strip()) <= {"-", "="} for value in row)
    )


def parse_vizier_table(
    text: str,
    catalogue_id: str,
    *,
    retrieved: str,
    members_by_group: Mapping[str, tuple[str, ...]] | None = None,
) -> tuple[DeepSkyObject, ...]:
    """Parse one VizieR TSV response, requiring its computed ICRS position."""
    spec = _SPEC_BY_ID[catalogue_id]
    lines = [
        line.rstrip("\r\n")
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    header_index = next(
        (
            index
            for index, line in enumerate(lines)
            if _field_key(spec.designation_field) in {_field_key(item) for item in line.split("\t")}
        ),
        None,
    )
    if header_index is None:
        raise ValueError(f"VizieR TSV for {catalogue_id} has no {spec.designation_field!r} header")
    header = [item.strip() for item in lines[header_index].split("\t")]
    objects: list[DeepSkyObject] = []
    for values in csv.reader(lines[header_index + 1 :], delimiter="\t"):
        if not values or all(not value.strip() for value in values):
            continue
        if all(set(value.strip()) <= {"-", "="} for value in values if value.strip()):
            continue
        if len(values) < len(header):
            values.extend([""] * (len(header) - len(values)))
        row = dict(zip(header, values, strict=False))
        source_designation = _field(row, spec.designation_field)
        if source_designation is None:
            continue
        if spec.row_filter_field is not None:
            filter_value = _field(row, spec.row_filter_field) or ""
            if filter_value not in spec.row_filter_values:
                continue
        if spec.prefix_filter is not None and not source_designation.casefold().startswith(
            spec.prefix_filter.casefold()
        ):
            continue
        if (
            spec.designation_pattern is not None
            and re.fullmatch(
                spec.designation_pattern, source_designation.strip(), flags=re.IGNORECASE
            )
            is None
        ):
            continue
        normalized_ra = _coordinate(_field(row, spec.normalized_ra_field), ra=True)
        normalized_dec = _coordinate(_field(row, spec.normalized_dec_field), ra=False)
        if normalized_ra is None or normalized_dec is None or not -90.0 <= normalized_dec <= 90.0:
            raise ValueError(
                f"{catalogue_id} {source_designation}: missing/invalid computed ICRS coordinates"
            )
        designation = format_vizier_designation(catalogue_id, source_designation)
        if catalogue_id == "IV/24:AbellPN":
            match = _NUMBER.search(designation)
            if match is None:
                continue
            designation = f"Abell PN {match.group(0)}"
        major = _float(row, spec.major_field)
        minor = _float(row, spec.minor_field)
        if major is not None:
            major *= spec.major_field_scale
        if minor is not None:
            minor *= spec.minor_field_scale
        area = _float(row, spec.area_field_deg2)
        if major is None and area is not None and area > 0.0:
            major = minor = 120.0 * math.sqrt(area / math.pi)
        if major is not None and major <= 0.0:
            major = None
        if minor is not None and minor <= 0.0:
            minor = None
        raw_fields = tuple(
            sorted((key, value.strip()) for key, value in row.items() if value.strip())
        )
        source = CatalogSourceRecord(
            catalogue_id=catalogue_id,
            designation=designation,
            source_url=spec.source_url,
            reference=spec.reference,
            retrieved=retrieved,
            coordinate_frame=spec.coordinate_frame,
            source_ra=_field(row, spec.ra_field),
            source_dec=_field(row, spec.dec_field),
            raw_fields=raw_fields,
        )
        aliases = _aliases(row, spec, designation)
        if catalogue_id == "IV/24:AbellPN":
            aliases = tuple(dict.fromkeys((*aliases, designation.replace("Abell PN ", "Abell "))))
        objects.append(
            DeepSkyObject(
                id=designation,
                ra_deg=normalized_ra,
                dec_deg=normalized_dec,
                object_type=spec.object_type,
                provenance=Provenance(
                    catalogue=catalogue_id, source_id=designation, version=retrieved
                ),
                major_axis_arcmin=major,
                minor_axis_arcmin=minor,
                cross_ids=aliases,
                semantic_subtype=spec.subtype,
                position_angle_deg=_float(row, spec.position_angle_field),
                magnitude=_float(row, spec.magnitude_field),
                magnitude_band="V" if spec.magnitude_field == "Vt" else None,
                member_designations=(members_by_group or {}).get(source_designation, ()),
                member_count=(
                    int(value)
                    if (value := _float(row, spec.member_count_field)) is not None
                    and value.is_integer()
                    else None
                ),
                catalogue_records=(source,),
            )
        )
    return tuple(objects)


def _query_url(spec: VizierCatalogueSpec, *, extra_output_fields: Iterable[str] = ()) -> str:
    output_fields = list(
        dict.fromkeys(
            field
            for field in (
                spec.designation_field,
                spec.ra_field,
                spec.dec_field,
                spec.major_field,
                spec.minor_field,
                spec.area_field_deg2,
                spec.position_angle_field,
                spec.magnitude_field,
                spec.member_count_field,
                spec.row_filter_field,
                *spec.raw_alias_fields,
                *spec.metadata_fields,
                *extra_output_fields,
            )
            if field is not None
        )
    )
    query = urllib.parse.urlencode(
        [
            ("-source", spec.table),
            ("-out.max", "unlimited"),
            ("-out", ",".join(output_fields)),
            ("-out.add", spec.normalized_ra_field),
            ("-out.add", spec.normalized_dec_field),
            ("-oc.form", "d"),
            *spec.query_filters,
        ]
    )
    return f"{VIZIER_BASE_URL}?{query}"


def download_vizier_catalogues(
    dest_dir: str | Path, *, catalogue_ids: Iterable[str] | None = None
) -> dict[str, Path]:
    """Fetch source snapshots explicitly; normal atlas builds never use network."""
    directory = Path(dest_dir)
    directory.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.now(UTC).replace(microsecond=0).isoformat()
    catalogue_files: dict[str, Path] = {}
    existing_manifest_path = directory / "manifest.json"
    if existing_manifest_path.is_file():
        existing_manifest = json.loads(existing_manifest_path.read_text(encoding="utf-8"))
    else:
        existing_manifest = {}
    manifest_entries = {
        entry["catalogue_id"]: entry for entry in existing_manifest.get("catalogues", [])
    }
    selected = set(catalogue_ids) if catalogue_ids is not None else None
    unknown = selected - set(_SPEC_BY_ID) if selected is not None else set()
    if unknown:
        raise ValueError(f"unknown VizieR catalogue IDs: {', '.join(sorted(unknown))}")
    for spec in VIZIER_CATALOGUES:
        if selected is not None and spec.catalogue_id not in selected:
            continue
        request = urllib.request.Request(
            _query_url(spec),
            headers={"User-Agent": "NightSkyAtlas/0.1 (VizieR catalogue import)"},
        )
        with urllib.request.urlopen(request, timeout=60) as response:
            body = response.read()
        text = body.decode("utf-8")
        if "<html" in text[:1000].casefold() or "access denied" in text[:2000].casefold():
            raise RuntimeError(f"VizieR returned an error page for {spec.catalogue_id}")
        parsed = parse_vizier_table(text, spec.catalogue_id, retrieved=retrieved)
        stem = spec.catalogue_id.replace("/", "_").replace(":", "_")
        target = directory / f"{stem}.tsv"
        target.write_bytes(body)
        catalogue_files[spec.catalogue_id] = target
        manifest_entry = {
            "catalogue_id": spec.catalogue_id,
            "vizier_catalogue_id": spec.vizier_id or spec.catalogue_id,
            "table": spec.table,
            "name": spec.name,
            "reference": spec.reference,
            "version_note": spec.version_note,
            "license_or_usage": spec.license_or_usage,
            "coordinate_frame": spec.coordinate_frame,
            "fields_used": {
                "designation": spec.designation_field,
                "source_ra": spec.ra_field,
                "source_dec": spec.dec_field,
                "normalized_ra": spec.normalized_ra_field,
                "normalized_dec": spec.normalized_dec_field,
                "major_extent": spec.major_field,
                "minor_extent": spec.minor_field,
                "position_angle": spec.position_angle_field,
                "area": spec.area_field_deg2,
                "magnitude": spec.magnitude_field,
                "member_count": spec.member_count_field,
                "aliases": list(spec.raw_alias_fields),
                "catalogue_metadata": list(spec.metadata_fields),
            },
            "query_filters": dict(spec.query_filters),
            "row_filter": {
                "field": spec.row_filter_field,
                "values": list(spec.row_filter_values),
                "designation_pattern": spec.designation_pattern,
                "prefix": spec.prefix_filter,
            },
            "source_url": spec.source_url,
            "query_url": _query_url(spec),
            "retrieved": retrieved,
            "row_count": len(parsed),
            "family_raw_row_count": len(parsed),
            "source_table_row_count": _source_table_rows(text),
            "sha256": hashlib.sha256(body).hexdigest(),
            "raw_file": target.name,
        }
        if spec.members_table:
            member_fields = tuple(
                field
                for field in (
                    spec.group_field,
                    spec.member_designation_field,
                    spec.member_component_field,
                )
                if field is not None
            )
            member_url = _query_url(
                replace(
                    spec,
                    table=spec.members_table,
                    query_filters=(),
                    major_field=None,
                    minor_field=None,
                    magnitude_field=None,
                    member_count_field=None,
                    raw_alias_fields=(),
                ),
                extra_output_fields=member_fields,
            )
            member_req = urllib.request.Request(
                member_url,
                headers={"User-Agent": "NightSkyAtlas/0.1 (VizieR catalogue import)"},
            )
            with urllib.request.urlopen(member_req, timeout=60) as response:
                member_body = response.read()
            member_file = directory / f"{stem}.members.tsv"
            member_file.write_bytes(member_body)
            manifest_entry["members"] = {
                "table": spec.members_table,
                "query_url": member_url,
                "raw_file": member_file.name,
                "sha256": hashlib.sha256(member_body).hexdigest(),
                "row_count": _source_table_rows(member_body.decode("utf-8")),
                "fields_used": list(member_fields),
            }
        manifest_entries[spec.catalogue_id] = manifest_entry
    manifest = {
        "service_acknowledgement": VIZIER_ACKNOWLEDGEMENT,
        "service_doi": "10.26093/cds/vizier",
        "catalogues": [manifest_entries[key] for key in sorted(manifest_entries)],
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return catalogue_files


def iter_vizier_objects(
    raw_dir: str | Path, *, manifest_path: str | Path | None = None
) -> Iterator[DeepSkyObject]:
    """Yield records from cached VizieR TSVs, checking the fetch manifest hash."""
    root = Path(raw_dir)
    manifest_file = Path(manifest_path) if manifest_path is not None else root / "manifest.json"
    if not manifest_file.is_file():
        raise FileNotFoundError(f"VizieR source manifest not found: {manifest_file}")
    manifest = json.loads(manifest_file.read_text(encoding="utf-8"))
    entries = {entry["catalogue_id"]: entry for entry in manifest.get("catalogues", [])}
    for spec in VIZIER_CATALOGUES:
        if spec.catalogue_id not in entries:
            continue
        source = root / f"{spec.catalogue_id.replace('/', '_').replace(':', '_')}.tsv"
        if not source.exists():
            raise FileNotFoundError(f"missing {spec.catalogue_id} snapshot: {source}")
        entry = entries.get(spec.catalogue_id)
        if entry is None:
            raise ValueError(f"source manifest has no entry for {spec.catalogue_id}")
        body = source.read_bytes()
        digest = hashlib.sha256(body).hexdigest()
        if digest != entry.get("sha256"):
            raise ValueError(f"source checksum mismatch for {source}")
        retrieved = entry.get("retrieved")
        if not retrieved:
            raise ValueError(f"source manifest has no retrieval date for {spec.catalogue_id}")
        members_by_group: dict[str, tuple[str, ...]] = {}
        if spec.members_table and spec.group_field and spec.member_designation_field:
            member_source = (
                root / f"{spec.catalogue_id.replace('/', '_').replace(':', '_')}.members.tsv"
            )
            member_entry = entry.get("members")
            if member_source.is_file() and member_entry:
                member_body = member_source.read_bytes()
                if hashlib.sha256(member_body).hexdigest() != member_entry.get("sha256"):
                    raise ValueError(f"source checksum mismatch for {member_source}")
                members_by_group = _group_members(
                    member_body.decode("utf-8"),
                    spec.group_field,
                    spec.member_designation_field,
                    spec.member_component_field,
                )
        yield from parse_vizier_table(
            body.decode("utf-8"),
            spec.catalogue_id,
            retrieved=retrieved,
            members_by_group=members_by_group,
        )


def _angular_distance_arcmin(left: DeepSkyObject, right: DeepSkyObject) -> float:
    ra1, dec1, ra2, dec2 = map(
        math.radians, (left.ra_deg, left.dec_deg, right.ra_deg, right.dec_deg)
    )
    delta_ra = ra2 - ra1
    cosine = math.sin(dec1) * math.sin(dec2) + math.cos(dec1) * math.cos(dec2) * math.cos(delta_ra)
    return math.degrees(math.acos(min(1.0, max(-1.0, cosine)))) * 60.0


def _unit_vector(obj: DeepSkyObject) -> tuple[float, float, float]:
    ra = math.radians(obj.ra_deg)
    dec = math.radians(obj.dec_deg)
    return math.cos(dec) * math.cos(ra), math.cos(dec) * math.sin(ra), math.sin(dec)


def _compatible_types(left: DsoType, right: DsoType) -> bool:
    if left == right:
        return True
    bright = {DsoType.BRIGHT_NEBULA, DsoType.SUPERNOVA_REMNANT}
    return left in bright and right in bright


def _match_radii(record: DeepSkyObject, candidate: DeepSkyObject) -> tuple[float, float]:
    """Return clear-match and ambiguity-search radii in arcmin, extent-aware."""
    sizes = [size for size in (record.major_axis_arcmin, candidate.major_axis_arcmin) if size]
    extent = max(sizes, default=0.0)
    if record.object_type == DsoType.DARK_NEBULA:
        return max(1.5, min(7.0, extent * 0.06)), max(4.0, min(30.0, extent * 0.18))
    if record.object_type == DsoType.OPEN_CLUSTER:
        # Sparse-cluster centres vary; the wider search remains ambiguous unless
        # there is a single well-supported candidate.
        return max(5.0, min(18.0, extent * 0.10)), max(20.0, min(90.0, extent * 0.35))
    return max(2.0, min(12.0, extent * 0.07)), max(8.0, min(60.0, extent * 0.20))


def _extent_compatible(left: DeepSkyObject, right: DeepSkyObject) -> bool:
    """Reject a confident positional merge when reported sizes strongly disagree."""
    left_size = left.major_axis_arcmin
    right_size = right.major_axis_arcmin
    if left_size is None or right_size is None:
        return True
    return max(left_size, right_size) / min(left_size, right_size) <= 4.0


def _merge_source_record(
    canonical: DeepSkyObject,
    record: DeepSkyObject,
    *,
    decision: str,
    matched_id: str,
    distance: float | None,
    confidence: str,
    reason: str,
) -> DeepSkyObject:
    updated_records = tuple(
        replace(
            item,
            crossmatch_decision=decision,
            matched_object_id=matched_id,
            match_distance_arcmin=distance,
            match_confidence=confidence,
            match_reason=reason,
        )
        for item in record.catalogue_records
    )
    aliases = list(canonical.cross_ids)
    for alias in (record.id, *record.cross_ids):
        if alias != canonical.id and alias not in aliases:
            aliases.append(alias)
    source_records = canonical.catalogue_records + tuple(
        item for item in updated_records if item not in canonical.catalogue_records
    )
    return replace(
        canonical,
        cross_ids=tuple(aliases),
        catalogue_records=source_records,
        semantic_subtype=canonical.semantic_subtype or record.semantic_subtype,
        member_designations=tuple(
            sorted(set((*canonical.member_designations, *record.member_designations)))
        ),
        member_count=canonical.member_count or record.member_count,
    )


def crossmatch_vizier_objects(
    openngc_objects: Iterable[DeepSkyObject],
    vizier_objects: Iterable[DeepSkyObject],
) -> VizierImportResult:
    """Merge strong identity/position matches; retain uncertain rows separately."""
    objects = list(openngc_objects)
    decisions: list[dict[str, object]] = []
    counts = {
        spec.catalogue_id: {
            "raw": 0,
            "new_objects": 0,
            "matched_aliases": 0,
            "uncertain": 0,
            "unmatched_aliases": 0,
        }
        for spec in VIZIER_CATALOGUES
    }
    by_catalogue: dict[str, list[DeepSkyObject]] = {catalogue_id: [] for catalogue_id in counts}
    for record in vizier_objects:
        if record.provenance.catalogue in by_catalogue:
            by_catalogue[record.provenance.catalogue].append(record)

    alias_index: dict[str, set[int]] = {}

    def add_aliases(index: int, obj: DeepSkyObject) -> None:
        for designation in (obj.id, *obj.cross_ids):
            alias_index.setdefault(canonical_designation(designation), set()).add(index)

    for index, obj in enumerate(objects):
        add_aliases(index, obj)

    max_search_chord = 2.0 * math.sin(math.radians(1.5) / 2.0)
    for catalogue_id, catalogue_records in by_catalogue.items():
        records = sorted(catalogue_records, key=lambda item: item.id)
        if not records:
            continue
        tree = cKDTree(np.asarray([_unit_vector(obj) for obj in objects])) if objects else None
        for record in records:
            counts[catalogue_id]["raw"] += 1
            aliases = {canonical_designation(item) for item in (record.id, *record.cross_ids)}
            explicit_indices = sorted(
                {
                    index
                    for alias in aliases
                    for index in alias_index.get(alias, ())
                    if _compatible_types(objects[index].object_type, record.object_type)
                }
            )
            nearby_indices = (
                tree.query_ball_point(_unit_vector(record), max_search_chord)
                if tree is not None
                else []
            )
            candidate_distances: list[tuple[float, int, float]] = []
            for index in nearby_indices:
                candidate = objects[index]
                if not _compatible_types(candidate.object_type, record.object_type):
                    continue
                distance = _angular_distance_arcmin(record, candidate)
                clear_radius, search_radius = _match_radii(record, candidate)
                if distance <= search_radius:
                    if not _extent_compatible(record, candidate):
                        clear_radius = 0.0
                    candidate_distances.append((distance, index, clear_radius))
            candidate_distances.sort(key=lambda item: (item[0], objects[item[1]].id))

            matched_index: int | None = None
            distance: float | None = None
            confidence = "high"
            reason = "no_candidate"
            if len(explicit_indices) == 1:
                matched_index = explicit_indices[0]
                distance = _angular_distance_arcmin(record, objects[matched_index])
                reason = "explicit_cross_identifier"
            elif len(explicit_indices) > 1:
                reason = "ambiguous_explicit_cross_identifiers"
            else:
                close = [
                    item for item in candidate_distances if item[2] > 0.0 and item[0] <= item[2]
                ]
                if len(close) == 1 and len(candidate_distances) == 1:
                    distance, matched_index, _ = close[0]
                    reason = "unique_extent_aware_position_match"
                elif candidate_distances:
                    distance = candidate_distances[0][0]
                    reason = "ambiguous_or_low_confidence_position_match"

            if matched_index is not None:
                matched = objects[matched_index]
                objects[matched_index] = _merge_source_record(
                    matched,
                    record,
                    decision="matched_alias",
                    matched_id=matched.id,
                    distance=distance,
                    confidence=confidence,
                    reason=reason,
                )
                add_aliases(matched_index, objects[matched_index])
                counts[catalogue_id]["matched_aliases"] += 1
                status = "matched_alias"
                canonical_id = matched.id
            else:
                uncertain = bool(candidate_distances or explicit_indices)
                if _SPEC_BY_ID[catalogue_id].alias_only:
                    decision = "uncertain_alias" if uncertain else "unmatched_alias"
                    confidence = "uncertain" if uncertain else "low"
                    if uncertain:
                        counts[catalogue_id]["uncertain"] += 1
                    else:
                        counts[catalogue_id]["unmatched_aliases"] += 1
                    decisions.append(
                        {
                            "catalogue_id": catalogue_id,
                            "designation": record.id,
                            "status": decision,
                            "canonical_id": None,
                            "match_distance_arcmin": distance,
                            "confidence": confidence,
                            "reason": reason,
                        }
                    )
                    continue
                if uncertain:
                    confidence = "uncertain"
                    decision = "uncertain"
                    counts[catalogue_id]["uncertain"] += 1
                else:
                    decision = "new"
                    counts[catalogue_id]["new_objects"] += 1
                updated_record = replace(
                    record,
                    catalogue_records=tuple(
                        replace(
                            item,
                            crossmatch_decision=decision,
                            matched_object_id=record.id,
                            match_distance_arcmin=distance,
                            match_confidence=confidence,
                            match_reason=reason,
                        )
                        for item in record.catalogue_records
                    ),
                )
                objects.append(updated_record)
                add_aliases(len(objects) - 1, updated_record)
                status = decision
                canonical_id = record.id

            decisions.append(
                {
                    "catalogue_id": catalogue_id,
                    "designation": record.id,
                    "status": status,
                    "canonical_id": canonical_id,
                    "match_distance_arcmin": distance,
                    "confidence": confidence,
                    "reason": reason,
                }
            )
    return VizierImportResult(tuple(objects), tuple(decisions), counts)


def import_vizier_catalogues(
    openngc_objects: Iterable[DeepSkyObject],
    vizier_objects: Iterable[DeepSkyObject],
) -> VizierImportResult:
    """Named wrapper for the deterministic merge pipeline."""
    return crossmatch_vizier_objects(openngc_objects, vizier_objects)
