# NightSky Atlas — alpha download notices

NightSky Atlas is an experimental, independently generated star atlas for
visual observing. Known label collisions may remain; see the accompanying
`layout-issues.json`. Printed telescope-field evaluation is still pending.
Print on A4 landscape at **100% / actual size**, without fit-to-page scaling.

## Use and sharing

The generator's [MIT licence](../LICENSE) covers its source code. Original
NightSky cartographic design/artwork is [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)
where identified. Neither statement replaces third-party terms. There is no
single blanket licence for all PDF content or for its object index.
The intended alpha use is free, non-commercial download, printing and sharing,
subject to the included source terms. Keep this download's notices and Gaia
contour data with shared copies. For separate PDF hosting, link these notices
and the corresponding contour download prominently beside the PDF.

## Principal sources and adaptations

- **Tycho-2:** Høg et al. (2000), ESA. **Hipparcos:** ESA (1997), NDAC/Lindegren
  and FAST/Kovalevsky teams. [CC BY-NC 3.0 IGO](https://creativecommons.org/licenses/by-nc/3.0/igo/).
  Imported positions and photometry are normalized as documented in
  [DATA_SOURCES.md](DATA_SOURCES.md); this does not grant commercial use.
- **OpenNGC:** Mattia Verga and contributors,
  [source](https://github.com/mattiaverga/OpenNGC),
  [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).
  NightSky converts coordinates/units, resolves aliases and applies documented
  classification corrections; imported level-2 outlines are projected/clipped.
  Adapted catalogue/outline material retains its applicable share-alike terms.
  Own cartography does not make those source terms disappear.
- **Gaia DR3 Magellanic contours:** ESA/Gaia/DPAC; CDS/CNRS/Université de
  Strasbourg; CDS hips2fits. The
  [density product](https://alasky.cds.unistra.fr/ancillary/GaiaDR3/density-map/)
  and [G-flux product](https://alasky.cds.unistra.fr/ancillary/GaiaDR3/G-flux-map/)
  are ODbL 1.0. The derivative
  [contours.geojson](../data/third_party/gaia_dr3_magellanic/contours.geojson)
  is separately available under [ODbL 1.0](https://opendatacommons.org/licenses/odbl/1-0/).
  Its [SOURCE.md](../data/third_party/gaia_dr3_magellanic/SOURCE.md) records exact
  products, filtering, thresholds and reproduction. The PDF is a Produced Work;
  this does not license the whole PDF under ODbL.
- **Milky Way contours:** Olaf Frohn, d3-celestial; original outline catalogue
  José R. Vieira. [Pinned source and transformations](../data/third_party/d3-celestial/SOURCE.md),
  [BSD-3-Clause notice](../data/third_party/d3-celestial/LICENSE).
  The upstream BSD distribution is accepted with the documented original-source
  caveat; no separate personal permission from Vieira is claimed.
- **Constellation figures:** Paul Krizak, Jonathan E. Piskor and Stellarium
  Team, Western (Sky & Telescope),
  [CC BY-SA 2.0](https://creativecommons.org/licenses/by-sa/2.0/).
  HIP polylines are normalized and projected with the NightSky star catalogue.
  [Attribution and pinned source](../data/fixtures/constellations/SOURCE.md).
- **Boundaries/star names:** Olaf Frohn, d3-celestial,
  [BSD notice](../data/fixtures/starnames/LICENSE). IAU spelling-check snapshot
  and its attribution caveat are in the
  [star-name source record](../data/fixtures/starnames/SOURCE.md).
- **Fonts:** Lato, Łukasz Dziedzic; Source Sans 3, Adobe. SIL OFL 1.1;
  complete [Lato](../src/nightsky_atlas/assets/fonts/OFL-Lato.txt) and
  [Source Sans 3](../src/nightsky_atlas/assets/fonts/OFL-SourceSans3.txt) notices
  accompany the embedded fonts.
- **Project schematic nebula artwork:** NightSky Atlas, CC BY 4.0;
  [source and scope](../data/fixtures/outlines/SOURCE.md).
- **Herschel 400 membership:** Wikipedia-derived, CC BY-SA 4.0;
  [source revision and identity adaptations](../data/fixtures/observing_lists/SOURCE.md).

## Scientific catalogues and accepted terms caveats

When used, historical sources include Sharpless (1959), Lynds (1965), Barnard
(1927), van den Bergh (1966), Lyngå (1987; Collinder/Melotte/Stock), Harris
(1996), Hickson (1982), Arp (1966) and de Vaucouleurs et al. (1991).
The exact tables, units and corrections are in [DATA_SOURCES.md](DATA_SOURCES.md).
No general permission to redistribute their original tables is asserted.

This research has made use of the VizieR catalogue access tool, CDS,
Strasbourg, France (DOI: 10.26093/cds/vizier).

The **UCC 260615** is credited to Perren et al. (2023),
[versioned source](https://zenodo.org/records/20705026),
[paper](https://doi.org/10.1093/mnras/stad2826). Its data licence is unspecified;
its software licence is not treated as a data licence.

**WDS:** Mason et al. (2001), U.S. Naval Observatory,
[source](https://crf.usno.navy.mil/wds). This research has made use of the
Washington Double Star Catalog maintained at the U.S. Naval Observatory.
No separate explicit reuse grant was established in the source review.

**UCAC4/APASS**, when used for faint detail-chart stars: Zacharias et al.
(2013), USNO. This publication makes use of data products from the AAVSO
Photometric All Sky Survey (APASS), funded by the Robert Martin Ayers Sciences
Fund and the National Science Foundation (AST-1412587).
[AAVSO data-use guidance](https://aavso.org/data-usage-guidelines-2026-07/).
NightSky uses valid APASS V and a documented empirical fallback; no separate
comprehensive redistribution grant for the stellar database was established.

These UCC, WDS, UCAC4/APASS and historical-catalogue uncertainties are explicitly
accepted caveats of the non-commercial alpha, not evidence of unrestricted
rights or established prohibitions. Raw/processed stellar and DSO databases are
not included in the download. The PDF index remains subject to applicable
source/database terms. See [THIRD_PARTY_LICENSES.md](../THIRD_PARTY_LICENSES.md).
