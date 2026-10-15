# Washington Double Star Catalog subset (test fixture)

This directory vendors a tiny, fixed subset of the **Washington Visual Double
Star Catalog (WDS)** used only by the unit tests for
`src/nightsky_atlas/catalog/wds.py`. It is not used by any production build.

## Source

| Field | Value |
| --- | --- |
| Catalogue | The Washington Visual Double Star Catalog (WDS) |
| Authors | Mason B.D., Wycoff G.L., Hartkopf W.I., Douglass G.G., Worley C.E. |
| Reference | Astron. J. 122, 3466 (2001) |
| Maintainer | U.S. Naval Observatory |
| CDS identifier | `B/wds` |
| Edition | `2026-08-10` |
| Raw file | `wds.dat.gz` (fixed-width, 130 bytes per record) |
| Fetched | 2026-09-17, `https://cdsarc.cds.unistra.fr/ftp/B/wds/wds.dat.gz` |

## Licence

The WDS is maintained by the U.S. Naval Observatory. The USNO source page
requests the following acknowledgement, which is retained in atlas credits.
The source page does not state an explicit reuse licence, so this fixture
documentation does not rely on a separate public-domain grant:

> This research has made use of the Washington Double Star Catalog maintained
> at the U.S. Naval Observatory.

## Fixture contents

`wds_subset.dat` contains nine verbatim 130-byte WDS records, unmodified, for
well-known visual doubles and a multiple system:

| WDS name | Designation | Components | Role in tests |
| --- | --- | --- | --- |
| 19307+2758 | BNU 10 | Aa,Ab | very close pair, separation 0.0 |
| 19307+2758 | STFA 43 | AB | Albireo; close pair with a matched companion |
| 19307+2758 | RBR 12 | Ba,Bb | separation/PA sentinel `-1` (unknown) |
| 13239+5456 | STF1744 | AB | Mizar A/B |
| 13239+5456 | STF1744 | AC | Mizar/Alcor; wide pair |
| 18443+3940 | STF2382 | AB | Epsilon Lyrae (northern pair) |
| 18443+3940 | STF2383 | CD | Epsilon Lyrae (southern pair) |
| 18443+3940 | STFA 37 | AB,CD | Epsilon Lyrae quadruple; `Comp` filled |
| 02039+4220 | STF 205 | A,BC | Gamma Andromedae (Almach) |

Records are extracted verbatim from the raw file; no field is rewritten. Tests
must not require the full catalogue or network access.
