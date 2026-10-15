# Visual nebula curation v1

NightSkyAtlas now has a first target-first Deep nebula curation proposal in
[`curated_dark_nebulae_v1.yaml`](../config/curated_dark_nebulae_v1.yaml) and
[`curated_bright_nebulae_v1.yaml`](../config/curated_bright_nebulae_v1.yaml).
They use stable local object IDs, NightSkyAtlas-owned `include` / `review`
decisions, and separate representation notes. They do not add catalogue rows,
merge aliases, or store third-party ratings or descriptions.

The selected v1 targets are now active in the Deep edition. Selection uses the
existing observing-list membership mechanism for bright nebulae and the
edition's curated-designation rule for dark nebulae. This does not change the
catalogue records, physical-object identities, symbol rendering, or outline
geometry. Dark-cloud entries are locator symbols, not invented contours.

## Current v1 proposal

| | Dark | Bright |
|---|---:|---:|
| Curated target entries | 52 | 49 |
| Include | 45 | 42 |
| Manual review | 6 | 7 |
| Excluded as a separate marker | 1 | 0 |
| Unique local object IDs in included targets | 47 | 42 |
| Added to the Deep curated selection | 32 | 13 |
| Included targets without a visually calibrated contour | 45 | 7 |

Dark preferred identities among included target entries are Barnard (20), LDN
(22), and named/region targets (3). The 47 local object IDs include multiple
components for Barnard's E. Bright preferred identities are NGC/IC/M and
Sharpless; no LBN object is a standalone v1 primary target. The 42 bright
targets comprise 39 bright nebulae and 3 supernova remnants.

The local observing-guide analysis supplied aggregate evidence for 20 dark and
11 bright emission/reflection candidates rated at least four stars. Those
ratings and the derived membership are not present in these curated files. The
bright core also uses the existing NightSkyAtlas target-first nebula research
matrix. This is an initial editorial selection, not a claim that every AL
program member was reviewed.

## Astronomical League inputs

No local AL membership file or fixture was present. The official Dark Nebula
program requires 35 listed objects and 35 additional choices from its optional
pool; its complete candidate-pool size and exact overlap have not been
calculated here. The official Bright Nebula program describes 150 targets.
Exact AL-to-local-object matches and AL/NSOG overlap remain open until the
source memberships are supplied in normalized form. See the [Dark Nebula
program](https://www.astroleague.org/dark-nebula-observing-program/) and
[Bright Nebula program](https://www.astroleague.org/bright-nebula-observing-program/).

Put private files at:

```text
local/research/nebula-lists/al_dark_nebula.csv
local/research/nebula-lists/al_bright_nebula.csv
```

The completed local coverage audits used CSV/TSV designation and optional
coordinate/type fields. Their one-time research adapters and commands have
since been retired; the resulting curation memberships remain active. Saved
coverage reports are under `build/research/al_dark_coverage.*` and
`build/research/al_bright_coverage.*`. See `CLI_CLEANUP_AUDIT.md`.

Keep source files and per-entry reports local. External-list membership is
validation evidence; it does not automatically select an object for Deep.

## Identity and review

The manual review queue is
[`nebula_manual_review_v1.yaml`](../config/nebula_manual_review_v1.yaml).
LDN/Barnard source references remain relationships, not aliases:

- LDN 66 ↔ B 72: source cross-reference, centres 7.6′ apart; Barnard extent is
  unavailable locally.
- LDN 93 ↔ B 86: source cross-reference, centres 4.28′ apart; approximate
  extents overlap. Keep separate catalogue IDs but use B 86 as the single map
  locator for this visual field.
- LDN 534 references six Barnard objects over a broad region. It must not be
  merged into six aliases of one physical object.

The dark review queue also contains unresolved identities for Dark Doodad,
R Coronae Australis, B 5, SL 7 and SL 11, plus LDN 534. These are candidates
for future catalogue/source work, not invented production records. LDN 93 is
excluded as a second plotted marker because B 86 provides a single locator for
the same practical field; the two catalogue identities remain distinct. LDN
66 is included separately from B 72: their centres are 7.6′ apart, enough to
keep the two locator positions distinguishable at Deep's printed scale. This
is a cartographic choice, not an assertion of exact physical identity.

Bright region reviews include Tarantula, Rosette, Eagle, Gamma Cygni, N 66,
Veil and Vela, where one observing region does not map cleanly to one local
catalogue object. IC 1396 is included as a locator despite its local record
covering only part of the larger nebula complex. LBN 239 remains out of v1
until its independent visual usefulness and shape are confirmed.

## Southern-sky check

Among resolved included dark objects, 32 have southern declinations and 5 lie
south of −30°. These include Coalsack and B 228; the remaining deep-southern
named targets without local object IDs stay in review. The included bright set
has 23 southern objects, including Eta Carinae (NGC 3372), Running Chicken
(IC 2944), the Prawn (IC 4628), Cat's Paw (NGC 6334), and Lobster (NGC 6357);
8 are south of −30°. Tarantula and N 66 remain review items until a nebular
region ID is distinguished from their local cluster records.

## Shape policy

All included dark targets currently use a locator position; none of those 45
targets has a NightSkyAtlas dark-cloud contour. Area-derived LDN extents are
not silhouettes. Among included bright targets, 35 have a traced survey
isophote and 7 have only catalogue/rough-region geometry or a locator. Survey isophotes are
not calibrated to visual thresholds, so the contour should not be presented
as a precise visual boundary.

Selection and representation remain separate. A useful target may be listed
with a locator while a reliable footprint is pending. No opacity, size, or
single numerical visibility threshold defines this curation.

## Introduction draft

> Bright and dark nebulae in NightSkyAtlas are curated for visual observing
> rather than selected for catalogue completeness. Deep prioritizes established
> observing targets and currently offers less diffuse-nebula depth than a
> Uranometria-class reference atlas. The selection and its representations can
> grow as better shape data and community proposals become available.

## Community proposals

A proposed addition should include a canonical NightSkyAtlas object ID, its
catalogue identity, a short reason it is useful for visual observing, and an
optional independent observing reference or outline source. NSOG membership is
not required. Report catalogue relationships separately from aliases unless
same-target identity has been checked.

## Research outputs

The Deep selection now covers 21 of the 59 matched NSOG dark targets by strict
object identity and 68 of 114 NSOG emission targets. The two missing 4–5-star
dark identities are LDN 534 (intentionally held for review) and LDN 93; the
latter's visual field is marked by B 86, while the catalogue IDs stay separate.
All 11 matched 4–5-star emission/reflection targets are selected. The bright
selection is supplied by
`data/fixtures/observing_lists/nightsky_curated_bright_nebulae_v1.json`; the
dark selection is listed in the Deep `curated_designations` configuration.
Both are NightSkyAtlas-owned curation data and contain no NSOG ratings or
descriptions. The local selector comparison in
`build/research/nebula_curation_v1.json` and `.md` predates activation and is
kept as a research artifact; regenerate it before using it as a current Deep
delta report.
