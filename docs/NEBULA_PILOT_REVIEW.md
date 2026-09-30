# Deep nebula pilot and first curation rule

Date: 2026-09-29/30. This follows the target-first research in
[`NEBULA_POLICY_RESEARCH.md`](NEBULA_POLICY_RESEARCH.md) and its
[`object matrix`](NEBULA_TARGET_MATRIX.csv). It is a three-page print pilot,
not an all-sky Deep acceptance review.

## Decision applied

Deep now selects dark nebulae from 15 stable object IDs in
`config/observing_lists.yaml`: `B033`, `C099`, `LDN 935`, `B 59`, `B 72`,
`B 78`, `B 86`, `B 92`, `B 93`, `B 142`, `B 143`, `B 150`, `B 168`, `B 228`
and `B 352`. The two Barnard pairs represent the Barnard's E and Pipe
targets, so these 15 chart objects cover **13 of the 14 proposed CORE dark
targets**. The missing CORE target is the southern Dark Doodad, for which the
current imports have no suitable object record. `B033` is OpenNGC's
Horsehead row with `B 33` merged as a Barnard cross-identifier. `C099` is
OpenNGC's Coalsack row. The remaining 14 IDs are not a blanket admission of
Barnard or LDN catalogues; four optional LDN objects in the matrix stay
Reference-only while their boundaries are unknown.

The explicit ID decision overrides an *uncertain positional cross-match* for
six selected Barnard rows (`B 59`, `B 78`, `B 92`, `B 93`, `B 150`, `B 168`).
The source uncertainty and raw record remain in the catalogue; other
uncertain external rows stay suppressed in Deep. The Reference edition clears
the curated dark-nebula gate and still selects its full dark catalogue
(2,129 dark records with the corrected pilot import). Standard and Pocket
selection rules were not changed; the factual `B033` type correction makes
that target eligible under their existing dark-nebula rules, whereas it was
previously an unclassified object. `C099` remains below their visibility
gate because it has no imported extent or photometry.

Until real dark outlines exist, Deep prints selected dark targets as fixed
2 mm locator squares. The squares are semantic *positions*, not claims about
cloud shape or area. No LDN or Barnard catalogue dimension is used as a dark
silhouette. An irregular broad target such as Coalsack still needs a contour
before this representation can be considered final atlas cartography.

The source-specific import also corrects these identities while retaining
raw snapshots and stable primary IDs:

| Primary ID | Corrected interpretation |
| --- | --- |
| `B033` | Horsehead, dark nebula; Barnard `B 33` merged as an alias |
| `C099` | Coalsack, dark nebula |
| `IC0434` | Emission background of Horsehead; erroneous Flame common name removed |
| `NGC6334` | H II/star-forming region, not SNR |
| `NGC3324` | Cluster within Gum 31/`IC2599`, not the nebula itself |
| `Sh2-240` | Simeis 147, supernova remnant, not H II |

The corrections are documented with primary sources in
[`DATA_SOURCES.md`](DATA_SOURCES.md). The import from the same raw files now
has 32,948 physical records, one fewer than before merging `B 33` into
`B033`. The pilot first used an isolated corrected import under
`build/nebula-pilot-2026-09-29/`. The normal generated
`data/processed/dso/catalogue.json` was then regenerated from the same raw
files and is byte-identical to the pilot catalogue. Its previous version and
cross-match report were saved in the pilot directory before regeneration.
One unrelated duplicate `Mel 72` is now an alias of `Mel072` under the current
importer, which accounts for the other one-row decrease from the previous
32,950-record processed catalogue.

## Print comparison

All pilots were rendered at 300 dpi on A4 landscape pages (3,508 × 2,480 px)
with the same chart definitions, stars and scale. The
temporary middle pilot removed selected raw catalogue rows solely in a
disposable input file. The final pilot uses the full corrected catalogue and
the edition-specific rule above.

| Deep chart | Baseline DSOs / hard issues | Temporary curation | Final rule |
| --- | ---: | ---: | ---: |
| [D081 Cygnus](../build/nebula-pilot-2026-09-29/final-policy/deep/charts/deep-081/preview.png) | 67 / 116 | 31 / 49 | **30 / 46** |
| [D223 Orion](../build/nebula-pilot-2026-09-29/final-policy/deep/charts/deep-223/preview.png) | 47 / 76 | 40 / 53 | **40 / 53** |
| [D393 Carina](../build/nebula-pilot-2026-09-29/final-policy/deep/charts/deep-393/preview.png) | 35 / 0 | 35 / 0 | **35 / 0** |

