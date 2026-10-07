# Tycho-2 magnitude and paper-density calibration

This is a measurement of the production normalized star store, not a theoretical
star-count model. Regenerate the underlying tables with:

```bash
nightsky data tycho-density-report --json build/tycho-density.json --csv build/tycho-density.csv
```

The report filters `catalogue='TYC2'` from `data/processed/stars/tycho2.sqlite`.
That is 2,539,913 Tycho-2 rows, separate from the 1,319 Hipparcos bright-star
supplements also present in the production store. The queried `magnitude` field
is normalized Johnson V, `V = VT - 0.090 * (BT - VT)`, exactly the field used
by star rendering. Counts are cumulative and include the limiting magnitude.

## All-sky cumulative counts and observed growth

| V limit | Cumulative stars | Added in interval | Growth factor | Effective alpha |
|---:|---:|---:|---:|---:|
| 7.0 | 15,340 | 15,340 (≤7.0) | — | — |
| 7.5 | 26,432 | 11,092 | 1.7231 | 0.4726 |
| 8.0 | 45,470 | 19,038 | 1.7203 | 0.4712 |
| 8.5 | 77,440 | 31,970 | 1.7031 | 0.4625 |
| 9.0 | 130,344 | 52,904 | 1.6832 | 0.4523 |
| 9.5 | 217,145 | 86,801 | 1.6659 | 0.4433 |
| 10.0 | 355,358 | 138,213 | 1.6365 | 0.4278 |
| 10.5 | 582,301 | 226,943 | 1.6386 | 0.4290 |
| 11.0 | 936,894 | 354,593 | 1.6090 | 0.4131 |
| 11.5 | 1,486,529 | 549,635 | 1.5867 | 0.4010 |

The 0.5-mag effective alphas are not constant. Interval means are 0.4620 for
7.5–9.0, 0.4334 for 9.0–10.5 and 0.4070 for 10.5–11.5; over 7.5–11.5 the
effective alpha is 0.4375.

## Regional fields

Windows are 27° in RA by 18.5° in declination, centered on the project benchmark
fields: sparse control / `test-sparse` at (192°, +27°), Virgo / `test-virgo` at
(187.5°, +12°), and Cygnus / `test-cygnus` at (307°, +41°). Sagittarius is
centered at (280.7°, −24.7°); the southern Milky Way control is (100°, −60°).
The areas below use the exact spherical area of each RA/Dec rectangle, so
counts are normalized by each window's true sky area.

| Field | Area deg² | ≤7.5 | ≤8.0 | ≤8.5 | ≤9.0 | ≤9.5 | ≤10.0 | ≤10.5 | ≤11.0 | ≤11.5 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Sparse | 443.1 | 182 | 294 | 471 | 721 | 1,108 | 1,654 | 2,524 | 3,763 | 5,668 |
| Virgo | 486.5 | 187 | 325 | 519 | 833 | 1,314 | 1,991 | 3,030 | 4,487 | 6,593 |
| Cygnus | 375.3 | 463 | 838 | 1,474 | 2,613 | 4,457 | 7,457 | 12,430 | 20,387 | 33,136 |
| Sagittarius | 451.8 | 383 | 662 | 1,240 | 2,107 | 3,653 | 6,373 | 11,059 | 19,272 | 32,387 |
| Southern Milky Way | 248.7 | 190 | 308 | 535 | 900 | 1,488 | 2,402 | 3,931 | 6,264 | 9,658 |

These differences are substantial: at V≤9.0 Cygnus has 6.96 stars/deg² versus
1.63 in the sparse field; at V≤11.5 it has 88.28 versus 12.79 stars/deg².
Sagittarius has 71.68 stars/deg² at V≤11.5.

## Candidate paper densities

Values are stars/cm², using `100 × stars/deg² / scale²`. Standard 9.0 is the
reference. These are mean densities over each region; dense local patches can
be busier than a whole-window mean.

| Candidate | All sky | Sparse | Virgo | Cygnus | Sagittarius | Southern MW |
|---|---:|---:|---:|---:|---:|---:|
| Pocket 7.5 (5 mm/deg) | 2.563 | 1.643 | 1.538 | 4.934 | 3.391 | 3.056 |
| Pocket 8.0 (5 mm/deg) | 4.409 | 2.654 | 2.672 | 8.931 | 5.861 | 4.954 |
| Standard 9.0 (10 mm/deg) | 3.160 | 1.627 | 1.712 | 6.962 | 4.663 | 3.619 |
| Deep 10.0 (20 mm/deg) | 2.154 | 0.933 | 1.023 | 4.967 | 3.526 | 2.415 |
| Deep 10.5 (20 mm/deg) | 3.529 | 1.424 | 1.557 | 8.279 | 6.119 | 3.952 |
| Eyepiece 11.0 (40 mm/deg) | 1.419 | 0.531 | 0.576 | 3.395 | 2.666 | 1.574 |
| Eyepiece 11.5 (40 mm/deg) | 2.252 | 0.799 | 0.847 | 5.518 | 4.480 | 2.427 |

