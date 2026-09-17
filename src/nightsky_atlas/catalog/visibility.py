"""Per-type deep-sky visibility evaluation.

A single global magnitude cut is the wrong selection tool: a large galaxy can
have a bright integrated magnitude while its surface brightness is fainter than
the sky, and a planetary nebula is tiny yet easy because its light is
concentrated.  This module evaluates each object type against explicit,
deterministic limits derived from integrated magnitude, mean surface brightness
(:meth:`~nightsky_atlas.catalog.models.DeepSkyObject.surface_brightness_mag_arcsec2`)
and angular size.

These are atlas-selection values, not a telescope simulator: the limits target a
documented aperture/sky class (``AGENTS.md`` section 3).  The result is a
:class:`VisibilityAssessment` with a boolean decision, a 0-100 score for ranking
and short machine-readable reasons for diagnostics.  Observing-list membership
forces an object in regardless of this assessment (``AGENTS.md`` section 15).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Protocol

from nightsky_atlas.catalog.models import DeepSkyObject, DsoType

__all__ = [
    "DEFAULT_LIMITS",
    "VisibilityAssessment",
    "VisibilityEvaluator",
    "VisibilityLimits",
    "evaluate_visibility",
    "evaluator_for",
]


@dataclass(frozen=True, slots=True)
class VisibilityLimits:
    """Selection limits for one edition's target aperture/sky class.

    ``reference_*`` values are the "comfortably visible" ends of the scoring
    ramps (a bright magnitude, a dark-sky surface brightness, a generous
    angular size); the ``*_limit`` values are the rejection ends.
    """

    integrated_magnitude_limit: float = 13.5
    surface_brightness_limit: float = 23.5
    min_axis_arcmin: float = 1.5
    bright_magnitude_limit: float = 10.5
    reference_magnitude: float = 8.0
    reference_surface_brightness: float = 21.0
    reference_axis_arcmin: float = 10.0


DEFAULT_LIMITS = VisibilityLimits()


@dataclass(frozen=True, slots=True)
class VisibilityAssessment:
    """Outcome of evaluating one object against the edition limits."""

    visible: bool
    score: float
    reasons: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-serializable mapping of this assessment."""
        return {
            "visible": self.visible,
            "score": self.score,
            "reasons": list(self.reasons),
        }


class VisibilityEvaluator(Protocol):
    """Per-type visibility rule."""

    object_type: ClassVar[DsoType]

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment: ...


def _lower_is_better(value: float, *, best: float, worst: float) -> float:
    """Map a quantity where smaller is better onto 0..1."""
    if value <= best:
        return 1.0
    if value >= worst:
        return 0.0
    return (worst - value) / (worst - best)


def _higher_is_better(value: float, *, worst: float, best: float) -> float:
    """Map a quantity where larger is better onto 0..1."""
    if value <= worst:
        return 0.0
    if value >= best:
        return 1.0
    return (value - worst) / (best - worst)


def _combine(parts: list[tuple[float, float]]) -> float:
    """Return a 0-100 weighted mean of ``(score, weight)`` components."""
    total_weight = sum(weight for _, weight in parts)
    if total_weight <= 0.0:
        return 0.0
    weighted = sum(score * weight for score, weight in parts)
    return round(100.0 * weighted / total_weight, 3)


def _magnitude_score(magnitude: float | None, limits: VisibilityLimits) -> float | None:
    if magnitude is None:
        return None
    return _lower_is_better(
        magnitude,
        best=limits.reference_magnitude,
        worst=limits.integrated_magnitude_limit,
    )


def _surface_brightness_score(
    surface_brightness: float | None, limits: VisibilityLimits
) -> float | None:
    if surface_brightness is None:
        return None
    return _lower_is_better(
        surface_brightness,
        best=limits.reference_surface_brightness,
        worst=limits.surface_brightness_limit,
    )


