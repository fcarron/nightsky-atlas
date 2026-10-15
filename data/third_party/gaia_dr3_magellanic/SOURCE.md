# Gaia DR3 Magellanic Cloud contour data

## Source and terms

The contours use two CDS Gaia DR3 HiPS products derived from Gaia table I/355:

- Gaia source density: `CDS/P/DM/I/355/gaiadr3`, processed 2022-06-15.
- Gaia G-band flux: `CDS/P/DM/flux-G/I/355/gaiadr3`, processed 2022-06-16.
- Density HiPS: <https://alasky.cds.unistra.fr/ancillary/GaiaDR3/density-map/>.
- G-flux HiPS: <https://alasky.cds.unistra.fr/ancillary/GaiaDR3/G-flux-map/>.
- HiPS product records: <https://alasky.cds.unistra.fr/MocServer/query?ID=CDS%2FP%2FDM%2FI%2F355%2Fgaiadr3&fmt=html&get=record>
  and <https://alasky.cds.unistra.fr/MocServer/query?ID=CDS%2FP%2FDM%2Fflux-G%2FI%2F355%2Fgaiadr3&fmt=html&get=record>.
- Both HiPS records declare ODbL-1.0, credit CDS/CNRS/Université de Strasbourg,
  and identify Gaia DR3 (ESA/Gaia/DPAC) as the underlying data source.
- Gaia DR3 release citation: <https://doi.org/10.5270/esa-qa4lep3>.
- ODbL text: <https://opendatacommons.org/licenses/odbl/1-0/>.
- The HiPS2FITS service requests acknowledgment of CDS's hips2fits service:
  <https://alasky.cds.unistra.fr/hips-image-services/hips2fits>.

The CDS product metadata, rather than the NightSkyAtlas software license,
governs these source data and their derivatives. Redistribution of the derived
contours must retain attribution and comply with ODbL-1.0, including applicable
share-alike obligations. Obtain legal review before changing the distribution
context or treating the derivative as separately licensed.

## Downloaded cutouts

All cutouts are 500×500 float32 FITS images with TAN projection and ICRS WCS.
The density and G-flux cutouts for each cloud share identical WCS. The G-flux
HiPS metadata reports units of `count.s-1.sr-1`.

| File | Product | Center RA, Dec | Field | Pixel scale | SHA-256 |
|---|---|---|---:|---:|---|
| `LMC-density.fits` | Gaia DR3 density | 80.9°, −69.75° | 20° | 0.0404111672°/pixel | `1df36efbc08470c02b3314fe60aa6c4b2c3445d7b20785fc2ccae396f91aae9f` |
| `LMC-gflux.fits` | Gaia DR3 G-band flux | 80.9°, −69.75° | 20° | 0.0404111672°/pixel | `a01f59b6d71b76b0f354aab4152c8f95687f1d67cdc234b943a04dcf5514fbbb` |
| `SMC-density.fits` | Gaia DR3 density | 13.2°, −72.8° | 12° | 0.0240881164°/pixel | `063989d62a590c7e7cb3fed637858a8e05117bb4d7ddd28ed88742a514d590d3` |
| `SMC-gflux.fits` | Gaia DR3 G-band flux | 13.2°, −72.8° | 12° | 0.0240881164°/pixel | `4f8f17220e27de2c3ee752ff853761ea3a17c436db5d275cc3b5f6f7eedbca8a` |

The request parameters are `format=fits`, `projection=TAN`, `coordsys=icrs`,
`width=500`, `height=500`, with the product ID and field centers above. The
files are cutouts of the source HiPS, not new catalogue measurements. Every
contour vertex is transformed through the source FITS TAN WCS into ICRS RA/Dec.

## Reproduction

From the repository root, with project dependencies installed:

```bash
python scripts/generate_magellanic_cloud_contours.py
python scripts/compare_magellanic_cloud_contours.py
```

The generator writes `contours.geojson` offline. The comparison script writes
Gaia-background comparisons to `build/magellanic-contour-comparison/`. The
generator processes each source independently:

1. Apply `log1p(max(pixel, 0))` to density or G-band flux. The flux product is a
   brightness proxy from Gaia sources; it is not a complete optical image or a
   direct measurement of gas emission.
2. For the SMC, replace the separate foreground cluster NGC 104 / 47 Tucanae
   (6.022333°/−72.081444°) inside 0.40° with a 15-pixel Gaussian-smoothed
   log-map estimate and taper the replacement to zero at 0.75°.
3. Apply a square median filter corresponding to 0.30° (7 pixels for LMC,
   13 pixels for SMC), then a 5-pixel Gaussian filter (12.1 arcmin for LMC,
   7.2 arcmin for SMC). This robust local filtering reduces isolated bright
   source peaks before using the flux map.
4. Fit a robust linear background plane to the four outer 12% corner regions,
   iteratively rejecting residuals beyond 3.5 scaled MAD; subtract it and keep
   positive excess.
5. Normalize each source map independently to the 99.5 percentile of positive
   excess in its central 10% radius. Extract the central connected component,
   fill internal holes and simplify the boundary by at most one pixel.
6. Apply the per-cloud source/threshold recipe below. Each contour is extracted
   independently; nesting is not imposed. The values are cartographic
   thresholds on filtered map excess, not physical galaxy boundaries.

| Cloud | Level 1 outer | Level 2 body | Level 3 inner |
|---|---|---|---|
| LMC | density 25% | density 50% | G flux 55% |
| SMC | density 25% | density 45% | density 65% |

The density map gives a stable broad envelope and irregular body. The filtered
G-flux map traces the LMC's asymmetric bright bar better than another density
threshold. For the SMC, G flux did not provide a convincing improvement to the
central morphology; a lower flux threshold also produced a conspicuous side lobe.
The SMC therefore retains the density-only reference thresholds. A
central-component rule excludes detached source islands. These are Gaia
stellar-population morphology contours, not formal physical boundaries or
direct visual surface-brightness limits.

## Processing details

`contours.geojson` records the source map and threshold per feature, product
identifiers, filtering values, coordinate method and attribution. Its SHA-256 is
`f73679f64435d7b6bc72f0ad1a9ba5e4d2f6885622c0206558ade7b05093a5a7`.
