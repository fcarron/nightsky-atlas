# Deep and Reference nebula curation — research draft

Date: 2026-09-29. Editorial research only; no catalogue imports, production
selection, symbols, or astronomical facts were changed. Planetary nebulae are
outside this review.

The subsequent implementation and print-scale pilot are recorded in
[`NEBULA_PILOT_REVIEW.md`](NEBULA_PILOT_REVIEW.md). Statements below about the
initial imported catalogue describe the research baseline.

## Decision in brief

Build Deep from **physical visual targets and named observing regions**, not
from all rows in a photographic catalogue. The companion
[`NEBULA_TARGET_MATRIX.csv`](NEBULA_TARGET_MATRIX.csv) records 106 first-pass
all-sky targets (59 CORE, 47 EXTENDED), one row per proposed observing target.
It separates emission, reflection, dark, SNR and mixed nebulae. The target set
is a curation proposal, not a completeness claim or an instruction to change
selection code. Each row gives a preferred atlas identity, approximate J2000
position and extent, source-family coverage, current contour status, Deep and
Reference disposition, source links, and identity notes. Coordinates and
extents are **finding/footprint approximations**, not proposed contour vertices.
For broad regions, published observing extents replace small NGC/IC catalogue
patch sizes where those would misdescribe the visual target.

**Proposed policy:** Deep plots all CORE targets, and EXTENDED targets with a
validated visible footprint. An object with a useful position but no defensible
shape may receive a restrained, explicitly non-morphological symbol when it is
compact and distinctive; broad dark/bright clouds should wait for a contour or
be indexed in Reference. Reference retains valid catalogue records for search,
aliases, and cross-identification, but a Reference record is not automatically
a drawn shape. No LDN or LBN row should create a second chart object where it
describes the same target, a parent complex, or a subregion already modelled.
CORE is a **Deep content requirement**, not permission to invent a footprint:
an unresolved CORE shape must be called out for editorial work rather than
silently discarded. A named locator can carry an important target while its
true silhouette is being developed.

At Deep's 20 mm/degree, one arcminute occupies 0.33 mm. A 10-arcminute cloud
can occupy several millimetres on paper: a generic square or equivalent-area
circle visibly asserts a shape the catalogue does not contain. This is most
damaging for dark lanes and large, irregular H II regions.

## Selection method and limits