def _size_score(size_arcmin: float | None, limits: VisibilityLimits) -> float | None:
    if size_arcmin is None:
        return None
    return _higher_is_better(
        size_arcmin,
        worst=limits.min_axis_arcmin,
        best=limits.reference_axis_arcmin,
    )


def _too_small(size_arcmin: float | None, limits: VisibilityLimits) -> bool:
    return size_arcmin is not None and size_arcmin < limits.min_axis_arcmin


class _ExcludedEvaluator:
    """Types that never contribute a deep-sky symbol by default."""

    object_type: ClassVar[DsoType]

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment:
        return VisibilityAssessment(visible=False, score=0.0, reasons=("excluded-type",))


class StarEvaluator(_ExcludedEvaluator):
    object_type = DsoType.STAR


class DoubleStarEvaluator(_ExcludedEvaluator):
    object_type = DsoType.DOUBLE_STAR


class GalaxyEvaluator:
    """Galaxies are surface-brightness limited, then magnitude, then size."""

    object_type = DsoType.GALAXY

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment:
        surface_brightness = dso.surface_brightness_mag_arcsec2()
        magnitude = dso.magnitude
        size = dso.major_axis_arcmin
        reasons: list[str] = []

        bright = magnitude is not None and magnitude <= limits.bright_magnitude_limit
        if _too_small(size, limits) and not bright:
            visible = False
            reasons.append("below-minimum-size")
        else:
            visible = (
                surface_brightness is not None
                and surface_brightness <= limits.surface_brightness_limit
            ) or (
                magnitude is not None
                and magnitude <= limits.integrated_magnitude_limit
            )
            if not visible:
                reasons.append("too-faint")

        parts: list[tuple[float, float]] = []
        sb_score = _surface_brightness_score(surface_brightness, limits)
        if sb_score is not None:
            parts.append((sb_score, 0.5))
        mag_score = _magnitude_score(magnitude, limits)
        if mag_score is not None:
            parts.append((mag_score, 0.3))
        size_score = _size_score(size, limits)
        if size_score is not None:
            parts.append((size_score, 0.2))
        if not parts:
            reasons.append("no-photometry")
        return VisibilityAssessment(
            visible=visible, score=_combine(parts), reasons=tuple(reasons)
        )


class GlobularClusterEvaluator:
    """Globulars are compact and bright; magnitude leads, size is no barrier."""

    object_type = DsoType.GLOBULAR_CLUSTER

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment:
        surface_brightness = dso.surface_brightness_mag_arcsec2()
        magnitude = dso.magnitude
        size = dso.major_axis_arcmin
        reasons: list[str] = []

        if magnitude is not None or surface_brightness is not None:
            visible = (
                magnitude is not None
                and magnitude <= limits.integrated_magnitude_limit
            ) or (
                surface_brightness is not None
                and surface_brightness <= limits.surface_brightness_limit
            )
        else:
            visible = size is not None and size >= limits.min_axis_arcmin
        if not visible:
            reasons.append("too-faint")

        parts: list[tuple[float, float]] = []
        mag_score = _magnitude_score(magnitude, limits)
        if mag_score is not None:
            parts.append((mag_score, 0.7))
        sb_score = _surface_brightness_score(surface_brightness, limits)
        if sb_score is not None:
            parts.append((sb_score, 0.3))
        if not parts:
            reasons.append("no-photometry")
        return VisibilityAssessment(
            visible=visible, score=_combine(parts), reasons=tuple(reasons)
        )