The full-width LDN boxes no longer dominate D081/D223. In D081, `LDN 935`
is now a small locator in the North America/Pelican gap, with `B 352` also
small. In D223 the oversized `LDN 1630` placeholder is absent; `B033` is a
single dark target against the `IC0434` outline. In D393 the existing
`IC2599` contour remains and `NGC3324` is shown as a cluster. The curation
does not materially change the Carina page because LDN's catalogue does not
cover this southern field.

**The three-page build still exits nonzero:** D081 has 46 hard layout issues,
D223 has 53, and D393 has none. The pilot total fell from 192 to 99 hard
issues after curation and source-identity corrections, but it did not resolve
the remaining layout problems. D081 still has large dashed **Sharpless** footprints (`Sh2-115`,
`Sh2-108`, `Sh2-112`) with no true outline. D223 has cramped labels around
Alnitak/B 33/IC 434 and M42/M43, plus a large schematic `Sh2-276` trace.
D393 remains crowded around Eta Carinae and Gum 31; some small labels there
need a print-size reading check. These pages are review artifacts, not
publication-ready outputs.

## Contour feasibility and rights: three dark targets

No usable dark vector contour was found in the current NightSkyAtlas outline
inventory. The following are *candidate extraction inputs*, not adopted
contours. A survey brightness edge is not automatically a visual-observer
boundary.