The list was assembled from independent visual-observing sources: the
[Astronomical League bright-nebula list](https://www.astroleague.org/files/u3/BrightNebulaRev1.pdf),
its [dark-nebula program](https://www.astroleague.org/dark-nebula-observing-program/)
and [optional-object list](https://www.astroleague.org/files/obsclubs/DarkNebula/DN-Optional.pdf),
the [RASC Deep-Sky Gems](https://www.rasc.ca/sites/default/files/DSG.pdf),
the [Saguaro Astronomy Club's Barnard selection](https://www.saguaroastro.org/the-best-of-barnards-dark-nebulae/),
the [ASSA Top 100](https://assa.saao.ac.za/sections/deep-sky/assa-top-100/)
and southern observing material linked per matrix row. A catalogue or
professional survey was used to establish identity and morphology, not as a
shortcut to visual suitability. One list was never copied wholesale. The AL
bright list itself notes duplicate and mistaken identities, including the
Flame/NGC 2023 confusion, IC 1318 sectors, Sh 2-8/NGC 6334, and IC 5068 in
the Pelican grouping.

CORE means an unmistakable atlas target, including difficult but canonical
visual challenges such as B 33. EXTENDED means a valuable Deep target whose
visual footprint or exact source identity may need more editorial work.
REFERENCE means a valid searchable record that currently lacks sufficient
observing or cartographic value for Deep. A name alone, an imager's nickname,
or membership in an imported catalogue does not promote a target. Empty
`preferred_common_name` cells are intentional. Named complexes are explicitly
typed `region`; a separate target for a distinct observable component is
allowed, but a second alias for the same patch is not.

| Category | CORE | EXTENDED | Editorial emphasis |
| --- | ---: | ---: | --- |
| Emission / H II | 31 | 18 | Includes Carina, Centaurus, Puppis, Ara, Sco, LMC and SMC |
| Reflection | 6 | 9 | NGC/IC first, vdB where it describes a distinct visual patch |
| Dark | 14 | 15 | Named regions, Barnard targets, southern exceptions, selected LDN |
| Supernova remnants | 5 | 3 | Optical filaments, not every radio remnant |
| Mixed / complex | 3 | 2 | Emission, reflection and/or absorption components kept separate |

The small number of Magellanic targets is deliberate: the core includes
Tarantula/30 Dor and SMC N 66; LMC NGC 2014 and NGC 2074 are EXTENDED. The
[Davies–Elliott–Meaburn catalogue](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/232?format=html&tex=true)
contains 358 LMC and 168 SMC H II entries and is the appropriate place to
audit more Magellanic regions, rather than extrapolating from a northern list.

### Primary display identities

Use the identity recognized at the eyepiece. Thus M 42, M 8, M 17, M 20, M 1
and M 78 lead their aliases; NGC/IC normally lead for prominent nebulae;
Sharpless leads for a distinct H II region without a better NGC/IC identity;
vdB leads for a genuinely distinct reflection patch; Barnard leads for a
Barnard dark target. This is a **target-specific hierarchy**. The Rosette,
Veil, Pipe, Pleiades reflection field and Vela SNR require a named-region
identity above their component IDs. Southern Coalsack and Musca's Dark Doodad
cannot be forced into Barnard/LDN nomenclature. LDN 935 is a legitimate
exception. LBN 239 is an unconfirmed EXTENDED exception, not a reason to plot
the whole LBN catalogue.

## Does Deep need LDN as a plotted catalogue?

Counts below are **unique targets in this matrix**, not source-row counts.
"Covered without LDN" means a useful Barnard or other established display
identity exists; it does not mean the target currently has a good contour.

| Dark targets | Total | Barnard primary | Other non-LDN primary | LDN best current identity |
| --- | ---: | ---: | ---: | ---: |
| CORE | 14 | 11 | 2 | **1**: LDN 935 |
| EXTENDED | 15 | 9 | 2 | **4**: LDN 582, 617, 889, 557 |

The two other CORE targets are Coalsack and Dark Doodad; the two other
EXTENDED targets are southern Lupus clouds SL 7 and SL 11. Consequently,
removing standalone LDN plotting **without curated exceptions would lose at
least LDN 935 and four worthwhile optional visual targets**. The first is a
CORE dark lane between North America and Pelican, explicitly in the
[AL required list](https://www.astroleague.org/files/obsclubs/DarkNebula/DN-RequiredObjects.pdf)
and described in [RASC material](https://rasc.ca/sites/default/files/publications/JRASC-2009-10-hr.pdf).
The other four are in the [AL optional list](https://www.astroleague.org/files/obsclubs/DarkNebula/DN-Optional.pdf);
their Deep plotting remains conditional on a trustworthy visual footprint.

LDN also duplicates or subdivides useful Barnard targets: B 142/B 143 form
Barnard's E amid LDN 688/694 ([ASSA cross-identifications](https://assa.saao.ac.za/wp-content/uploads/sites/23/2017/10/concards_v154.pdf));
B 168 overlaps the LDN 1055 dark-lane complex, and B 150 corresponds to LDN
1082. These are examples, not a complete global deduplication count.
[Lynds' catalogue documentation](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/7A?format=html&tex=true)
explicitly permits several opacity patches within one larger cloud and up to
eight Barnard cross-IDs on one LDN row. The current local LDN source records
do not retain populated `Barn` cross-ID values in the normalized objects
inspected here, so deriving an exact **all-catalogue** duplicate count from
this import would be misleading. B 33 is a projection of larger LDN 1630;
LDN 1630 is not an alias for the four-arcminute horse head.

**Dark policy:** choose Option B in *curated* form: Barnard for selected
visually useful patches, selected LDN (especially 935) as actual targets,
explicit named and southern exceptions. Option A alone loses identifiable
targets. Option C alone is too strict while essentially no imported dark
contours exist; it would suppress even Coalsack and B 33. Yet C's demand for
morphology should govern large dark-cloud **shape rendering**. The Southern
[Hartley catalogue](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/191?format=html&tex=true)
contains 1,101 clouds south of −33°, complements Lynds, and has sizes but not
polygons. It is a source for southern identity/aliases, not a blanket Deep
plotting list.

| Dark option | Visual benefit | Main cost | Decision |
| --- | --- | --- | --- |
| A: Barnard, LDN aliases only | Low duplicate density | Misses LDN 935 and selected northern targets; southern exceptions still required | Insufficient alone |
| B: Barnard + selected LDN | Preserves named/observed Lynds exceptions | Requires target-level deduplication and shape work | **Recommended**, with southern named/Hartley/Sandqvist targets |
| C: only LDN with contour | Avoids false morphology | Almost no current dark paths; would hide useful targets | Use as a contour gate, not an identity gate |

## Does Deep need LBN as a plotted catalogue?

These counts exclude SNRs, which have their own selection and morphology
policy. "LBN cross-ID" means a catalogue relation recorded locally or in
the AL cross-referenced list, not a separate physical target.

| Bright target coverage | CORE (40) | EXTENDED (29) |
| --- | ---: | ---: |
| NGC/IC identity, including region components | 40 | 22 |
| Sharpless relation | 5 | 6 |
| vdB relation | 1 | 1 |
| Union of NGC/IC, Sharpless and vdB | **40** | **26** |

The three EXTENDED targets outside that union are RCW 58, Simeis 57
(DWB 111/119) and the conditional LBN 239. These are overlapping family
counts, not additive row counts. OpenNGC supplies local records for all 40
CORE bright targets, although NGC 2070 represents the **cluster within**
30 Doradus and cannot by itself define the Tarantula's whole extent. It
supplies records for 23 of 29 EXTENDED bright targets.

| Emission, reflection, mixed targets | Total | With LBN cross-ID | Confirmed LBN primary needed | Conditional LBN primary |
| --- | ---: | ---: | ---: | ---: |
| CORE | 40 | 27 | **0** | 0 |
| EXTENDED | 29 | 16 | **0** | **1**: LBN 239 |

Most important LBN-linked targets already have an NGC/IC, Sharpless or vdB
identity: NGC 7000/LBN 373, IC 5070/LBN 350/353, IC 434/LBN 953, M 8/LBN
25/26, M 17/LBN 60, NGC 6888/LBN 203 and NGC 7023/LBN 487 are examples.
The LBN catalogue's size is explicitly measured on the photographic plate
where a nebula appeared brightest, and its 1–6 brightness is a photographic
ranking, not a calibrated visual surface brightness. It records a complexity
ID indicating subregions of larger nebulosity; no vector contour is supplied.
See [CDS VII/9](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/9?format=html&tex=true).

Several LBN-only objects in the AL list are photographic brightness class
5–6 (for example LBN 619, 896, 991, 1001 and 1010). They are valid
REFERENCE records but do not by themselves justify large, square Deep symbols.
LBN 239 is class 2 and appears independently in the AL list; its identity,
visual observing value and boundaries need a focused Cygnus review. The
current evidence supports **zero confirmed** LBN-only must-have targets and
**one conditional** extended target in this curated set. Thus choose bright
Option C: LBN normally aliases or indexes; a standalone object appears only
after an object-level observing and footprint review. This is practically
Option A for the current CORE set, but does not prejudge the conditional case.

| Bright option | Visual benefit | Main cost | Decision |
| --- | --- | --- | --- |
| A: NGC/IC + Sharpless + vdB, LBN aliases | Covers all confirmed CORE targets | Can overlook a real Lynds-only field | Adequate for current CORE |
| B: add a broad selected LBN subset | More photographic entries | Many weak, rough shapes and duplicates | No evidence for blanket expansion |
| C: LBN primary only for independently valuable targets | Allows a genuine exception | Needs field verification | **Recommended**; LBN 239 remains conditional |

## Horsehead: four different things on one chart

[ESO describes](https://www.eso.org/public/poland/news/eso0202/) the
Horsehead as **B 33**, a protrusion of the larger **LDN 1630/Orion B** dark
cloud, silhouetted at the edge of the **IC 434** H II emission region. The
bright background's LBN alias is **LBN 953**. These are not four separate
horseheads. B 33 is the visual dark target and receives the Horsehead name;
IC 434 is the bright background target and receives its own emission contour
and label. LDN 1630 is parent-cloud metadata or a separately reviewed broad
region, never B 33's exact contour. LBN 953 is an alias of IC 434. The B 33
silhouette should be drawn as dark foreground against IC 434; using the IC 434
contour for B 33 would invert the physical relation. NGC 2024 is the distinct
**Flame Nebula** nearby. The local processed `IC0434` common-name field
said "Flame Nebula" in the research baseline; the follow-up importer correction
removes it. Current imported outlines
include IC 434 but no B 33 dark contour.

## Overlap audit: physical regions and chart objects

| Field | Distinct visual targets | Avoided duplicate / parent relation |
| --- | --- | --- |
| Orion | M 42, M 43, Running Man, NGC 2023, Flame/NGC 2024, IC 434, B 33, M 78 | LDN 1630 is the large parent of B 33; LBN 953 is IC 434; NGC 2023 is not Flame |
| Cygnus | NGC 7000, Pelican/IC 5070, LDN 935, IC 1318 sectors, Crescent, Veil filaments | IC 5067 belongs within Pelican region; IC 5068 is outside it; Veil's components share one Cygnus Loop parent |
| Sagittarius / Scutum | M 8, M 20, M 17, B 86, B 92, B 93, Scutum star-cloud dark patches | Internal M 8 and M 17 dust lanes are not automatically separate nearby Barnard rows; LBN 26 overlaps M 8 |
| Cepheus | IC 1396, Elephant's Trunk/IC 1396A, NGC 7023, B 150, Cave/Sh 2-155 | Elephant's Trunk is a dark/rim component of IC 1396, not a second whole H II nebula; B 150/LDN 1082 one cloud |
| Carina / Centaurus | NGC 3372, its Keyhole, Gum 31/IC 2599, IC 2944/2948, NGC 3579 | Keyhole is internal absorption; Gum 31 is a separate H II target around the NGC 3324 cluster; Running Chicken is a broad region, not just its tiny OpenNGC extent |
| Vela / Puppis | Vela SNR, NGC 2736 filament, Gum 12, NGC 2467 | Pencil is only one Vela filament; Gum 12 is a much larger ionized shell with debated origin, not an alias for the Vela SNR |
| Taurus / Perseus | Pleiades vdB 20–23 patches, B 5, NGC 1333, M 78 vicinity | Pleiades are several reflection patches; do not enclose the whole cluster in one made-up nebula |
| Sco / Oph | Rho Oph reflection, Pipe with B 59/B 78, B 72, B 68, NGC 6334, NGC 6357 | Pipe is a named multi-cloud system; NGC 6334 and 6357 are separate H II complexes |
| Magellanic Clouds | Tarantula/30 Dor, SMC N 66, LMC NGC 2014, NGC 2074 | NGC 2070 is the bright core/cluster within larger 30 Dor; do not convert every DEM subregion into a Deep object |
| Cygnus Propeller | Simeis 57 with DWB 111 and DWB 119 arms | The named Propeller is not only DWB 111; the two arcs are visual components of a difficult target |

The proposed atlas model is a **region/system with component relationships**:
one named parent may own several independently observable children, each
with its own identity and contour. A region label does not imply one catalogue
row or one polygon. Alias records do not draw new symbols. The printed index
can point a common name to a region and list its child designations. This is
especially important for Veil, Pipe, Rosette, Pelican, Pleiades, Carina and
the Vela remnant. The matrix's `physical_object_or_region` column identifies
where this treatment is required; it is not an instruction to add a new
production domain type now.

## Shape-quality rule

| Grade | Meaning | Deep treatment |
| --- | --- | --- |
| A | An image/survey-derived vector outline tied to the correct physical component | Preferred, after visual-threshold and legal review |
| B | Credible, target-specific major/minor footprint (not merely a generic box) | Acceptable restrained ellipse for a compact target |
| C | Rough catalogue dimensions or equivalent-area estimate | A small labelled fallback only if position is useful; avoid a morphological claim |
| D | Centre with weak/no defensible extent | Index/point locator in Reference; broad cloud normally absent from Deep |

The currently loaded project inventory has 156 outline object IDs / 192
components: 149 bright nebula and seven SNR IDs, **zero dark**. Of the 106
matrix targets, 51 have a direct imported OpenNGC traced outline; a region
may have only partial child contours. [OpenNGC's methodology](https://github.com/mattiaverga/OpenNGC/blob/master/outlines/metodology.txt)
traces three brightness levels by hand against DSS2 Color in Aladin. The
import uses level 2: a useful image isophote, **not** a physical edge or a
calibrated naked-eye/eyepiece visibility threshold. The OpenNGC data are
[CC BY-SA 4.0](https://github.com/mattiaverga/OpenNGC), while the underlying
[DSS use policy](https://gsss.stsci.edu/zzzoldwebsite/dss/data_use.html)
restricts commercial use of DSS images; derivative-polygon redistribution
for a published atlas deserves explicit rights review. The project's five
schematic Cygnus paths are original but also not physical contours.

LDN has centre, area and opacity; its local equivalent circle is **computed**
from area, not supplied as morphology. Barnard supplies a diameter but no
polygon. LBN supplies a photographic major/minor footprint and area, no
contour. Sharpless and southern Gum/RCW designations are useful identity and
rough size sources, not shape files. vdB is useful for reflection identity but
often only centre and weak size; current source positions were supplemented
from SIMBAD. DEM Magellanic regions supply major/minor axes and rough
brightness but no contour. Green's SNR catalogue supplies positions/sizes and
physical classification, not an optical filament path. None of these should
be rendered as an apparently observed rectangle merely because two dimensions
are present. [LDN](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/7A?format=html&tex=true),
[LBN](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/9?format=html&tex=true),
[Hartley](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/191?format=html&tex=true),
[DEM](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/232?format=html&tex=true),
[Green](https://www.mrao.cam.ac.uk/surveys/snrs/).

## Practical contour-source candidates

All raster surveys below are **inputs from which NightSkyAtlas could derive
its own simplified vector paths**, not pre-licensed vector outlines. A
scientific emission threshold, a photographic threshold and a visual
detectability threshold differ. Every derived path needs registration,
background/star removal, smoothing, source attribution, field inspection and
an explicit redistribution decision. Survey FITS generally has celestial WCS
(usually equatorial; some downloadable mosaics are Galactic); output would be
J2000/ICRS RA–Dec vertices tied to the chosen physical target.

| Source | Type, coverage, representation | Rights and feasibility |
| --- | --- | --- |
| [OpenNGC outlines](https://github.com/mattiaverga/OpenNGC/blob/master/outlines/metodology.txt) | Hand-traced DSS2 isophote vectors for selected NGC/IC nebulae; RA/Dec paths | CC BY-SA 4.0 upstream; already imported; audit DSS derivative rights and each object's identity/visual boundary |
| [SHASSA](https://amundsen.swarthmore.edu/SHASSA/) | Southern H-alpha, δ < +15°, 0.8′ pixels, WCS FITS; good large emission shells | [Explicitly non-commercial without permission](https://amundsen.swarthmore.edu/ack.html); unsuitable for unrestricted atlas redistribution until licensed |
| [VTSS](https://www1.phys.vt.edu/~halpha/results.html), [WHAM](https://www.astro.wisc.edu/research/research-areas/galactic-astronomy/wham/wham-sky-survey/) | Northern H-alpha plus all-sky low-resolution intensity maps | WHAM is open for research with attribution; redistribution/commercial terms require confirmation; broad emission only, not small reflection/detail |
| [IGAPS/IPHAS](https://www.star.ucl.ac.uk/IGAPS/data.shtml), [VPHAS+](https://www.hq.eso.org/cms/eso-archive-news/final-imaging-data-release-of-the-vst-public-survey-vphas-plus.html) | High-resolution H-alpha / continuum images of north and south Galactic planes; WCS FITS | Strong candidate for H II and optical SNR filaments in surveyed planes; attribution documented, derived-outline redistribution terms to verify |
| [Pan-STARRS1](https://outerspace.stsci.edu/spaces/PANSTARRS/overview), [SkyMapper DR4](https://skymapper.anu.edu.au/data-release/) | Broadband optical imaging, complementary north/south coverage; WCS frames | Better for reflection and some dark silhouettes than H-alpha; public data and attribution, but check survey-specific publication/redistribution policy before product use |
| [Dobashi optical extinction atlas](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/244A?format=html&tex=true) | Galactic latitude magnitude ≤ 40°; 6′/18′ FITS extinction maps plus cloud IDs; derives from DSS star counts | Promising large dark-lane geometry, too coarse for B 33/B 68; DSS-derived rights require review; not the same as a visual edge |
| [Hartley southern dark clouds](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/191?format=html&tex=true) | 1,101 southern entries, B1950 centre and two sizes, no contours | Essential southern identity/cross-ID supplement; C-grade shape only |
| [DEM Magellanic H II](https://cdsarc.cds.unistra.fr/viz-bin/ReadMe/VII/232?format=html&tex=true), [DeMCELS](https://datalab.noirlab.edu/data/demcels) | DEM IDs/sizes; DeMCELS WCS H-alpha and [S II] images of LMC public DR1 | Best separate MC region audit; DR1 only central 54 deg² LMC; source and commercial redistribution terms to verify |
| [Green SNR catalogue](https://www.mrao.cam.ac.uk/surveys/snrs/), H-alpha surveys above | Identity and rough SNR extent; H-alpha/[S II] offers optical filament geometry | Do not trace radio shells as if visible. Match optical filament to remnant first; survey rights as above |

SkyView's [usage FAQ](https://skyview.gsfc.nasa.gov/current/help/faq.html)
states that generated images usually may be reprinted but names DSS as an
exception; using SkyView as a transport does not remove source rights. No
copyrighted printed-atlas artwork should be scraped or traced.

## Mandatory southern audit

The candidate policy keeps the southern benchmark targets with appropriate
identities: Eta Carinae/NGC 3372 and nearby Gum 31/IC 2599 (with cluster
NGC 3324); IC 2944/2948 around
λ Centauri; NGC 3579, NGC 6188, IC 4628, NGC 6334/6357; Vela SNR with
the Pencil/NGC 2736 component; NGC 2467 in Puppis; Coalsack and Musca's
Dark Doodad; Tarantula/30 Dor in the LMC and N 66/NGC 346 in the SMC.
The [ASSA Top 100](https://assa.saao.ac.za/sections/deep-sky/assa-top-100/)
independently confirms Eta Carinae, Tarantula, Coalsack, Musca dark cloud
and B 228 in Lupus; the [AL list](https://www.astroleague.org/files/u3/BrightNebulaRev1.pdf)
adds many southern H II/RCW targets; [ASSA's IC 2944 visual description](https://assa.saao.ac.za/wp-content/uploads/sites/23/2021/03/AstronomyDelights_Magda_Streicher1.pdf)
establishes the Running Chicken field. Important southern reflection examples
in the matrix are IC 2220, IC 2631, IC 4604 and NGC 6729.
Of the 106 proposed targets, 57 lie south of the celestial equator (32 CORE,
25 EXTENDED); 25 lie below −30° (14 CORE, 11 EXTENDED). These are an audit
measure, not a quota or proof of complete southern coverage.

Removing **standalone LDN** causes no extra southern hole because the Lynds
survey ends near −33°; the south already needs named regions, Barnard where
available, Sandqvist/Lindroos and possibly Hartley/Dobashi. Removing
**standalone LBN** causes no identified southern CORE loss: the key targets
have NGC/IC or other established identities. This does **not** mean present
Deep is southern-complete: RCW 58, DWB 111, B 5 and SL 7/11 in the matrix
are absent from the current normalized imports, and Coalsack/Dark Doodad have
no true contour. The Magellanic DEM audit remains a necessary next research
pass before declaring Reference coverage broad.

## Reference-only class and next editorial gate

REFERENCE contains all correctly typed, well-provenanced catalogue records
needed for lookup, including faint LBN/LDN entries, with their source IDs,
coordinates, approximate dimensions and aliases. Examples that should stay
Reference-only *pending visual evidence* are LBN 619, 896, 991, 1001 and
1010 (AL list brightness class 5–6), and generic LDN opacity patches within
already named Barnard complexes. Reference must mark positional/photographic
footprints honestly; a search hit does not require an atlas symbol. Other
RCW/Gum/DEM/Hartley objects may advance one by one after southern visual and
shape review. No target count was imposed for this class.

The follow-up corrected `IC0434`, `NGC6334`, `Sh2-240`, `NGC3324`, B 33 and
Coalsack source identities, then inspected Deep pilot pages in Orion, Cygnus
and Carina. The remaining editorial gates are: audit cluster-plus-nebula
identities including NGC 346 and M 16; confirm LBN 239 visually; develop
defensible dark contours for Coalsack, Pipe, Dark Doodad, LDN 935 and B 33;
resolve the rights of each adopted survey-derived outline; and extend the Deep
print sample beyond Sagittarius, Vela and the LMC. The first southern page
review and B 33/LDN 935/Coalsack survey-image decisions are recorded in
[`NEBULA_PILOT_REVIEW.md`](NEBULA_PILOT_REVIEW.md). Gum 12
should remain a REFERENCE contextual region
for now: its roughly 36° faint shell is not demonstrated to be a useful
20 mm/degree visual finding chart object, and its physical origin has several
proposed explanations ([ESO review](https://www.eso.org/sci/libraries/historicaldocuments/Scientific_Reports/Scientific_Report_11_A1b.pdf)).
The atlas should then admit **specific physical targets
by stable identity**, and use LDN/LBN as aliases or selected primary IDs,
never switch whole catalogue families on simply to fill gaps.
