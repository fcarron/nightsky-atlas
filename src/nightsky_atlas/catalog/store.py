"""SQLite-backed indexed store for normalized stars.

SQLite is the simplest storage and query approach that performs adequately for
per-chart star selection: it ships with Python, needs no extra dependency and
supports indexed range queries (``AGENTS.md`` section 9).  A chart query is a
declination/magnitude range plus an RA range, with RA wrapping handled at the
equator and near the poles.
"""

from __future__ import annotations

import math
import sqlite3
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path

from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition

__all__ = ["QueryBox", "StarStore", "build_star_store", "chart_query_box"]

_SCHEMA = """
CREATE TABLE stars (
    id        TEXT PRIMARY KEY,
    ra_deg    REAL NOT NULL,
    dec_deg   REAL NOT NULL,
    magnitude REAL NOT NULL,
    hip_id    TEXT,
    source_id TEXT NOT NULL,
    catalogue TEXT NOT NULL,
    version   TEXT
);
"""

_INSERT = (
    "INSERT OR REPLACE INTO stars "
    "(id, ra_deg, dec_deg, magnitude, hip_id, source_id, catalogue, version) "
    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
)


@dataclass(frozen=True, slots=True)
class QueryBox:
    """A declination range plus an RA range (possibly wrapping through 0h)."""

    ra_min_deg: float
    ra_max_deg: float
    dec_min_deg: float
    dec_max_deg: float

    @property
    def wraps_ra(self) -> bool:
        """Whether the RA range crosses 0/360 degrees."""
        return self.ra_min_deg > self.ra_max_deg


def chart_query_box(definition: ChartDefinition, *, padding_deg: float = 2.0) -> QueryBox:
    """Compute a generous catalogue query box for a chart.

    The box is a superset of the chart field: RA convergence with declination is
    accounted for and extra padding is added.  The scene builder performs the
    exact field test afterwards, so over-selection is safe.
    """
    half_height = definition.height_deg / 2.0 + padding_deg
    dec_min = max(-90.0, definition.center_dec_deg - half_height)
    dec_max = min(90.0, definition.center_dec_deg + half_height)

    worst_dec = min(89.9, max(abs(dec_min), abs(dec_max)))
    cos_dec = math.cos(math.radians(worst_dec))
    if cos_dec < 0.02:
        return QueryBox(0.0, 360.0, dec_min, dec_max)

    half_width = (definition.width_deg / 2.0 + padding_deg) / cos_dec
    if half_width >= 180.0:
        return QueryBox(0.0, 360.0, dec_min, dec_max)

    ra_min = (definition.center_ra_deg - half_width) % 360.0
    ra_max = (definition.center_ra_deg + half_width) % 360.0
    return QueryBox(ra_min, ra_max, dec_min, dec_max)


class StarStore:
    """Read access to a processed SQLite star store."""

    def __init__(self, connection: sqlite3.Connection, path: Path) -> None:
        self._connection = connection
        self.path = path

    @classmethod
    def open(cls, path: str | Path) -> StarStore:
        """Open an existing star store for querying."""
        resolved = Path(path)
        if not resolved.exists():
            raise FileNotFoundError(f"star store not found: {resolved}")
        connection = sqlite3.connect(resolved)
        return cls(connection, resolved)

    def close(self) -> None:
        """Close the underlying database connection."""
        self._connection.close()

    def __enter__(self) -> StarStore:
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def count(self) -> int:
        """Return the number of stored stars."""
        row = self._connection.execute("SELECT COUNT(*) FROM stars").fetchone()
        return int(row[0])

    def query_box(
        self,
        box: QueryBox,
        *,
        magnitude_limit: float = math.inf,
    ) -> list[Star]:
        """Return stars inside a query box brighter than a magnitude limit."""
        sql = (
            "SELECT id, ra_deg, dec_deg, magnitude, hip_id, source_id, catalogue, version "
            "FROM stars WHERE dec_deg >= ? AND dec_deg <= ? AND magnitude <= ?"
        )
        params: list[float] = [box.dec_min_deg, box.dec_max_deg, magnitude_limit]
        if box.wraps_ra:
            sql += " AND (ra_deg >= ? OR ra_deg <= ?)"
        else:
            sql += " AND ra_deg >= ? AND ra_deg <= ?"
        params.extend([box.ra_min_deg, box.ra_max_deg])
        rows = self._connection.execute(sql, params).fetchall()
        return [_row_to_star(row) for row in rows]


def _row_to_star(row: tuple[object, ...]) -> Star:
    return Star(
        id=str(row[0]),
        ra_deg=float(row[1]),  # type: ignore[arg-type]
        dec_deg=float(row[2]),  # type: ignore[arg-type]
        magnitude=float(row[3]),  # type: ignore[arg-type]
        provenance=Provenance(
            catalogue=str(row[6]),
            source_id=str(row[5]),
            version=None if row[7] is None else str(row[7]),
        ),
        hip_id=None if row[4] is None else str(row[4]),
    )


def build_star_store(path: str | Path, stars: Iterable[Star]) -> int:
    """Create a star store, bulk-load ``stars`` and index it.

    Returns the number of rows written.  The store is written atomically from
    the caller's perspective: it is built at a temporary path and moved into
    place only after indexing succeeds.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_suffix(target.suffix + ".tmp")
    temporary.unlink(missing_ok=True)

    connection = sqlite3.connect(temporary)
    try:
        connection.execute("PRAGMA journal_mode=OFF")
        connection.execute("PRAGMA synchronous=OFF")
        connection.executescript(_SCHEMA)
        count = 0
        batch: list[tuple[object, ...]] = []
        for star in stars:
            batch.append(_star_to_row(star))
            count += 1
            if len(batch) >= 50_000:
                connection.executemany(_INSERT, batch)
                batch.clear()
        if batch:
            connection.executemany(_INSERT, batch)
        connection.commit()

        connection.execute("CREATE INDEX stars_dec_mag_idx ON stars(dec_deg, magnitude)")
        connection.execute("CREATE INDEX stars_ra_idx ON stars(ra_deg)")
        connection.execute("ANALYZE")
        connection.commit()
    except Exception:
        connection.close()
        temporary.unlink(missing_ok=True)
        raise
    connection.close()

    target.unlink(missing_ok=True)
    temporary.rename(target)
    return count


def _star_to_row(star: Star) -> tuple[object, ...]:
    return (
        star.id,
        star.ra_deg,
        star.dec_deg,
        star.magnitude,
        star.hip_id,
        star.provenance.source_id,
        star.provenance.catalogue,
        star.provenance.version,
    )


def iter_stars_in_box(store: StarStore, box: QueryBox, magnitude_limit: float) -> Iterator[Star]:
    """Yield stars in a box (convenience wrapper over :meth:`StarStore.query_box`)."""
    yield from store.query_box(box, magnitude_limit=magnitude_limit)