"""Reproducible galaxy visibility classification after Crumey (2014).

This module estimates whether the *integrated light* of a galaxy is detectable
by a visual observer through 100, 200 and 400 mm apertures.  It is an atlas
presentation aid, not a telescope simulator: the result only selects how heavy a
galaxy contour is drawn (``bold``/``normal``/``fine``/``dotted``), never whether
an object exists or how it is labelled.

Scientific scope and NightSkyAtlas heuristics
---------------------------------------------

Andrew Crumey, "Human Contrast Threshold and Astronomical Visibility", MNRAS
442, 2600-2619 (2014), supplies the contrast threshold for a *uniform extended
object* against an adapted sky background.  The following parts are
NightSkyAtlas heuristics layered on top of that threshold and must not be read
as Crumey's model:

- the Hubble-type -> Sersic-index mapping;
- the B-V colour fallbacks;
- the reconstruction of inner sub-apertures from a single mean surface
  brightness;
- the assumed reference observing conditions;
- the score boundary ``-0.25``;
- the contour classification itself;
- the confidence assessment.

The result means "some integrated galaxy light is approximately detectable
under the reference conditions".  It says nothing reliable about spiral arms,
dust lanes, H II regions or the full D25 diameter.

All mathematics here is renderer independent and deterministic; the dense
41-fraction / 121-exit-pupil rasterisation exists for reproducibility.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from functools import cache

import numpy as np
from scipy.optimize import brentq
from scipy.special import gamma, gammainc

from nightsky_atlas.catalog.models import DeepSkyObject

__all__ = [
    "APERTURES_MM",
    "DEFAULT_CONDITIONS",
    "DEFAULT_SKY_MAG_ARCSEC2",
    "GalaxyContourClass",
    "GalaxyVisibility",
    "ApertureVisibility",
    "MorphologyPrior",
    "VisibilityConditions",
    "classify_galaxy_contour",
    "crumey_required_contrast",
    "effective_visual_surface_brightness",
    "ellipse_area_sr",
    "estimate_galaxy_visibility",
    "mean_mu_b_within_fraction",
    "morphology_priors",
    "score_galaxy_at_aperture",
    "sky_luminance_cd_m2",
    "solve_x25",
    "visibility_score",
]

# Crumey contrast-threshold coefficients (Crumey 2014, table/eq. constants).
R1 = 6.505e-4
R2 = -8.461e-4
K1 = 7.633e-3
K2 = -7.174e-3
Q = 0.6

ZERO_BACKGROUND_CD_M2 = 1.0e-5
DEFAULT_SKY_MAG_ARCSEC2 = 21.5
DEFAULT_TRANSMISSION = 0.75
DEFAULT_EYE_PUPIL_MM = 7.0
DEFAULT_FIELD_FACTOR = 2.0 * math.sqrt(2.0)
DEFAULT_AFOV_DEG = 68.0

APERTURES_MM = (100.0, 200.0, 400.0)
MAX_MAGNIFICATION = 300.0
MIN_EXIT_PUPIL_MM = 1.0
MAX_EXIT_PUPIL_MM = 7.0

PROFILE_FRACTION_COUNT = 41
EXIT_PUPIL_COUNT = 121
VISIBILITY_THRESHOLD = -0.25


class GalaxyContourClass(StrEnum):
    """How heavy a galaxy contour should be printed."""

    BOLD = "bold"
    NORMAL = "normal"
    FINE = "fine"
    DOTTED = "dotted"
    UNCLASSIFIED = "unclassified"


@dataclass(frozen=True, slots=True)
class VisibilityConditions:
    """Reference observing conditions for the contrast model.

    These are deliberate, documented assumptions (NightSkyAtlas heuristic), not
    a measurement of any particular site or instrument.
    """

    sky_mag_arcsec2: float = DEFAULT_SKY_MAG_ARCSEC2
    transmission: float = DEFAULT_TRANSMISSION
    eye_pupil_mm: float = DEFAULT_EYE_PUPIL_MM
    field_factor: float = DEFAULT_FIELD_FACTOR
    afov_deg: float = DEFAULT_AFOV_DEG
    max_magnification: float = MAX_MAGNIFICATION


DEFAULT_CONDITIONS = VisibilityConditions()


@dataclass(frozen=True, slots=True)
class MorphologyPrior:
    """Sersic index and B-V prior inferred from an OpenNGC Hubble string."""

    n: float
    b_minus_v: float
    uncertain: bool = False
    missing: bool = False


@dataclass(frozen=True, slots=True)
class ApertureVisibility:
    """Best visibility score found for one aperture.

    ``best_fraction`` is the inner fraction of the D25 ellipse, ``best_exit_pupil_mm``
    the eyepiece exit pupil and ``best_magnification`` the resulting power.  The
    contrast fields are the values at that optimum.  ``exit_pupil_band_mm`` is a
    diagnostic range of exit pupils within 0.05 mag of the optimum.
    """

    aperture_mm: float
    score: float
    best_fraction: float
    best_exit_pupil_mm: float
    best_magnification: float
    effective_surface_brightness: float
    object_contrast: float
    required_contrast: float
    exit_pupil_band_mm: tuple[float, float] | None = None


@dataclass(frozen=True, slots=True)
class GalaxyVisibility:
    """Full classification result for one galaxy."""

    contour_class: GalaxyContourClass
    by_aperture: Mapping[int, ApertureVisibility]
    confidence: str
    confidence_reasons: tuple[str, ...]
    surface_brightness_source: str


# ---------------------------------------------------------------------------
# Morphology prior
# ---------------------------------------------------------------------------

_UNKNOWN_PRIOR = MorphologyPrior(n=1.5, b_minus_v=0.70, uncertain=True, missing=True)

# Keys are lower-cased *after* the SB/SAB bar prefix has been removed, so
# ``SBbc`` and ``SABbc`` collapse onto ``Sbc`` (the bar form follows its base
# class).  The subtype letters must keep their case: ``Sbc`` and ``SBc`` are
# different classes and uppercase would merge them.
_MORPHOLOGY_PRIORS: dict[str, MorphologyPrior] = {
    "e": MorphologyPrior(4.0, 0.90),
    "e-s0": MorphologyPrior(4.0, 0.90),
    "s0": MorphologyPrior(3.0, 0.85),
    "s0-a": MorphologyPrior(3.0, 0.85),
    "s0a": MorphologyPrior(3.0, 0.85),
    "s0/a": MorphologyPrior(3.0, 0.85),
    "sa": MorphologyPrior(2.5, 0.80),
    "sab": MorphologyPrior(2.5, 0.80),
    "sb": MorphologyPrior(2.0, 0.75),
    "sbc": MorphologyPrior(1.5, 0.65),
    "sc": MorphologyPrior(1.2, 0.55),
    "scd": MorphologyPrior(1.0, 0.45),
    "sd": MorphologyPrior(1.0, 0.45),
    "sdm": MorphologyPrior(1.0, 0.45),
    "sm": MorphologyPrior(1.0, 0.45),
    "irr": MorphologyPrior(1.0, 0.45),
    "i": MorphologyPrior(1.0, 0.45),
    "ib": MorphologyPrior(1.0, 0.45),
    "iab": MorphologyPrior(1.0, 0.45),
    "im": MorphologyPrior(1.0, 0.45),
}


def _strip_bar_prefix(hubble: str) -> str:
    """Remove a leading ``SAB``/``SB`` bar prefix, keeping the base class."""
    if hubble.startswith("SAB"):
        return "S" + hubble[3:]
    if hubble.startswith("SB"):
        return "S" + hubble[2:]
    return hubble


def _strip_parentheticals(hubble: str) -> str:
    """Drop parenthesised qualifiers such as ``SAB(rs)bc`` -> ``SABbc``."""
    out: list[str] = []
    depth = 0
    for character in hubble:
        if character == "(":
            depth += 1
        elif character == ")":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(character)
    return "".join(out)


def morphology_priors(hubble: str | None) -> MorphologyPrior:
    """Return the Sersic index and B-V prior for an OpenNGC Hubble string.

    A missing or unrecognised type falls back to ``n=1.5``, ``B-V=0.70`` and is
    flagged as uncertain.  An uncertain type containing ``?`` is classified by
    its recognisable base type and flagged as uncertain.
    """
    if hubble is None or not hubble.strip():
        return _UNKNOWN_PRIOR
    cleaned = _strip_parentheticals(hubble.strip().replace(" ", ""))
    uncertain = "?" in cleaned
    cleaned = cleaned.replace("?", "")
    base = _strip_bar_prefix(cleaned).lower()
    prior = _MORPHOLOGY_PRIORS.get(base)
    if prior is None:
        return _UNKNOWN_PRIOR
    if uncertain:
        return MorphologyPrior(prior.n, prior.b_minus_v, uncertain=True)
    return prior


# ---------------------------------------------------------------------------
# Photometry helpers
# ---------------------------------------------------------------------------


def effective_visual_surface_brightness(mu_b: float, b_minus_v: float) -> float:
    """Convert a mean B surface brightness to an effective visual value.

    ``mu_B - (B-V) + 0.27 * ((B-V) - 0.7)`` is the NightSkyAtlas heuristic that
    maps a B-band surface brightness onto the visual band for this model.
    """
    return mu_b - b_minus_v + 0.27 * (b_minus_v - 0.7)


def ellipse_area_sr(major_arcmin: float, minor_arcmin: float, fraction: float = 1.0) -> float:
    """Solid angle of a (sub-)ellipse in steradians.

    ``major_arcmin``/``minor_arcmin`` are the *full* D25 axes in arcminutes;
    ``fraction`` scales both axes, so the area scales with ``fraction**2``.
    """
    area_arcmin2 = math.pi / 4.0 * major_arcmin * minor_arcmin * fraction**2
    return area_arcmin2 * (math.pi / (180.0 * 60.0)) ** 2


def sky_luminance_cd_m2(sky_mag_arcsec2: float) -> float:
    """Sky luminance in cd/m^2 for a sky brightness in mag/arcsec^2."""
    return 10.0 ** ((12.58 - sky_mag_arcsec2) / 2.5)


def _surface_brightness_from_magnitude(
    magnitude: float, major_arcmin: float, minor_arcmin: float
) -> float:
    """Mean surface brightness from an integrated magnitude and full axes."""
    area_arcsec2 = 3600.0 * math.pi / 4.0 * major_arcmin * minor_arcmin
    return magnitude + 2.5 * math.log10(area_arcsec2)


# ---------------------------------------------------------------------------
# Sersic profile reconstruction
# ---------------------------------------------------------------------------


def solve_x25(n: float, mean_mu_b_25: float) -> float | None:
    """Solve the Sersic scale radius ``x25`` for a D25 mean surface brightness.

    Returns ``None`` when ``mean_mu_b_25 >= 25`` (the equation has no solution)
    or when the numerical solver fails; callers then fall back to a uniform
    ellipse.  Uses SciPy's incomplete gamma function.
    """
    target = 10.0 ** (0.4 * (25.0 - mean_mu_b_25))
    if target <= 1.0:
        return None

    def residual(x: float) -> float:
        lower_gamma = gammainc(2.0 * n, x) * gamma(2.0 * n)
        ratio = 2.0 * n * math.exp(x) * lower_gamma / x ** (2.0 * n)
        return ratio - target

    try:
        return float(brentq(residual, 1.0e-4, 100.0))
    except (ValueError, RuntimeError):
        return None


def mean_mu_b_within_fraction(
    mean_mu_b_25: float,
    n: float,
    x25: float,
    fraction: float,
) -> float:
    """Mean B surface brightness inside ``fraction`` of the D25 ellipse."""
    numerator = gammainc(2.0 * n, x25 * fraction ** (1.0 / n))
    denominator = gammainc(2.0 * n, x25)
    flux_per_area_ratio = (numerator / denominator) / fraction**2
    return mean_mu_b_25 - 2.5 * math.log10(flux_per_area_ratio)


def _mean_mu_b_array(
    mean_mu_b_25: float, n: float, x25: float, fractions: np.ndarray
) -> np.ndarray:
    """Vectorised :func:`mean_mu_b_within_fraction` over fractions."""
    numerator = gammainc(2.0 * n, x25 * fractions ** (1.0 / n))
    denominator = gammainc(2.0 * n, x25)
    return mean_mu_b_25 - 2.5 * np.log10((numerator / denominator) / fractions**2)


# ---------------------------------------------------------------------------
# Crumey contrast threshold
# ---------------------------------------------------------------------------


def _background_terms(exit_pupil_mm: np.ndarray | float, conditions: VisibilityConditions):
    """Return ``(R(B), C_infinity(B))`` for one or more exit pupils."""
    sky = sky_luminance_cd_m2(conditions.sky_mag_arcsec2)
    apparent_sky = (
        sky
        * conditions.transmission
        * (np.minimum(exit_pupil_mm, conditions.eye_pupil_mm) / conditions.eye_pupil_mm) ** 2
    )
    background = np.maximum(apparent_sky, ZERO_BACKGROUND_CD_M2)
    r = (R1 * background ** (-0.25) + R2) ** 2
    c_infinity = K1 * background ** (-0.25) + K2
    return r, c_infinity


def crumey_required_contrast(
    area_sr: float,
    aperture_mm: float,
    exit_pupil_mm: float,
    conditions: VisibilityConditions = DEFAULT_CONDITIONS,
) -> float:
    """Crumey required contrast for an object of solid angle ``area_sr``."""
    magnification = aperture_mm / exit_pupil_mm
    r, c_infinity = _background_terms(exit_pupil_mm, conditions)
    apparent_area = magnification**2 * area_sr
    raw_threshold = ((r / apparent_area) ** Q + c_infinity**Q) ** (1.0 / Q)
    return conditions.field_factor * float(raw_threshold)


def _required_contrast_grid(
    areas_sr: np.ndarray,
    aperture_mm: float,
    exit_pupils_mm: np.ndarray,
    conditions: VisibilityConditions,
) -> np.ndarray:
    """Vectorised required contrast over ``(exit_pupil, fraction)``."""
    magnification = aperture_mm / exit_pupils_mm
    r, c_infinity = _background_terms(exit_pupils_mm, conditions)
    apparent_area = (magnification**2)[:, None] * areas_sr[None, :]
    raw_threshold = ((r[:, None] / apparent_area) ** Q + c_infinity[:, None] ** Q) ** (1.0 / Q)
    return conditions.field_factor * raw_threshold


def visibility_score(object_contrast: float, required_contrast: float) -> float:
    """Visibility score in magnitudes: ``2.5 log10(C_obj / C_req)``.

    ``S = 0`` is the conservative detection threshold assumed here; ``S >=
    -0.25`` is still treated as reachable for the coarse atlas classification.
    """
    return 2.5 * math.log10(object_contrast / required_contrast)


# ---------------------------------------------------------------------------
# Profile resolution and scoring
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _GalaxyProfile:
    major_arcmin: float
    minor_arcmin: float
    mean_mu_b_25: float
    n: float
    b_minus_v: float
    x25: float | None
    solver_fallback: bool
    morphology: MorphologyPrior
    surface_brightness_source: str
    colour_derived: bool
    minor_axis_missing: bool
    surface_brightness_derived: bool
    brightness_inconsistent: bool


def _resolve_profile(dso: DeepSkyObject) -> _GalaxyProfile | None:
    """Resolve photometry, colour and profile parameters for one galaxy.

    Returns ``None`` when no usable photometry or no major axis is available;
    the caller then classifies the object as ``unclassified``.
    """
    major = dso.major_axis_arcmin
    if major is None or major <= 0.0:
        return None
    minor = dso.minor_axis_arcmin
    minor_axis_missing = minor is None or minor <= 0.0
    if minor_axis_missing:
        minor = major

    morphology = morphology_priors(dso.hubble_type)
    b_minus_v = morphology.b_minus_v
    colour_derived = True
    if dso.b_magnitude is not None and dso.v_magnitude is not None:
        candidate = dso.b_magnitude - dso.v_magnitude
        if 0.0 <= candidate <= 1.5 and abs(candidate - morphology.b_minus_v) <= 0.25:
            b_minus_v = candidate
            colour_derived = False

    surface_brightness_derived = False
    brightness_inconsistent = False
    mu_b_25 = dso.mean_surface_brightness_mag_arcsec2
    if mu_b_25 is not None:
        source = "openngc_surfbr"
        if dso.b_magnitude is not None:
            derived = _surface_brightness_from_magnitude(dso.b_magnitude, major, minor)
            brightness_inconsistent = abs(mu_b_25 - derived) > 0.75
    elif dso.b_magnitude is not None:
        mu_b_25 = _surface_brightness_from_magnitude(dso.b_magnitude, major, minor)
        source = "derived_from_b_mag"
        surface_brightness_derived = True
    elif dso.v_magnitude is not None:
        mu_b_25 = _surface_brightness_from_magnitude(
            dso.v_magnitude + b_minus_v, major, minor
        )
        source = "derived_from_v_mag_and_colour_prior"
        surface_brightness_derived = True
    else:
        return None

    x25 = solve_x25(morphology.n, mu_b_25)
    return _GalaxyProfile(
        major_arcmin=major,
        minor_arcmin=minor,
        mean_mu_b_25=mu_b_25,
        n=morphology.n,
        b_minus_v=b_minus_v,
        x25=x25,
        solver_fallback=x25 is None,
        morphology=morphology,
        surface_brightness_source=source,
        colour_derived=colour_derived,
        minor_axis_missing=minor_axis_missing,
        surface_brightness_derived=surface_brightness_derived,
        brightness_inconsistent=brightness_inconsistent,
    )


def _score_profile(
    profile: _GalaxyProfile, aperture_mm: float, conditions: VisibilityConditions
) -> ApertureVisibility:
    """Vectorised magnification/profile optimisation for one aperture."""
    if profile.x25 is None:
        fractions = np.array([1.0])
        mu_b = np.array([profile.mean_mu_b_25])
    else:
        fractions = np.geomspace(0.10, 1.0, PROFILE_FRACTION_COUNT)
        mu_b = _mean_mu_b_array(
            profile.mean_mu_b_25, profile.n, profile.x25, fractions
        )

    mu_eff = effective_visual_surface_brightness(mu_b, profile.b_minus_v)
    object_contrast = 10.0 ** (-0.4 * (mu_eff - conditions.sky_mag_arcsec2))
    areas = np.pi / 4.0 * profile.major_arcmin * profile.minor_arcmin * fractions**2
    areas = areas * (np.pi / (180.0 * 60.0)) ** 2

    d_min = max(MIN_EXIT_PUPIL_MM, aperture_mm / conditions.max_magnification)
    d_max = min(MAX_EXIT_PUPIL_MM, conditions.eye_pupil_mm)
    exit_pupils = np.geomspace(d_min, d_max, EXIT_PUPIL_COUNT)
    magnification = aperture_mm / exit_pupils

    apparent_axis_deg = (
        magnification[:, None] * profile.major_arcmin * fractions[None, :] / 60.0
    )
    valid = apparent_axis_deg <= 0.8 * conditions.afov_deg

    required = _required_contrast_grid(areas, aperture_mm, exit_pupils, conditions)
    ratio = object_contrast[None, :] / required
    scores = 2.5 * np.log10(ratio)
    scores = np.where(valid, scores, -np.inf)

    best_flat = int(np.argmax(scores))
    pupil_index, fraction_index = np.unravel_index(best_flat, scores.shape)
    best_score = float(scores[pupil_index, fraction_index])
    best_fraction = float(fractions[fraction_index])
    best_exit_pupil = float(exit_pupils[pupil_index])

    band = _exit_pupil_band(scores[:, fraction_index], exit_pupils, best_score)

    return ApertureVisibility(
        aperture_mm=aperture_mm,
        score=best_score,
        best_fraction=best_fraction,
        best_exit_pupil_mm=best_exit_pupil,
        best_magnification=float(aperture_mm / best_exit_pupil),
        effective_surface_brightness=float(mu_eff[fraction_index]),
        object_contrast=float(object_contrast[fraction_index]),
        required_contrast=float(required[pupil_index, fraction_index]),
        exit_pupil_band_mm=band,
    )


def _exit_pupil_band(
    column: np.ndarray, exit_pupils: np.ndarray, best_score: float
) -> tuple[float, float] | None:
    """Diagnostic exit-pupil range within 0.05 mag of the optimum."""
    usable = np.isfinite(column) & (column >= best_score - 0.05)
    if not np.any(usable):
        return None
    selected = exit_pupils[usable]
    return (float(np.min(selected)), float(np.max(selected)))


def score_galaxy_at_aperture(
    galaxy: DeepSkyObject,
    aperture_mm: float,
    conditions: VisibilityConditions = DEFAULT_CONDITIONS,
) -> ApertureVisibility | None:
    """Return the best visibility score for ``galaxy`` at ``aperture_mm``.

    ``None`` means the object cannot be scored (missing major axis or usable
    photometry).
    """
    profile = _resolve_profile(galaxy)
    if profile is None:
        return None
    return _score_profile(profile, aperture_mm, conditions)


def classify_galaxy_contour(scores: Mapping[int, float]) -> GalaxyContourClass:
    """Map per-aperture scores onto the contour class.

    The ``-0.25`` boundary is a NightSkyAtlas heuristic, not a Crumey result.
    """
    s100 = scores.get(100)
    s200 = scores.get(200)
    s400 = scores.get(400)
    if s100 is None or s200 is None or s400 is None:
        return GalaxyContourClass.UNCLASSIFIED
    if s100 >= VISIBILITY_THRESHOLD:
        return GalaxyContourClass.BOLD
    if s200 >= VISIBILITY_THRESHOLD:
        return GalaxyContourClass.NORMAL
    if s400 >= VISIBILITY_THRESHOLD:
        return GalaxyContourClass.FINE
    return GalaxyContourClass.DOTTED


def _confidence(
    profile: _GalaxyProfile, by_aperture: Mapping[int, ApertureVisibility]
) -> tuple[str, tuple[str, ...]]:
    """Confidence in the classification; never changes score or contour."""
    points = 3
    reasons: list[str] = []
    if profile.colour_derived:
        points -= 1
        reasons.append("colour_from_morphology")
    if profile.morphology.missing:
        points -= 1
        reasons.append("morphology_missing")
    elif profile.morphology.uncertain:
        points -= 1
        reasons.append("morphology_uncertain")
    if profile.surface_brightness_derived:
        points -= 1
        reasons.append("surface_brightness_derived")
    if profile.brightness_inconsistent:
        points -= 1
        reasons.append("surface_brightness_inconsistent")
    if profile.mean_mu_b_25 >= 24.9 or profile.solver_fallback:
        points -= 1
        reasons.append("faint_or_profile_fallback")
    if profile.minor_axis_missing:
        points -= 1
        reasons.append("missing_minor_axis")
    best = max(by_aperture.values(), key=lambda entry: entry.score)
    if best.best_fraction < 0.20:
        points -= 1
        reasons.append("small_best_fraction")
    points = max(points, 0)
    label = "high" if points >= 3 else "medium" if points == 2 else "low"
    return label, tuple(reasons)


@cache
def estimate_galaxy_visibility(
    galaxy: DeepSkyObject,
    conditions: VisibilityConditions = DEFAULT_CONDITIONS,
) -> GalaxyVisibility:
    """Classify one galaxy, caching by galaxy and reference conditions.

    The result is computed once per galaxy and reused across every chart it
    appears on.
    """
    profile = _resolve_profile(galaxy)
    if profile is None:
        reason = (
            "missing_major_axis"
            if galaxy.major_axis_arcmin is None
            else "missing_photometry"
        )
        return GalaxyVisibility(
            contour_class=GalaxyContourClass.UNCLASSIFIED,
            by_aperture={},
            confidence="low",
            confidence_reasons=(reason,),
            surface_brightness_source="unavailable",
        )

    by_aperture = {
        int(aperture): _score_profile(profile, aperture, conditions)
        for aperture in APERTURES_MM
    }
    scores = {aperture: entry.score for aperture, entry in by_aperture.items()}
    confidence, reasons = _confidence(profile, by_aperture)
    return GalaxyVisibility(
        contour_class=classify_galaxy_contour(scores),
        by_aperture=by_aperture,
        confidence=confidence,
        confidence_reasons=reasons,
        surface_brightness_source=profile.surface_brightness_source,
    )