class OpenClusterEvaluator:
    """Open clusters are resolved, so angular size leads and magnitude follows."""

    object_type = DsoType.OPEN_CLUSTER

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment:
        magnitude = dso.magnitude
        size = dso.major_axis_arcmin
        reasons: list[str] = []

        bright = magnitude is not None and magnitude <= limits.bright_magnitude_limit
        if size is None and magnitude is None:
            visible = False
            reasons.append("no-photometry")
        elif _too_small(size, limits) and not bright:
            visible = False
            reasons.append("below-minimum-size")
        else:
            visible = (
                size is not None and size >= limits.min_axis_arcmin
            ) or (
                magnitude is not None
                and magnitude <= limits.integrated_magnitude_limit
            )
            if not visible:
                reasons.append("too-faint")

        parts: list[tuple[float, float]] = []
        size_score = _size_score(size, limits)
        if size_score is not None:
            parts.append((size_score, 0.6))
        mag_score = _magnitude_score(magnitude, limits)
        if mag_score is not None:
            parts.append((mag_score, 0.4))
        return VisibilityAssessment(
            visible=visible, score=_combine(parts), reasons=tuple(reasons)
        )


class PlanetaryNebulaEvaluator:
    """Planetary nebulae are high-surface-brightness points; magnitude leads."""

    object_type = DsoType.PLANETARY_NEBULA

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment:
        surface_brightness = dso.surface_brightness_mag_arcsec2()
        magnitude = dso.magnitude
        size = dso.major_axis_arcmin
        reasons: list[str] = []

        if magnitude is None and surface_brightness is None:
            visible = size is not None
        else:
            visible = (
                magnitude is not None
                and magnitude <= limits.integrated_magnitude_limit
            ) or (
                surface_brightness is not None
                and surface_brightness <= limits.surface_brightness_limit
            )
        if not visible:
            reasons.append("too-faint")

        parts: list[tuple[float, float]] = []
        mag_score = _magnitude_score(magnitude, limits)
        if mag_score is not None:
            parts.append((mag_score, 0.8))
        sb_score = _surface_brightness_score(surface_brightness, limits)
        if sb_score is not None:
            parts.append((sb_score, 0.2))
        if not parts:
            reasons.append("no-photometry")
        return VisibilityAssessment(
            visible=visible, score=_combine(parts), reasons=tuple(reasons)
        )


class BrightNebulaEvaluator:
    """Bright nebulae are extended and surface-brightness limited."""

    object_type = DsoType.BRIGHT_NEBULA

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment:
        surface_brightness = dso.surface_brightness_mag_arcsec2()
        magnitude = dso.magnitude
        size = dso.major_axis_arcmin
        reasons: list[str] = []

        bright = magnitude is not None and magnitude <= limits.bright_magnitude_limit
        if _too_small(size, limits) and not bright:
            visible = False
            reasons.append("below-minimum-size")
        else:
            visible = (
                surface_brightness is not None
                and surface_brightness <= limits.surface_brightness_limit
            ) or (
                magnitude is not None
                and magnitude <= limits.integrated_magnitude_limit
            )
            if not visible:
                reasons.append("too-faint")

        parts: list[tuple[float, float]] = []
        sb_score = _surface_brightness_score(surface_brightness, limits)
        if sb_score is not None:
            parts.append((sb_score, 0.5))
        size_score = _size_score(size, limits)
        if size_score is not None:
            parts.append((size_score, 0.3))
        mag_score = _magnitude_score(magnitude, limits)
        if mag_score is not None:
            parts.append((mag_score, 0.2))
        if not parts:
            reasons.append("no-photometry")
        return VisibilityAssessment(
            visible=visible, score=_combine(parts), reasons=tuple(reasons)
        )


class DarkNebulaEvaluator:
    """Dark nebulae have no magnitude; size and contrast potential decide."""

    object_type = DsoType.DARK_NEBULA

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment:
        size = dso.major_axis_arcmin
        reasons: list[str] = []
        if size is None:
            visible = False
            reasons.append("no-photometry")
        else:
            visible = size >= limits.min_axis_arcmin
            if not visible:
                reasons.append("below-minimum-size")
        size_score = _size_score(size, limits)
        parts = [(size_score, 1.0)] if size_score is not None else []
        return VisibilityAssessment(
            visible=visible, score=_combine(parts), reasons=tuple(reasons)
        )


