# Optional UCAC4 faint-star supplement

The optional faint layer supplements the Tycho-2 + Hipparcos store, which
remains the named-star and WDS layer. Pocket, Standard, and Deep main charts do
not query the supplement. A detail chart may opt in through its own `stars`
configuration; its DSO selection still comes from its parent edition.

For example, Pocket PD02 uses this supplement to reach its configured 11.25
magnitude limit. This is an approximate cartographic limit, not precision
photometry; the catalogue's magnitude sources and calibration limitations are
described below.

## Source and format

UCAC4 is the USNO CCD Astrograph Catalog DR4, distributed in 900 declination
zones. The official binary zone records are 78 bytes each. RA and south-pole
distance are integer milliarcseconds in J2000 ICRS; the importer converts the
latter with `Dec = SPD - 324000000 mas`. Source documentation lists about
113.8 million rows. Each row includes APASS B,V,g,r,i for a subset and native
UCAC model/aperture photometry. Its cross-match flag identifies Hipparcos and
Tycho-source stars.

UCAC4 `f.mag` is the UCAC fit-model magnitude in a 579–642 nm bandpass,
between V and R. It is not Johnson V. UCAC4 supplies APASS V, 2MASS J/Ks,
their quality flags, and the source-position flag in the 78-byte records. The
atlas magnitude hierarchy is:

1. Use APASS Johnson V when the magnitude is present and its error field is
   valid and nonzero. An error value of zero can mark bright-star Tycho V
   substitutions, so it is not treated as APASS Johnson V.
2. Otherwise, use a deterministic empirical calibration fitted from UCAC4
   records that have both valid APASS V and UCAC `f.mag`. Calibration pairs
   have APASS V errors no larger than 0.30 mag. The importer takes a seeded
   reservoir sample of at most 100,000 records, fits a linear model and a
   linear model with 2MASS `J-Ks`, then compares residuals on a deterministic
   20% holdout. The linear model is selected only when it reduces holdout RMS
   by at least 0.02 mag versus raw `f.mag`; the colour term is selected only
   when it reduces RMS by at least 0.02 mag versus the selected simpler model.
   A colour requires clean 2MASS J and Ks measurements with
   quality A in both bands. The equations are `V_atlas = a + b*f.mag` or
   `V_atlas = a + b*f.mag + c*(J-Ks)`; the fitted coefficients and holdout
   diagnostics are saved in the manifest. Coefficients are empirical and are
   derived from the exact local UCAC4 files used by the import.
3. If no calibration can be fitted, or a usable `f.mag` lies outside the
   calibration sample's range, preserve raw `f.mag` as an explicitly marked
   raw fallback. It is not silently treated as Johnson V.

This is a cartographic calibration for approximate consistency around
magnitude 10–14, not precision photometry. The manifest includes the sample
size and range, raw/linear/colour holdout median residual, RMS and MAD, residual
bins by magnitude and colour, and final faint-star counts and percentages from
APASS V, calibrated UCAC fallback, and raw fallback.

### Full-catalogue calibration run

The full UCAC4 import on 2026-10-05 yielded 77,299 calibration pairs after
requiring valid APASS V, APASS error no larger than 0.30 mag, and the 8–16 mag
fitting interval. Of these, 71,628 had clean 2MASS J and Ks quality-A values.
The held-out comparison selected the colour model:

```text
V_atlas = 0.312800 + 0.970737*f.mag + 0.451936*(J-Ks)
```

For fallback stars without usable J/K colour, the selected linear model is:

```text
V_atlas = 0.694878 + 0.959488*f.mag
```

On the common held-out colour sample, raw `f.mag` had median residual −0.126,
RMS 0.272 mag and MAD 0.112 mag. The linear fit had median −0.012, RMS 0.236
mag and MAD 0.117 mag. The colour fit had median −0.012, RMS 0.214 mag and
MAD 0.083 mag. The selected model's binned median residual moves from about
+0.10 mag at `f.mag` 10.0–10.5 to about −0.02 mag at 13.5–14.0; residuals
and counts by 0.5-mag and 0.5-colour bins are retained in the import manifest.
The remaining scatter and magnitude trend are why these values are suitable
for chart selection but not for scientific photometry.

In this run, the final store contains 11,199,184 rows: 9,013,968 (80.49%) use
APASS V, 2,184,845 (19.51%) use a calibrated UCAC fallback—1,562,999 colour
calibrated and 621,846 linear—and 371 (0.003%) use raw `f.mag` because they
fell outside the fitted range.

