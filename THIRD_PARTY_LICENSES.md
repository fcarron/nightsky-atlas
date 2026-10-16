# Third-party licenses and attribution

NightSky Atlas source code and generator are MIT-licensed. Original
NightSky-authored cartographic design and layout are licensed under
[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) where identified.
Generated atlas PDFs are offered for free non-commercial download, printing and
sharing, subject to the applicable terms of all included third-party material.
These statements do not relicense third-party content or automatically apply
the MIT License to generated PDFs.

There is no single blanket licence for a generated PDF. OpenNGC-derived
catalogue material remains subject to CC BY-SA 4.0; Tycho-2 and Hipparcos
remain subject to CC BY-NC 3.0 IGO; Gaia-derived contour data are separately
offered under ODbL 1.0. A PDF is a cartographic Produced Work and is not
therefore itself offered under ODbL. Free non-commercial beta distribution is
the intended use, not a legal clearance or permission for commercial use.

For PDF downloads, retain the [distribution notices](docs/ATLAS_DISTRIBUTION.md)
and accompanying source notices/data. The README describes the local package
preparation tool; it does not publish or approve a release.

## Tycho-2 and Hipparcos

The Tycho-2 catalogue and the Hipparcos catalogue are credited to ESA and their
catalogue authors (Høg et al. 2000; ESA 1997). The Hipparcos observing teams
were NDAC, led by Lennart Lindegren, and FAST, led by Jean Kovalevsky. The
repository's source records identify both catalogue datasets as **CC BY-NC
3.0 IGO**; this is a
non-commercial licence. See the [ESA licence text](https://creativecommons.org/licenses/by-nc/3.0/igo/)
and the detailed transformations in `docs/DATA_SOURCES.md`. This condition
applies to those catalogue data, not to the atlas generator's MIT licence.

## OpenNGC

OpenNGC is distributed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
The atlas retains OpenNGC attribution and the source share-alike condition for
the OpenNGC-derived catalogue material. See `docs/DATA_SOURCES.md` for the
imported files and transformations.

## Washington Double Star Catalog

The WDS is maintained by the U.S. Naval Observatory. The repository preserves
the USNO's requested acknowledgement. The current USNO source page does not
state a separate reuse licence; this repository does not rely on an explicit
public-domain grant:

> This research has made use of the Washington Double Star Catalog maintained
> at the U.S. Naval Observatory.

See the [USNO WDS page](https://crf.usno.navy.mil/wds) and
`data/fixtures/double_stars/SOURCE.md`.

## UCAC4 and APASS photometry

UCAC4 is cited as Zacharias et al. (2013), USNO, CDS I/322A. UCAC4 includes
APASS photometry for a subset of records; NightSky uses APASS V where valid and
an empirical fallback described in `docs/FAINT_STAR_SUPPLEMENT.md`. The local
UCAC4 manifest says that no explicit redistribution licence was identified.
The project has not established separate usage terms for the incorporated
APASS photometry. Rights for distributing the faint-star database or derived
products containing these records therefore remain **unresolved**; no blanket
redistribution permission is asserted here.

Pocket PD02 can use this optional faint-star layer. This is an accepted
documentation caveat for the non-commercial beta, not evidence of an explicit
prohibition or a grant of commercial rights. Do not redistribute the raw or
processed UCAC4/APASS catalogue as a standalone dataset without clarifying its
terms.

## Gaia DR3 Magellanic Cloud contours

The LMC/SMC contour GeoJSON is derived from the CDS Gaia DR3 density-map HiPS
product and G-band-flux HiPS product. Their product records identify
ESA/Gaia/DPAC and CDS/CNRS and declare ODbL 1.0. NightSky Atlas treats the
generated GeoJSON as a derivative database and offers that file under ODbL 1.0;
its attribution and reproducible processing are in
`data/third_party/gaia_dr3_magellanic/SOURCE.md` and the adjacent `LICENSE`.
When distributing a PDF that includes these contours, retain the source and
licence notice and make the corresponding derivative GeoJSON available under
ODbL 1.0. The PDF is a Produced Work; this does not place the PDF as a whole
under ODbL. See the [official ODbL 1.0 text](https://opendatacommons.org/licenses/odbl/1-0/),
especially its attribution, share-alike and Produced Work provisions.

The exact product identifiers, release dates, cutouts and processing are
recorded in the Gaia `SOURCE.md`. The original d3-celestial Milky Way contours
remain in use and are separately distributed under BSD-3-Clause as described
below; no Gaia replacement has been made.

## Unified Cluster Catalogue

The UCC Zenodo record and its README request citation of Perren et al. (2023),
but do not state a data licence. The GPL licence of the UCC software is not
treated as a data licence. The beta uses selected UCC-backed object targets in
the atlas rather than distributing the raw catalogue or a complete structured
UCC extract. This remains an accepted caveat: no explicit prohibition has
been identified, but no redistribution permission is asserted. See
`docs/DATA_SOURCES.md` and the local import report. Clarify terms before
redistributing raw or structured derived UCC data.

## Historical VizieR catalogues

VizieR is a CDS catalogue service, not a blanket licence for the historical
catalogues it serves. Their terms vary by source and publication; the project
does not assert a general redistribution licence for the imported Sharpless,
Lynds, Barnard, van den Bergh, Lyngå, Kohoutek, Harris, Hickson, Arp or RC3
records. The exact tables, authors, import fields and source-level terms are
recorded in `docs/DATA_SOURCES.md` and the local source manifests. The CDS
acknowledgement requested for VizieR is:

> This research has made use of the VizieR catalogue access tool, CDS,
> Strasbourg, France (DOI: 10.26093/cds/vizier).

## Stellarium Western (Sky & Telescope) constellation figures

- **Source project:** [Stellarium Sky Cultures](https://github.com/Stellarium/stellarium-skycultures).
- **Sky culture:** Western (Sky & Telescope), `western_SnT`.
- **Source file:** [`western_SnT/index.json`](https://github.com/Stellarium/stellarium-skycultures/blob/014fbb5e59233d133c22f9811af96b67d05a95c9/western_SnT/index.json).
- **Revision:** `014fbb5e59233d133c22f9811af96b67d05a95c9`.
- **License:** [Creative Commons Attribution-ShareAlike 2.0](https://creativecommons.org/licenses/by-sa/2.0/).
- **Attribution:** Paul Krizak and Jonathan E. Piskor; rework by the Stellarium Team. The sky culture represents the Sky & Telescope constellation-figure tradition.
- **Changes:** NightSky normalized HIP polylines, removed zero-length consecutive duplicate references, resolved HIP positions through its own stellar catalog, and retained the source bold/normal/thin hierarchy.
- **NightSky data file:** `data/fixtures/constellations/constellations.lines.json` and its adjacent manifest. This derived figure dataset remains CC BY-SA 2.0.

The upstream author/license statement is in the [pinned sky-culture description](https://github.com/Stellarium/stellarium-skycultures/blob/014fbb5e59233d133c22f9811af96b67d05a95c9/western_SnT/description.md).

## Constellation boundaries

`data/fixtures/constellations/constellations.bounds.json` comes from
[d3-celestial](https://github.com/ofrohn/d3-celestial) by Olaf Frohn and is
BSD-3-Clause licensed; see `data/fixtures/constellations/LICENSE`.

## Star names

The imported star-name and designation data are from d3-celestial by Olaf
Frohn, under BSD-3-Clause; the adjacent `LICENSE` and `SOURCE.md` retain the
notice. The 2022 IAU Catalog of Star Names snapshot used to check the curated
spellings is identified by its source as Creative Commons Attribution. That
snapshot does not specify a version. This attribution does not establish terms
for future IAU catalogue releases; see `data/fixtures/starnames/SOURCE.md`.

## Milky Way outlines

`data/third_party/d3-celestial/mw.json` is distributed by d3-celestial under
BSD-3-Clause; see the adjacent `LICENSE` and `SOURCE.md`. The upstream file
cites José R. Vieira's *Milky Way Outline Catalog*. The project has not
verified a separate licence grant from Vieira for the original outline
catalogue and does not claim that the d3-celestial BSD licence was issued by
Vieira.

## Project-authored outlines and fonts

The schematic nebula outlines in `data/fixtures/outlines/nebulae.json` are
NightSky-authored cartographic artwork and are licensed under CC BY 4.0. This
does not include catalogue coordinates or outlines supplied by other sources.

The bundled Source Sans 3 font is copyright Adobe; bundled Lato Regular and
Bold fonts are copyright Łukasz Dziedzic. Both font families are licensed under
the [SIL Open Font License 1.1](https://openfontlicense.org/); the full notices
are retained beside the font files as `OFL-SourceSans3.txt` and `OFL-Lato.txt`.
The fonts are not covered by the repository's MIT licence.