class GalaxyClusterEvaluator:
    """Galaxy clusters often lack photometry; size is a valid fallback."""

    object_type = DsoType.GALAXY_CLUSTER

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment:
        surface_brightness = dso.surface_brightness_mag_arcsec2()
        magnitude = dso.magnitude
        size = dso.major_axis_arcmin
        reasons: list[str] = []

        visible = (
            surface_brightness is not None
            and surface_brightness <= limits.surface_brightness_limit
        ) or (
            magnitude is not None and magnitude <= limits.integrated_magnitude_limit
        )
        if (
            not visible
            and magnitude is None
            and surface_brightness is None
            and size is not None
            and size >= limits.min_axis_arcmin
        ):
            visible = True
        if _too_small(size, limits) and not visible:
            reasons.append("below-minimum-size")
        elif not visible:
            reasons.append("too-faint")

        parts: list[tuple[float, float]] = []
        size_score = _size_score(size, limits)
        if size_score is not None:
            parts.append((size_score, 0.5))
        mag_score = _magnitude_score(magnitude, limits)
        if mag_score is not None:
            parts.append((mag_score, 0.3))
        sb_score = _surface_brightness_score(surface_brightness, limits)
        if sb_score is not None:
            parts.append((sb_score, 0.2))
        if not parts:
            reasons.append("no-photometry")
        return VisibilityAssessment(
            visible=visible, score=_combine(parts), reasons=tuple(reasons)
        )


class OtherEvaluator:
    """Fallback for unclassified entries: magnitude, then surface brightness."""

    object_type = DsoType.OTHER

    def evaluate(
        self, dso: DeepSkyObject, limits: VisibilityLimits
    ) -> VisibilityAssessment:
        surface_brightness = dso.surface_brightness_mag_arcsec2()
        magnitude = dso.magnitude
        reasons: list[str] = []
        visible = (
            magnitude is not None and magnitude <= limits.integrated_magnitude_limit
        ) or (
            surface_brightness is not None
            and surface_brightness <= limits.surface_brightness_limit
        )
        if not visible:
            reasons.append("too-faint")

        parts: list[tuple[float, float]] = []
        mag_score = _magnitude_score(magnitude, limits)
        if mag_score is not None:
            parts.append((mag_score, 0.6))
        sb_score = _surface_brightness_score(surface_brightness, limits)
        if sb_score is not None:
            parts.append((sb_score, 0.4))
        if not parts:
            reasons.append("no-photometry")
        return VisibilityAssessment(
            visible=visible, score=_combine(parts), reasons=tuple(reasons)
        )


_EVALUATORS: dict[DsoType, VisibilityEvaluator] = {
    DsoType.GALAXY: GalaxyEvaluator(),
    DsoType.OPEN_CLUSTER: OpenClusterEvaluator(),
    DsoType.GLOBULAR_CLUSTER: GlobularClusterEvaluator(),
    DsoType.PLANETARY_NEBULA: PlanetaryNebulaEvaluator(),
    DsoType.BRIGHT_NEBULA: BrightNebulaEvaluator(),
    DsoType.DARK_NEBULA: DarkNebulaEvaluator(),
    DsoType.GALAXY_CLUSTER: GalaxyClusterEvaluator(),
    DsoType.STAR: StarEvaluator(),
    DsoType.DOUBLE_STAR: DoubleStarEvaluator(),
    DsoType.OTHER: OtherEvaluator(),
}

_FALLBACK_EVALUATOR: VisibilityEvaluator = OtherEvaluator()


def evaluator_for(object_type: DsoType) -> VisibilityEvaluator:
    """Return the evaluator registered for ``object_type``."""
    return _EVALUATORS.get(object_type, _FALLBACK_EVALUATOR)


def evaluate_visibility(
    dso: DeepSkyObject, limits: VisibilityLimits = DEFAULT_LIMITS
) -> VisibilityAssessment:
    """Evaluate one deep-sky object against ``limits``."""
    return evaluator_for(dso.object_type).evaluate(dso, limits)