The binary source can be downloaded from the CDS UCAC4 mirror. UCAC4's NASA/IPAC
metadata identifies the data as U.S. government work; cite Zacharias et al.
(2013) and DOI `10.26131/IRSA17`. Raw source files and generated databases stay
local under the ignored `data/raw/` and `data/processed/` trees; they are not
vendored by this feature.

Source references: [UCAC4 definitions and fields](https://irsa.ipac.caltech.edu/data/USNO/UCAC4/ucac4.html),
[CDS UCAC4 binary zones](https://cdsarc.cds.unistra.fr/ftp/cats/I/322A/UCAC4/u4b/),
and [NASA data.gov metadata/license](https://catalog.data.gov/dataset/the-fourth-u-s-naval-observatory-ccd-astrograph-catalog).

## Fetch and import

The complete zone set is approximately 8.5 GiB before the local SQLite store.
Fetch all zones explicitly:

```sh
nightsky data fetch-ucac4 --dest data/raw/ucac4/u4b
nightsky data import-ucac4-faint \
  --raw data/raw/ucac4/u4b \
  --primary-star-store data/processed/stars/tycho2.sqlite \
  --out data/processed/stars/faint_stars.sqlite \
  --limit 14.0
```

For a small regional parser check, `--zones 450` fetches one zone. A partial
zone directory produces a partial store; the manifest lists zones and marks
whether all 900 were imported. It must not be used as the all-sky Eyepiece
store. Re-running fetch skips existing zone files and resumes at missing ones.

UCAC4's first `tf` source flag is applied before positional matching: 1, 2 and 7
identify Hipparcos-source positions; 3, 4 and 5 identify Tycho-source
positions. These are catalogue-origin flags, not individual HIP/TYC identifiers.
Flag 6 identifies an FK6 position substitution and is not assumed to be present
in the NightSkyAtlas Tycho-2/Hipparcos store, so it goes through the position
check. Flags 8 and 9 describe proper-motion substitutions and do not establish
that the position is already in the primary store.

For remaining rows, a unique primary-store star within 0.5 arcseconds is
removed by a one-to-one positional fallback. Multiple primary candidates within
that radius are retained as ambiguous; a primary star cannot remove multiple
UCAC4 detections. The manifest separates Hipparcos flags, Tycho flags,
positional removals, ambiguous candidates retained, and retained UCAC4 rows
within 2 arcseconds of a primary star. Stable integer row IDs are derived from
the zone and row number; compact SQLite rows have no per-star catalogue strings
or name fields.

In the full-catalogue run, the importer excluded 2,421,514 rows with Tycho
source flags and 114,768 with Hipparcos source flags, then removed 4,798 unique
positional matches. No positional case had multiple primary candidates within
0.5 arcseconds; 325 retained UCAC4 rows lie within 2 arcseconds of a primary.
The source flags identify the origin catalogue, not a unique HIP/TYC number.

```sh
nightsky data faint-star-count --store data/processed/stars/faint_stars.sqlite
```

The completed density/performance study commands were retired in the CLI
cleanup. The store remains queryable at any magnitude limit through
`FaintStarStore`; import, calibration and rendering support are unchanged.

To opt a single chart or atlas build in, pass `--faint-star-store` and
`--faint-star-limit`. Both are required together; absent these options, the
production chart path is unchanged. When enabled, the primary Tycho-2/Hipparcos
query is raised to at least the faint-star limit (while preserving a higher
explicit primary limit). This is necessary because UCAC4 counterparts are
removed from the supplement: a fainter Tycho star must still be queried from
the primary store to appear once. The supplement then contributes unmatched
UCAC4 stars through its own limit. Faint stars have positions and magnitude
only and cannot acquire proper, Bayer, or Flamsteed labels or WDS associations.

## Limitations

- UCAC4 APASS V is unavailable for roughly half the catalogue. The empirical
  fallback is calibrated only where valid APASS V exists; local residuals and
  the selected equation must be reviewed in the generated manifest.
- APASS and 2MASS quality vary across the sky. The calibration may not remove
  all colour, crowding, or magnitude-dependent systematics.
- The 0.5 arcsecond crossmatch is deliberately conservative; some unresolved
  catalogue duplicates can remain near blended primaries.
- Tycho-2 incompleteness and UCAC4/APASS photometric quality vary by sky area.
- The full source import was not run in the restricted build environment when
  DNS access to CDS is unavailable. In that case use the commands above on a
  machine with network access; don't substitute synthetic counts for real
  survey statistics.