| Target | Practical source and extraction question | Current gate |
| --- | --- | --- |
| `B033` / B 33 | Northern optical images from the [Pan-STARRS1 public archive](https://outerspace.stsci.edu/spaces/PANSTARRS/overview), registered around the [Horsehead/IC 434 geometry](https://www.eso.org/public/poland/news/eso0202/). Trace only the compact foreground silhouette, not the larger Orion B cloud or the IC 434 emission outline. | Feasible first small-field contour pilot; choose and document a visual edge, confirm PS1 product terms and attribution before redistribution. |
| `LDN 935` | Pan-STARRS1 optical star-count/reddening deficit across the North America/Pelican lane; compare against the separately identified NGC 7000 and IC 5070 emission boundaries. | A single intensity threshold is unlikely to describe the complex dark lane; require field-by-field visual review. |
| `C099` Coalsack | The [VPHAS+ southern Galactic-plane survey](https://alasky.cds.unistra.fr/MocServer/query?ID=CDS%2FP%2FVPHAS%2FDR4%2FHalpha&fmt=html&get=record) has WCS imaging and explicit CC BY 4.0 attribution metadata. A wide mosaic or star-count/extinction map is needed for the several-degree cloud. | More extraction and mosaic work than B 33; a 2 mm locator cannot convey the shape or full extent. |

The [MAST data-use policy](https://archive.stsci.edu/publishing/data-use)
allows released science data in general but explicitly restricts commercial
use of DSS and GSC material without written permission. This matters because
the current OpenNGC nebula outlines were hand traced from DSS2. The
[ESO science product policy](https://www.eso.org/rm/api/v1/public/releaseDescriptions/70)
states CC BY 4.0 distribution with ESO credit and preserved headers, and
VPHAS+ metadata gives the same licence. These findings favor an independent
VPHAS+ derived southern contour and careful source-specific review for PS1;
they do not clear a blanket reuse of DSS-derived polygons in a distributed
atlas. No new survey image or contour was imported in this pilot.

## Follow-up: survey images, bright-nebula symbols and southern print sample

The second pilot uses the same corrected catalogue. Deep now gives a bright
nebula **without a real outline** a small dashed locator, just as it does for
dark nebulae without outlines. Its catalogue width no longer draws a large
square that suggests a measured cloud boundary. Outlined nebulae, including
`NGC7000`, `IC5070` and `IC0434`, retain their existing traced paths. This is
an edition-specific print treatment, not a change to catalogue dimensions or
selection. A locator states *where* to look; it cannot represent a large
complex such as Barnard's Loop (`Sh2-276`).

| Deep chart | First curated pilot: DSOs / hard issues | Small bright locators: DSOs / hard issues | Print observation |
| --- | ---: | ---: | --- |
| [D081 Cygnus](../build/nebula-contours-2026-09-29/bright-locators/deep/charts/deep-081/preview.png) | 30 / 46 | **30 / 0** | Sharpless boxes no longer obscure the North America/Pelican field. |
| [D223 Orion](../build/nebula-contours-2026-09-29/bright-locators/deep/charts/deep-223/preview.png) | 40 / 53 | **40 / 1** | `IC0434` path and `B033` locator are distinct; Barnard's Loop still needs a real arc. |
| [D393 Carina](../build/nebula-contours-2026-09-29/bright-locators/deep/charts/deep-393/preview.png) | 35 / 0 | **35 / 0** | Existing Carina/Gum 31 paths remain. |
| [D318 Sagittarius](../build/nebula-contours-2026-09-29/southern-audit/deep/charts/deep-318/preview.png) | — | **60 / 0** | M8 outline remains; minor Sharpless rows have compact locators. |
| [D355 Vela](../build/nebula-contours-2026-09-29/southern-audit/deep/charts/deep-355/preview.png) | — | **9 / 0** | Small NGC 2626 path remains; the much larger Gum 12 / Vela SNR region is still missing as a region object. |
| [D405 LMC](../build/nebula-contours-2026-09-29/southern-audit/deep/charts/deep-405/preview.png) | — | **272 / 9** | Real small paths survive; dense NGC/IC labels and the large `ESO056-115` enclosing symbol need separate layout work. |
| [D409 Coalsack/Musca](../build/nebula-contours-2026-09-29/southern-audit/deep/charts/deep-409/preview.png) | — | **17 / 0** | Coalsack is labelled but only as a tiny locator; Dark Doodad is still absent. |

The three original pages drop from **99 to 1** hard issue. The remaining D223
issue is the mandatory Alnilam label inside the large `Cr 70` open-cluster
symbol: the collision check treats the dashed perimeter as a filled area.
Likewise, seven of D405's nine hard issues are NGC labels inside the
`ESO056-115` enclosing symbol; two involve overlapping NGC 1962/1965/1966
symbols. These are distinct layout/region-hierarchy problems, not a reason to
restore the false Sharpless squares. Both sample builds exit nonzero because
of these issues, and neither sample is publication-ready.

Three WCS survey cutouts were reviewed; they are research artifacts under
`build/nebula-contours-2026-09-29/` and are **not** imported atlas contours:

| Target | Survey evidence | Decision |
| --- | --- | --- |
| `B033` | The [Pan-STARRS1 r-band cutout](https://outerspace.stsci.edu/spaces/PANSTARRS/pages/298812251/PS1%2BImage%2BCutout%2BService) resolves the head and neck. A 43-vertex [trace prototype](../build/nebula-contours-2026-09-29/B033_ps1_r_traced.png) has an arbitrary closure where the silhouette joins the larger Orion B cloud. The head/neck span is only about 1–2 mm at Deep scale. | Keep the distinct `B033` locator and `IC0434` emission outline on the main chart. A tiny closed polygon would imply an unsupported physical boundary. Revisit on an Orion detail map or with open-path/region semantics. |
| `LDN 935` | A 3° [Pan-STARRS1 r-band field](../build/nebula-contours-2026-09-29/LDN935_ps1_r_preview.png) shows multiple branching dark lanes, continuing to the image edge. | No single closed contour or simple image threshold is defensible. It needs a chosen region hierarchy and a larger mosaic before tracing. |
| `C099` Coalsack | A 6° [VPHAS+ DR4 r-band field](../build/nebula-contours-2026-09-29/Coalsack_vphas_r_preview.png) shows a broad dark zone, but the survey has missing coverage at the edge and the cloud extends beyond one tile. [VPHAS+ HiPS metadata](https://alasky.cds.unistra.fr/MocServer/query?ID=CDS%2FP%2FVPHAS%2FDR4%2FHalpha&fmt=html&get=record) states CC BY 4.0. | Keep the locator for identification only. Obtain a complete wider southern mosaic or extinction map, choose a documented observational boundary, and then validate at 20 mm/degree. |

The [ASSA dark-nebula report](https://assa.saao.ac.za/wp-content/uploads/sites/23/2021/07/Special-Report-4-Seeing-the-Dark.pdf)
describes the roughly 3° Dark Doodad and records several identifiers,
including Sandqvist 149 and `[DB2002b] G301.70-7.16`. These identifiers may
refer to different portions of the Musca filament in other catalogues. Its
whole-region primary ID and contour require an explicit cross-identification
before a new record is imported; the current matrix's `SDC 301.0-08.6c` is a
candidate, not a confirmed one-to-one identity.

### Remaining editorial work

1. Define real, source-documented shapes for the large northern and southern
   complexes, beginning with Coalsack, LDN 935, Barnard's Loop, Gum 12 and
   Vela SNR. Avoid closed polygons where a region has no natural closure.
2. Resolve the Dark Doodad's whole-region identity and add it through the
   catalogue/provenance workflow. Audit other southern CORE gaps in the LMC,
   SMC and Vela; the four southern sample pages are a check, not all-sky proof.
3. Handle enclosing region symbols as boundaries during label validation, and
   review the two remaining D405 NGC-symbol collisions at print scale.
4. Review Reference's standalone LBN plotting separately: the catalogue is
   imported, but the current edition policy does not enable standalone
   `VII/9` rows.
