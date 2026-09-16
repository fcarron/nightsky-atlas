"""Label construction from a scene.

Labels are built here, never inside the renderer (``AGENTS.md`` section 16).
Priority and mandatory status follow the conceptual ordering in section 14.3.
"""

from __future__ import annotations

from nightsky_atlas.atlas.config import StyleConfig
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.candidates import compass_candidates
from nightsky_atlas.layout.models import Label
from nightsky_atlas.render.symbols import galaxy_ellipse
from nightsky_atlas.render.text import TextMeasurer
from nightsky_atlas.scene.models import ChartScene

__all__ = ["build_dso_labels", "display_name", "label_priority"]

_MESSIER_PRIORITY = 100
_COMMON_NAME_PRIORITY = 90
_BRIGHT_DSO_PRIORITY = 60
_ORDINARY_DSO_PRIORITY = 30
_BRIGHT_MAGNITUDE = 9.0


def _messier_id(dso: DeepSkyObject) -> str | None:
    for cross_id in dso.cross_ids:
        if cross_id.startswith("M") and cross_id[1:].isdigit():
            return cross_id
    return None


def display_name(dso: DeepSkyObject) -> str:
    """Choose a display label: Messier, then common name, then catalogue ID."""
    messier = _messier_id(dso)
    if messier is not None:
        return messier
    if dso.common_name:
        return dso.common_name
    return dso.id


def label_priority(dso: DeepSkyObject) -> tuple[int, bool]:
    """Return ``(priority, mandatory)`` for a deep-sky object."""
    if _messier_id(dso) is not None:
        return _MESSIER_PRIORITY, True
    if dso.common_name:
        return _COMMON_NAME_PRIORITY, True
    if dso.magnitude is not None and dso.magnitude <= _BRIGHT_MAGNITUDE:
        return _BRIGHT_DSO_PRIORITY, True
    return _ORDINARY_DSO_PRIORITY, False


def _exclusion_radius_mm(
    dso: DeepSkyObject, transform: PageTransform, style: StyleConfig
) -> float:
    if dso.object_type == DsoType.GALAXY:
        geometry = galaxy_ellipse(
            dso,
            mm_per_deg=transform.mm_per_deg,
            min_axis_mm=style.dso.min_axis_mm,
            max_axis_mm=style.dso.max_axis_mm,
        )
        if geometry is not None:
            return geometry.major_mm / 2.0
    return style.dso.size_mm / 2.0


def build_dso_labels(
    scene: ChartScene,
    transform: PageTransform,
    style: StyleConfig,
) -> tuple[Label, ...]:
    """Build one label per deep-sky object in the scene."""
    measurer = TextMeasurer(style.label.font_family, style.label.font_size_pt)
    labels: list[Label] = []
    for scene_dso in scene.deep_sky_objects:
        dso = scene_dso.dso
        label_id = f"label:dso:{dso.id}"
        metrics = measurer.measure_mm(display_name(dso))
        anchor = transform.to_page(scene_dso.chart_point)
        candidates = compass_candidates(
            label_id=label_id,
            metrics=metrics,
            anchor=anchor,
            exclusion_radius_mm=_exclusion_radius_mm(dso, transform, style),
            ring_count=style.label.candidate_rings,
            ring_gap_mm=style.label.ring_gap_mm,
        )
        priority, mandatory = label_priority(dso)
        labels.append(
            Label(
                id=label_id,
                target_id=dso.id,
                text=display_name(dso),
                priority=priority,
                mandatory=mandatory,
                candidates=candidates,
            )
        )
    return tuple(labels)