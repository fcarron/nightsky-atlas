# Deep detail-map candidates from the complete build

Implementation update: all six candidate fields below are now Deep detail
maps, together with M42, NGC 7331/Stephan's Quintet and the Pleiades. The
finished build and label-fallback counts are recorded in [STATE.md](STATE.md).
The table retains the original field-size trials and build evidence.

Date: 2026-09-30. Source: [`build/complete-2026-09-30/deep/draft-report.json`](../build/complete-2026-09-30/deep/draft-report.json), its [manifest](../build/complete-2026-09-30/deep/manifest.json), and the 100-dpi page previews. The build contains 430 main charts, no coverage gaps, and 69 hard layout issues on 19 pages. A dense page is only a prompt to inspect a field; a detail map should solve a local identification problem.

The field sizes below are starting points on A4 landscape. A 3° × 2° field at 90 mm/degree prints 270 × 180 mm; a 2° × 1.5° field at 120 mm/degree prints 240 × 180 mm. Counts in the last column are catalogue objects in the proposed field before Deep's source and label selection, so they are a density estimate, not a promise that every object will be printed or labelled.

| Priority | Region and proposed centre (J2000) | Main charts / build evidence | First detail-map trial | Catalogue objects in field | Reason |
| --- | --- | --- | --- | ---: | --- |
| 1 | **Coma Cluster**, NGC 4874/4889; RA 194.97°, Dec +27.97° | [D120](../build/complete-2026-09-30/deep/charts/deep-120/preview.png): 130 DSOs, 4 hard issues; [D121](../build/complete-2026-09-30/deep/charts/deep-121/preview.png): 90 DSOs, 7 hard issues | **2° × 1.5° at 120 mm/degree**, perhaps with a wider finder field | 141 | The cluster core falls on the D120/D121 seam. A 4° × 3° map would hold about 207 catalogue objects and is unlikely to make all numbers easy to associate. |
| 1 | **Virgo M84/M86 and Markarian chain**; RA 186.75°, Dec +13.0° | [D173](../build/complete-2026-09-30/deep/charts/deep-173/preview.png): 139 DSOs, 1 hard issue; [D174](../build/complete-2026-09-30/deep/charts/deep-174/preview.png): 189 DSOs, 0 hard issues | **3° × 2° at 90 mm/degree** | 74 | The named chain is crowded and split near the D173/D174 edge. The 0-hard count on D174 does not make its dense numbered galaxies easy to read at print size. |
| 1 | **30 Doradus / Tarantula**, LMC; RA 84.68°, Dec −69.10° | [D405](../build/complete-2026-09-30/deep/charts/deep-405/preview.png): 272 DSOs, 149 labels, 9 hard issues | **3° × 2° at 90 mm/degree** | 68 | Many clusters and nebula subregions occupy a small part of D405. A focused card can make their designations usable. |
| 1 | **SMC N 66 / NGC 346**; RA 14.77°, Dec −72.18° | [D415](../build/complete-2026-09-30/deep/charts/deep-415/preview.png): 48 DSOs, 9 hard issues; SMC field is close to its north edge | **4° × 3° at 60 mm/degree** | 43 | A centred field will show the crowded SMC star-forming area with its surroundings instead of placing it at the cap-chart edge. |
| 2 | **LMC central bar**; RA 80.5°, Dec −69.0° | D405 has the highest DSO count in the atlas | **3° × 2° at 90 mm/degree** | 70 | This field is distinct from 30 Dor and needs its own local map if the cluster/nebula labels remain too dense after D405 layout repair. |
| 2 | **Fornax core**, NGC 1399; RA 54.62°, Dec −35.45° | [D328](../build/complete-2026-09-30/deep/charts/deep-328/preview.png): 38 DSOs, 0 hard issues; D329 continues immediately west | **4° × 3° at 60 mm/degree** | 49 | The core group is compact and near the D328/D329 edge. A detail card is useful for identifying individual galaxies, even though the current layout validator reports no hard collision. |

## What the report does not justify yet

- [D096](../build/complete-2026-09-30/deep/charts/deep-096/preview.png) has 89 DSOs but most are spread across the field. Its 95 labels have no hard issues; review specific subgroups before creating a detail card.
- [D318](../build/complete-2026-09-30/deep/charts/deep-318/preview.png) has 60 DSOs around Sagittarius, but the plotted field is readable. Better nebula contours are a more direct improvement there.
- [D398](../build/complete-2026-09-30/deep/charts/deep-398/preview.png) has 75 DSOs in Pavo/Ara, widely distributed and with no hard issues. Defer a Pavo detail map until a compact subgroup proves too hard to identify at print size.
- The nine D405 and nine D415 hard issues are not all density failures. Large enclosing LMC/SMC region symbols are treated as filled collision areas against labels inside them. Correct that region/collision model separately; a new map alone will not clear those diagnostics.

For a detail card used to omit ordinary galaxy numbers on a parent page, use the established Standard/Pocket rule: frame the field and print its code on the parent chart; omit only the numbers of stable object IDs whose labels are actually placed and readable on the detail map. Keep Messier and H400 galaxy labels on the parent. The implemented field sizes were refined after print-size trials; their final geometry is in `atlas/deep.yaml`.
