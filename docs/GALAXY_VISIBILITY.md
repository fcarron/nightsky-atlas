# Galaxy visibility classification

NightSky Atlas estimates the visual detectability of galaxies with an
approximate contrast-threshold model after Andrew Crumey.  For 100, 200 and
400 mm apertures it explores different magnifications and inner galaxy
apertures.  The resulting contour weight shows at which aperture the *integrated
galaxy light* becomes approximately detectable under the assumed reference
conditions.

The classification is **not a guarantee** that an object is visible in a given
telescope.  Transparency, local sky brightness, altitude, dark adaptation,
observer experience, bright field stars and a galaxy's real brightness structure
can change the outcome substantially.  The classification describes the
detection of *some* galaxy light, not the visibility of spiral arms, dust lanes
or the full catalogue diameter.

## Scientific scope

Crumey, "Human Contrast Threshold and Astronomical Visibility", MNRAS 442,
2600-2619 (2014), supplies the contrast threshold for a **uniform extended
object** against an adapted sky background.  The following parts are
NightSkyAtlas heuristics layered on top of that threshold and are labelled as
such in `catalog/galaxy_visibility.py`:

- the Hubble-type to Sersic-index mapping;
- the B-V colour fallbacks;
- the reconstruction of inner sub-apertures from a single mean surface
  brightness;
- the assumed reference observing conditions;
- the score boundary `-0.25`;
- the contour classification;
- the confidence assessment.

Only OpenNGC entries with `Type == "G"` are scored.  `GPair`, `GTrpl`, `GGroup`
and `GCl` are galaxy *groups*, not single galaxies, and are not evaluated as
one.  No object name is special-cased.

## Method

Inputs are the OpenNGC fields `Type`, `Name`, `M`, `MajAx`, `MinAx`, `SurfBr`,
`B-Mag`, `V-Mag`, `Hubble`, `PosAng` and `Sources`.

1. **Surface brightness.**  Use `SurfBr` (`openngc_surfbr`); otherwise derive
   `mu_B = m_B + 2.5 log10(3600 * pi/4 * a * b)` from `B-Mag` and both full D25
   axes (`derived_from_b_mag`); otherwise estimate `m_B = m_V + (B-V)prior`
   from `V-Mag` and derive (`derived_from_v_mag_and_colour_prior`).  A missing
   `MajAx` or unusable photometry gives `unclassified`.  A missing `MinAx` is
   replaced by `MajAx` at reduced confidence.
2. **Colour.**  A measured `B-V` is accepted only when `0 <= B-V <= 1.5` and
   within `0.25` mag of the morphology prior; otherwise the prior is used.
   `mu_eff = mu_B - (B-V) + 0.27 ((B-V) - 0.7)`.
3. **Profile.**  The D25 mean surface brightness is treated as a Sersic mean.
   For `mu_B,25 < 25`, `x25` is solved with SciPy's incomplete gamma function
   and 41 inner fractions from 0.10 to 1.0 are rasterised; otherwise the full
   uniform ellipse is used.
4. **Contrast.**  The Crumey threshold gives the required contrast; the object
   contrast is `10^(-0.4 (mu_eff - mu_sky))` and the score is
   `S = 2.5 log10(C_obj / C_req)`.  For each aperture the best of
   `41 x 121` fraction/exit-pupil combinations is kept, rejecting combinations
   whose apparent major axis exceeds `0.8 * AFOV`.
5. **Classification.**  `S100 >= -0.25` is `bold`, else `S200 >= -0.25` is
   `normal`, else `S400 >= -0.25` is `fine`, else `dotted`.  The contour class
   affects only the galaxy contour/symbol; the label hierarchy (Messier bold
   and 1.15x, Herschel 400 bold, ordinary regular) is independent.
6. **Confidence.**  A diagnostic score (high/medium/low) from colour fallback,
   uncertain/missing morphology, derived surface brightness, inconsistent
   `SurfBr` vs `B-Mag`, very small best fraction, faint profile/solver fallback
   and a missing minor axis.  Confidence never changes the score or contour.

Reference constants: `R1 = 6.505e-4`, `R2 = -8.461e-4`, `K1 = 7.633e-3`,
`K2 = -7.174e-3`, `Q = 0.6`, `ZERO_BACKGROUND_CD_M2 = 1e-5`,
sky `21.5 mag/arcsec^2`, transmission `0.75`, eye pupil `7 mm`,
field factor `2 sqrt(2)`, AFOV `68 deg`, apertures `(100, 200, 400) mm`,
maximum magnification `300x`, exit pupils `1-7 mm`.

The classification is computed once per galaxy when the catalogue is prepared
and cached by galaxy and reference conditions, so it is not recomputed for each
chart.

## Rendering

The contour class selects a style block (`styles/*.yaml`, `dso.galaxy_contours`):

| Class | Stroke |
| --- | --- |
| `bold` | solid, 0.176 mm |
| `normal` | solid, 0.106 mm |
| `fine` | solid, 0.071 mm |
| `dotted` | 0.088 mm, short dash (0.4 / 0.35 mm) |
| `unclassified` | neutral `dso.line_width_mm` fallback |

`dotted` uses a short dash rather than isolated dots so that very small galaxy
symbols stay visible in the PDF.  Messier/Herschel 400 *label* weight is never
overridden by the contour class.

## Version note

The repository's OpenNGC snapshot is newer than the commit used when this model
was first specified (`da90466031b0372c896588b85be6016c617e205b`).  The reference
objects (NGC 6207, IC 4617, NGC 7331, NGC 7317, NGC 7319, NGC 7320, NGC 7320C)
match their expected scores within `0.03` mag, but the whole-catalogue counts
differ slightly because more galaxies are present:

| Class | Local snapshot | Reference commit |
| --- | ---: | ---: |
| total `G` | 10522 | 10482 |
| `bold` | 1308 | 1305 |
| `normal` | 2864 | ~2856-2857 |
| `fine` | 2116 | 2111 |
| `dotted` | 4174 | ~4149-4150 |
| `unclassified` | 60 | 60 |

## Limitations

- Overlapping galaxies (for example NGC 7318A/B) are scored from their own
  catalogue rows only; the model does not separate blended light.  This is a
  documented limitation of this first version.
- The result describes detection of integrated light, not structure.
- The reference conditions are assumptions, not a site measurement.

## Sources

- Andrew Crumey, "Human Contrast Threshold and Astronomical Visibility",
  MNRAS 442, 2600-2619 (2014): https://doi.org/10.1093/mnras/stu992
- Open manuscript: https://arxiv.org/abs/1405.4209
- OpenNGC: https://github.com/mattiaverga/OpenNGC

No interstellarum classes or proprietary catalogue data are used.
