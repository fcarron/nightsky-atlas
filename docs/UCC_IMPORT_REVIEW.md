# UCC 260615 import and matching review

This report records the local import audit performed on 2026-10-13. The raw
release is in `data/raw/ucc/260615/` (local, ignored data); rerun with
`nightsky data fetch-ucc` and `nightsky data import-ucc`. The complete
machine-readable row decisions are in
`data/processed/dso/ucc-crossmatch.json`.

## Release and field handling

The versioned README lists 18,299 clusters and documents `Name(s)`, `name`,
`RA_ICRS`, `DE_ICRS`, `r_50`, `N_membs`, `C3`, `UTI`, `P_dup`, and `bad_oc`.
The file checksum is Zenodo MD5
`b09c51f12865df0233df8fd90e4a8443`; independently computed SHA-256 is
`dfed72e9469dbf786ff1d0708c836aee356cde66dd1ea26531bebe143532a235`.
README MD5 is `2b7ee76fb08e7f21976ee03f81ad4b83`. `C3` values in this release
span all 16 combinations from AA through DD. `UTI` and `P_dup` each span 0–1.
The `bad_oc` column contains 10,130 `y` and 8,169 `n` values.

`r_50` spans 0.3–805.5 arcmin in this snapshot. It is retained verbatim in
source provenance because it is the radius containing half the estimated
members; it is not converted to a visible cluster diameter. UCC supplies no
visual diameter in this table. `N_membs` becomes the normalized member count;
quality values remain available in each UCC source record's `raw_fields`.