### Density ratios to Standard 9.0

| Candidate | All sky | Sparse | Cygnus | Sagittarius |
|---|---:|---:|---:|---:|
| Pocket 7.5 | 0.81× | 1.01× | 0.71× | 0.73× |
| Pocket 8.0 | 1.40× | 1.63× | 1.28× | 1.26× |
| Standard 9.0 | 1.00× | 1.00× | 1.00× | 1.00× |
| Deep 10.0 | 0.68× | 0.57× | 0.71× | 0.76× |
| Deep 10.5 | 1.12× | 0.88× | 1.19× | 1.31× |
| Eyepiece 11.0 | 0.45× | 0.33× | 0.49× | 0.57× |
| Eyepiece 11.5 | 0.71× | 0.49× | 0.79× | 0.96× |

Pocket 8.0 is a clear dense-field increase over Standard's paper loading even
though the all-sky value is only 1.40×. Deep 10.5 is close to Standard overall,
but 1.19× in Cygnus and 1.31× in Sagittarius. Neither is automatically too
dense, but those are the fields that deserve the field test. Eyepiece 11.5 stays
below Standard's average paper density because the map scale is four times
larger.

## Dense-field stress test

| Field | Magnitude extension | Added stars/window | Added stars/deg² | Cumulative factor |
|---|---|---:|---:|---:|
| Cygnus | 9.0 → 10.0 | 4,844 | 12.91 | 2.85× |
| Cygnus | 9.0 → 10.5 | 9,817 | 26.15 | 4.76× |
| Cygnus | 10.5 → 11.0 | 7,957 | 21.20 | 1.64× |
| Cygnus | 11.0 → 11.5 | 12,749 | 33.97 | 1.63× |
| Sagittarius | 9.0 → 10.0 | 4,266 | 9.44 | 3.02× |
| Sagittarius | 9.0 → 10.5 | 8,952 | 19.81 | 5.25× |
| Sagittarius | 10.5 → 11.0 | 8,213 | 18.18 | 1.74× |
| Sagittarius | 11.0 → 11.5 | 13,115 | 29.03 | 1.68× |

The >4× jump from 9.0 to 10.5 is the biggest practical warning for the Deep
optional limit. At 40 mm/deg, neither Eyepiece candidate is obviously extreme in
paper density, though the faintest bin still adds many actual plotted catalogue
stars to the Milky Way fields.

## Completeness and scale law

ESO Tycho-2 catalogue documentation gives approximately 99% completeness at
V=11.0 and 90% at V=11.5 ([catalogue properties](https://archive.eso.org/ASTROM/TYC-2/docs/htmfiles/property.html)).
The observed 11.0–11.5 growth factor of 1.5867 may therefore be depressed partly
by incompleteness. This report does not correct it: the cartographic density of
the actual catalogue is the quantity needed for this atlas.

For an approximate constant-paper-density comparison, doubling scale requires
four times as many stars. Interpolating the measured all-sky cumulative counts
gives these magnitude increments:

| Scale doubling | Baseline limit | Limit for equal paper density | Delta mag |
|---|---:|---:|---:|
| 5 → 10 mm/deg | 7.5 | 8.77 | +1.27 |
| 10 → 20 mm/deg | 9.0 | 10.37 | +1.37 |
| 20 → 40 mm/deg | 10.0 | 11.44 | +1.44 |

The last estimate uses 10.0 as its baseline so the fourfold target remains
inside the measured Tycho-2 range. It is empirical interpolation, not a claim
that the same increment works for every field. It supports about +1.3 to +1.4
mag per scale doubling in all-sky means, while the regional field differences
argue for more restraint in Cygnus and Sagittarius.

Pocket Sky Atlas at roughly 5 mm/deg and V≈7.6 is contextually close to Pocket
7.5's measured mean paper density. Sky Atlas 2000.0 at 7.1 mm/deg, V≈8.5 and
Uranometria 2000.0 at 18.5 mm/deg, V≈9.75 are useful scale/limit reference
points; their actual plotted star densities are not inferred here. NightSky's
candidate densities above come only from its Tycho-2 store.

## Recommendation

| Edition | Official default | Optional deeper mode |
|---|---:|---:|
| Pocket | 7.5 | 8.0 |
| Standard | 9.0 | — |
| Deep | 10.5 | — |
| Eyepiece | 11.0 | 11.5 |

The measured scaling supports Deep 10.5 as the selected production limit. It
increases the paper star density substantially over Deep 10.0, especially in
Milky Way fields; the plotted faint-end symbol diameter is reduced to keep the
additional stars distinct. Pocket remains at 7.5, Standard at 9.0, and the
Eyepiece figures remain research recommendations rather than production
defaults. Eyepiece 11.5 remains subject to the 90%-at-11.5 completeness caveat.
