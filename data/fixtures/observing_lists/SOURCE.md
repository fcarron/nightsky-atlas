# Observing-list fixtures

Curated visual observing lists used as DSO selection metadata.  Membership is
atlas metadata, not an astronomical fact: fixtures here are never merged into
the normalized catalogue and never modify `DeepSkyObject` fields.

Designations are normalized at load time (whitespace removed, NGC/IC leading
zeros stripped, Messier numbers canonicalized), so a fixture may list
`NGC 869`, `NGC869` or `M 42` interchangeably.

## herschel400.json

- **List:** Herschel 400 (400 catalogue entries)
- **Source:** Wikipedia, *Herschel 400 Catalogue*, revision 1369720351
  (<https://en.wikipedia.org/wiki/Herschel_400_Catalogue>)
- **License:** CC BY-SA 4.0 (Wikipedia text)
- **Retrieved:** 2026-09-16
- **Contents:** 402 normalized NGC designations.  Three Herschel rows carry a
  double NGC number and were expanded to one entry per designation
  (NGC 650/651, NGC 2371/2372, NGC 4038/4039), giving 402 entries for 400
  catalogue rows.
- **Identity normalization:** NGC 651 → NGC 650, NGC 2372 → NGC 2371, and
  NGC 6885 → NGC 6882 are explicit alternate/duplicate designations. The last
  is supported by the normalized OpenNGC cross-identification. These mappings
  do not add physical objects.
- **Current unresolved rows:** NGC 2527 and NGC 7296 have no safe compatible
  physical-object match in the normalized pool. NGC 2244 is mapped to the
  normalized NGC 2239 `Cl+N` Rosette-target record. Other formerly unmatched
  designations now resolve through the imported catalogue pool.

The membership was checked against the Astronomical League's current [Herschel
400 by NGC list](https://www.astroleague.org/herschel-400-observing-program/).
The League notes that the manual uses NGC 1750 where its current website list
uses NGC 7814 and accepts either. The vendored snapshot uses NGC 7814; this is
an explicit source-version difference, not a coordinate or catalogue rewrite.

## messier.json

- **List:** modern Messier observing list, M1–M110 (110 rows)
- **Sources:** [NASA HEASARC Messier database](https://heasarc.gsfc.nasa.gov/w3browse/all/messier.html), checked against [SEDS NGC Online cross-identifications](https://spider.seds.org/ngc/cid.html)
- **Retrieved:** 2026-09-28
- **License/usage:** designation membership only; no HEASARC coordinates or photometry are imported.
- **M102 handling:** HEASARC's compiled table contains 109 objects because it treats M102 as spurious; the modern observing list has 110 entries. M102 is linked to NGC 5866 for membership only.
- **M40 handling:** this is a double-star entry rather than a DSO. It is reported separately as a non-DSO list member; it does not create a DSO symbol. The star field remains supplied by the normal star/WDS layers.

## caldwell.json

- **List:** Caldwell catalogue, 109 entries
- **Source:** [Astronomical League Caldwell Program Object List](https://www.astroleague.org/caldwell-program-object-list/)
- **Retrieved:** 2026-09-28
- **License/usage:** designation membership only; coordinates, magnitudes and dimensions continue to come from NightSkyAtlas catalogues. The source page gives J2000 positions, but they are not ingested.
- **Mapping:** C14 expands to NGC 869 and NGC 884, avoiding a third aggregate C014 plotted over the two clusters. C41 maps to the existing Melotte 25 / Hyades object. C37 maps to NGC 6882; the existing OpenNGC cross-identification and duplicate-entry reference connect the list's NGC 6885 designation to it. C50 / NGC 2244 maps to the existing NGC 2239 OpenNGC record, whose raw type is `Cl+N` and whose cross-identification includes C050; NGC 2244 and NGC 2239 are treated as alternate designations of the same Rosette cluster target. The 2026-10-06 source-identity correction represents this entry as an open cluster, preserves NGC 2239 internally and prefers NGC 2244 for observer-facing output; no second physical object is created.
- **Display rule:** Caldwell is observing-list metadata only. Caldwell designations are not used for atlas labels.

## nightsky_curated_pn.json

- **List:** NightSkyAtlas's independently curated all-sky planetary-nebula minimum set (104 physical targets).
- **Source and method:** [`docs/PN_DARK_CURATION.md`](../../../docs/PN_DARK_CURATION.md) and its cited independent visual-observing sources; this is an original editorial selection, not a copy of any one external list.
- **License:** NightSkyAtlas project (MIT). The fixture stores designation membership only, with no third-party descriptions, ratings or photometry.
- **Edition use:** Deep and inherited Reference use the membership as an additive PN selection reason. Pocket and Standard PN selection is unchanged; all their targets are already selected by their existing rules.
- **Identity:** Four names absent from the previous normalized pool are imported individually from the existing VizieR `IV/24` source as `Jones 1`, `J 900`, `Minkowski 1-64` and `Shapley 1`. Their catalogue provenance and aliases remain in the normalized records.

## nightsky_confirmed_abell_pn.json

- **List:** 72 confirmed Abell planetary-nebula targets in the current normalized pool.
- **Source and method:** Abell entries in Kohoutek's `IV/24` table without its `f_PK` possible/misclassified marker; Abell 21 is additionally included because independent observing references establish it as a visual PN target. The two NGC aliases remain represented by their canonical physical-object IDs.
- **License/usage:** Designation membership only; no catalogue measurements, descriptions or ratings. No upstream licence is asserted for the Abell-derived identifiers; see the source citation and repository data policy.
- **Edition use:** Deep adds these targets regardless of missing magnitude or size. Reference keeps its separate catalogue-coverage policy; Pocket and Standard are unchanged.
- **Exclusions:** `f_PK=*` entries are only possible PN and are not added automatically; known misclassifications are not plotted as PN. Abell 21 is the explicit independently supported exception.


## nightsky_pocket_classics.json

- **List:** Three NightSkyAtlas editorial exceptions: Melotte 20, NGC 281 and NGC 2359.
- **Source and method:** Conservative visual-target review in [`docs/POCKET_DSO_AUDIT.md`](../../../docs/POCKET_DSO_AUDIT.md), normalized to existing catalogue identities.
- **License:** Original NightSkyAtlas membership decision (MIT); no copied descriptions, ratings or photometry.
- **Edition use:** Forced only in Pocket, with the reason `pocket_curated_visual_target`; it does not enable the full Melotte catalogue.

## nightsky_curated_dark_nebulae_v1.json

- **List:** 47 canonical object IDs from the included entries in `config/curated_dark_nebulae_v1.yaml`.
- **Source and method:** NightSkyAtlas visual-target curation documented in [`docs/NEBULA_CURATION_V1.md`](../../../docs/NEBULA_CURATION_V1.md). Entries awaiting identity review are excluded.
- **License:** Original NightSkyAtlas selection (MIT); designations only, with no copied observing notes or ratings.
- **Edition use:** Standard and Deep. This shares the existing curated targets; it does not expand selection to all Barnard or LDN entries.

## nightsky_curated_bright_nebulae_v1.json

- **List:** 42 canonical object IDs from the included entries in `config/curated_bright_nebulae_v1.yaml`.
- **Source and method:** NightSkyAtlas visual-target curation documented in [`docs/NEBULA_CURATION_V1.md`](../../../docs/NEBULA_CURATION_V1.md).
- **License:** Original NightSkyAtlas selection (MIT); designations only, with no copied observing notes or ratings.
- **Edition use:** Standard and Deep. This is a curated set, not a broad LBN catalogue inclusion rule.