The Zenodo record and release README do not state a data licence. The GitHub
software licence is not applied to the dataset. Raw and derived UCC data are
kept local pending clarification of redistribution rights. The README asks
users to cite Perren et al. (2023), MNRAS 526, 4107–4119,
[doi:10.1093/mnras/stad2826](https://doi.org/10.1093/mnras/stad2826), and gives
an acknowledgement sentence.

## Crossmatch outcome

| Decision | Rows | Rule |
| --- | ---: | --- |
| Exact identity merged into an existing canonical object | 577 | Normalized designation/alias, compatible object type, and coordinate agreement within the established open-cluster search envelope |
| New normalized UCC cluster object | 4,654 | No existing alias, type conflict, or nearby open-cluster candidate |
| Uncertain, retained only in the report | 404 | 279 position-only candidates, 109 cross-type/identity conflicts, 16 large coordinate disagreements |
| Excluded by `bad_oc=y` | 10,035 | Explicit likely-asterism/moving-group/artifact flag; 95 flagged rows had exact safe matches and were attached as source records instead |
| Held for duplicate-risk review | 2,629 | `P_dup >= 0.5`, unless an exact safe existing-object match was established first |
| **Total** | **18,299** | |

No positional-only match is automatically merged. The search radius follows the
existing open-cluster extent-aware envelope (20–90 arcmin), using only the
existing catalogue extent; UCC `r_50` is not used as an extent. Stable IDs of
existing objects, their coordinates, angular extents, object types and primary
chart labels were preserved. The resulting 37,611-object catalogue has no
duplicate IDs. Re-importing the result produced byte-identical normalized
catalogue and crossmatch-report files.

The six existing sample identities resolved as follows:

| Existing target | Canonical ID retained | UCC result |
| --- | --- | --- |
| Melotte 25 / Hyades | `C041` | Exact alias match |
| Melotte 20 | `Mel 20` | Exact alias match |
| Stock 2 | `Stock 2` | Exact alias match |
| Stock 23 | `Stock 23` | Exact alias match |
| Collinder 69 | `Cr 69` | Exact alias match |
| Collinder 399 | `Cl399` | Exact alias match |

## Seven requested observing targets

| Target | In UCC? | UCC name / alternatives | Identity and quality | Existing catalogue / import decision | Edition recommendation |
| --- | --- | --- | --- | --- | --- |
| Kemble 1 | No | — | A visual asterism, not a physical cluster entry | Absent; no import | Keep as a future asterism/region annotation question, not a UCC cluster |
| [Trumpler 2](https://ucc.ar/_clusters/trumpler2/) | Yes | `Trumpler 2`; Collinder 29, MWSC 219, OCL 365, FoF 2297 | C3 AA, UTI 0.96, P_dup 0, `bad_oc=n`, 245 members, `r_50=15.3′` | New canonical `Trumpler 2`; current catalogue has no identity alias | Selected for Pocket in the follow-up review using the existing generic symbol; `r_50` is not a chart diameter |
| [Stephenson 1](https://ucc.ar/_clusters/stephenson1/) | Yes | `Stephenson 1`; MWSC 3018, Delta Lyr, OCL 137, FoF 2433, OCSN 263, LISC 3582 | C3 AA, UTI 0.98, P_dup 0, `bad_oc=n`, 438 members, `r_50=37.2′` | New canonical `Stephenson 1` | Selected for Pocket in the follow-up review using the existing generic symbol; UCC supplies no visual diameter |
| [Harvard 20](https://ucc.ar/_clusters/collinder408/) | Yes | UCC main name `Collinder 408`; Harvard 20, MWSC 3198, OCL 116, FSR 0144 | C3 AA, UTI 0.76, P_dup 0, `bad_oc=n`, 54 members, `r_50=3.1′` | Exact match to existing stable ID `H20`; Pocket and Deep already select it | Already represented; no selection change |
| Melotte 31 | Yes | `Melotte 31` | C3 DD, UTI 0.04, `bad_oc=y`, 19 members, `r_50=5.9′` | Rejected from physical cluster import by the UCC non-cluster flag | Do not select as a physical open cluster without independent evidence; likely asterism/candidate |
| [Trumpler 24](https://ucc.ar/_clusters/trumpler24/) | Yes | `Trumpler 24` | C3 BC, UTI 0.34, P_dup 0, `bad_oc=n`, 17 members, `r_50=58.8′` | Uncertain: positional candidate `Cr 316` is 19.33′ away; retained in the review report, not merged or added | Defer. Low trust/loose structure, possible moving-group interpretation, no visual diameter, and nearby identity ambiguity |
| [Stock 7](https://ucc.ar/_clusters/stock7/) | Yes | `Stock 7`; MWSC 202, FoF 2320 | C3 AA, UTI 0.80, P_dup 0.16, `bad_oc=n`, 157 members, `r_50=13.9′` | New canonical `Stock 7`; no nearby existing open-cluster identity candidate | Selected for Pocket in the follow-up review using the existing generic symbol; `r_50` is not a chart diameter |

UCC pages also identify Trumpler 2, Stephenson 1, Collinder 408/Harvard 20,
Trumpler 24 and Stock 7 with these identities. The catalogue-backed UCC
records show that several earlier “not in catalogue” results meant “missing
from the imported NightSkyAtlas sources,” not “absent from astronomical
catalogues.”

The follow-up Pocket review selected Trumpler 2, Stephenson 1 and Stock 7 using
the existing fallback symbol; it did not treat `r_50` as a visible diameter.
The edition hierarchy carries those choices into Standard and Deep. Harvard 20
was already selected in Pocket and Deep; Standard does not currently select it.
Melotte 31 remains excluded as a physical cluster based on this UCC record, and
Trumpler 24 remains deferred until its identity relative to Cr 316 is resolved.
Kemble 1 would need a separate asterism representation rather than a UCC
cluster entry.

## Edition-selection check

Import did not add UCC to any edition's `included_catalogues`, and no observing
selection files were changed. The current selected-ID sets before and after
the import are identical:

| Edition | Before | After | Added / removed |
| --- | ---: | ---: | ---: |
| Pocket | 1,264 | 1,264 | 0 / 0 |
| Standard | 2,962 | 2,962 | 0 / 0 |
| Deep | 9,532 | 9,532 | 0 / 0 |

The data catalogue grew from 32,957 to 37,611 normalized physical-object
records; that is a data-availability change, not an atlas-selection change.
