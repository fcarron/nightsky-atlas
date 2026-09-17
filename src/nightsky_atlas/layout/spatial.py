"""Uniform spatial index for the deterministic label optimizer.

The optimizer repeatedly asks which already-placed label boxes and symbols lie
near a candidate box.  Scanning every placed box each time is quadratic in the
number of labels, which dominates dense fields.  ``RectIndex`` stores each
rectangle in every grid cell it touches and answers neighbour queries in
insertion order, so a caller that sums over neighbours sees exactly the same
ordering (and therefore the same floating-point result) as a full linear scan.
"""

from __future__ import annotations

import math

from nightsky_atlas.chart.page import PageRect

__all__ = ["RectIndex"]


class RectIndex[T]:
    """Grid over axis-aligned rectangles with ordered neighbour queries."""

    def __init__(self, cell_mm: float) -> None:
        if cell_mm <= 0.0:
            raise ValueError("cell_mm must be positive")
        self._cell_mm = cell_mm
        self._buckets: dict[tuple[int, int], list[int]] = {}
        self._entries: dict[int, tuple[PageRect, T]] = {}
        self._key_seq: dict[str, int] = {}
        self._seq_cells: dict[int, tuple[tuple[int, int], ...]] = {}
        self._next_seq = 0

    def _cells(self, rect: PageRect, margin_mm: float) -> tuple[tuple[int, int], ...]:
        cell = self._cell_mm
        first_col = math.floor((rect.left_mm - margin_mm) / cell)
        last_col = math.floor((rect.right_mm + margin_mm) / cell)
        first_row = math.floor((rect.top_mm - margin_mm) / cell)
        last_row = math.floor((rect.bottom_mm + margin_mm) / cell)
        return tuple(
            (col, row)
            for col in range(first_col, last_col + 1)
            for row in range(first_row, last_row + 1)
        )

    def _unlink(self, seq: int) -> None:
        for cell in self._seq_cells[seq]:
            bucket = self._buckets[cell]
            bucket.remove(seq)
            if not bucket:
                del self._buckets[cell]

    def set(self, key: str, bounds: PageRect, payload: T) -> None:
        """Insert or move ``key``; an existing key keeps its insertion order."""
        seq = self._key_seq.get(key)
        if seq is None:
            seq = self._next_seq
            self._next_seq += 1
            self._key_seq[key] = seq
        else:
            self._unlink(seq)
        cells = self._cells(bounds, 0.0)
        for cell in cells:
            self._buckets.setdefault(cell, []).append(seq)
        self._seq_cells[seq] = cells
        self._entries[seq] = (bounds, payload)

    def discard(self, key: str) -> None:
        """Remove ``key`` if it is present."""
        seq = self._key_seq.pop(key, None)
        if seq is None:
            return
        self._unlink(seq)
        self._seq_cells.pop(seq, None)
        self._entries.pop(seq, None)

    def query(
        self,
        rect: PageRect,
        *,
        margin_mm: float = 0.0,
        exclude: str | None = None,
    ) -> list[T]:
        """Return payloads near ``rect``, in insertion order."""
        found: set[int] = set()
        for cell in self._cells(rect, margin_mm):
            bucket = self._buckets.get(cell)
            if bucket:
                found.update(bucket)
        if exclude is not None:
            excluded = self._key_seq.get(exclude)
            if excluded is not None:
                found.discard(excluded)
        return [self._entries[seq][1] for seq in sorted(found)]
