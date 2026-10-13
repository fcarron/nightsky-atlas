# Pocket DSO candidate review

Re-review of the 32 DeepskyLog targets supplied for at least three observations
with apertures up to 120 mm. Their observation counts remain the primary
curation signal. Identity and representation were checked against the current
local merged DSO catalogue (`data/processed/dso/catalogue.json`, 37,611
records), the UCC import decision report, and the existing Pocket selection.
An alias match was accepted only where the imported records identify a stable
canonical object; nearby coordinates alone were not treated as identity.

This review removes two earlier blanket exclusions: additions are allowed to
flow from Pocket into Standard and Deep, and large angular extents are assessed
individually. UCC `r_50` remains a member-radius statistic, not a visible
diameter. For the three new UCC clusters without a visual extent, the map uses
the existing fallback symbol and does not claim that it outlines the cluster.

## Candidate decisions

| Candidate (≤120 mm observations) | Canonical identity / match | Type; major axis | Pocket before | Decision | Reason |
|---|---|---|---:|---|---|
| Stock 2 (56) | `Stock 2`; VII/92A, UCC exact alias | Open cluster; 60′ | No | `added` | Strongly observed, established cluster, and a useful 1°-scale field marker. |
| B 143 (47) | `B 143`; VII/220A stable designation | Dark nebula; 30′ | Yes | `already_present` | Retained from the earlier curation. Now shown with B 142 as the two Barnard's E components. |
| Kemble 1 (32) | No normalized DSO record | Asterism | No | `unsuitable_representation` | A visual star chain, not a physical cluster; the DSO catalogue has no asterism representation for it. |
| B 168 (27) | `B 168`; VII/220A row, uncertain auxiliary position match (4.30′) | Dark nebula; 10′ | No | `ambiguous_identity` | Identity/position remains unresolved in the imported match record; the stored 10′ extent would also reduce this extended Cocoon-region target to a point-like symbol. |
| Trumpler 2 (27) | `Trumpler 2`; new UCC object, aliases Collinder 29 / OCL 365 | Open cluster; visual extent missing | No | `added` | UCC C3 AA, UTI 0.96, `bad_oc=n`; high-quality cluster and strong observing history. UCC `r_50=15.3′` is not used as a diameter. |
| Stock 23 (26) | `Stock 23`; VII/92A, UCC exact alias | Open cluster; 14′ | No | `added` | Compact, but a reliable identity and very high observing count; its marker and label remain legible at Pocket scale. |
| Cr 69 (25) | `Cr 69`; VII/92A, UCC exact alias | Open cluster; 64′ | No | `added` | Well-sized Lambda Orionis region and high observing count. |
| Cr 70 (25) | `Cr 70`; VII/92A, alias Orion Belt; UCC exact alias | Open cluster; 149′ | No | `added` | The large outline is an intentional representation of the Orion Belt cluster and fits Pocket as a broad orientation region. One validator overlap is the Alnilam member-star label inside its own cluster extent; the rendered label remains readable. |
| B 111 (24) | `B 111`; VII/220A row, uncertain auxiliary position match (18.39′) | Dark nebula; 120′ | No | `ambiguous_identity` | The match uncertainty is substantial, and a 10 mm circular symbol would imply a more secure boundary than the available record supports. |
| Stephenson 1 (22) | `Stephenson 1`; new UCC object, aliases Delta Lyrae / OCL 137 | Open cluster; visual extent missing | No | `added` | UCC C3 AA, UTI 0.98, `bad_oc=n`; high-quality object and strong observing history. `r_50=37.2′` is not treated as visual extent. |
| B 92 (22) | `B 92`; VII/220A row, uncertain auxiliary position match (2.98′) | Dark nebula; 12′ | No | `ambiguous_identity` | The source-match ambiguity remains; it is also one of several small Pipe-region designations without a distinct outline model. |
| B 93 (20) | `B 93`; VII/220A row, uncertain auxiliary position match (0.53′) | Dark nebula; 2′ | No | `ambiguous_identity` | Uncertain source match and too small to show as a meaningful Pocket-scale dark feature; avoid another generic marker in the Pipe group. |
| Cr 65 (19) | `Cr 65`; VII/92A, UCC exact alias | Open cluster; 219′ | No | `added` | The broad region is still useful at Pocket scale: its outline stays within the chart and the major stars remain visible. The old 120′ cutoff alone was not a sufficient reason to omit it. |
| Cr 89 (18) | `Cr 89`; VII/92A alias OCL 473 | Open cluster; 35′ | No | `added` | Reliable, compact cluster; earlier non-selection by Standard is no longer an exclusion reason. |
| NGC 1977 (17) | `NGC1977`; exact OpenNGC identity | Bright nebula; 10.2′ | Yes | `already_present` | Retained from the earlier curation; no duplicate created. |
| B 142 (15) | `B 142`; VII/220A stable designation | Dark nebula; 40′ | No | `added` | Complements B 143 in Barnard's E. Both labels and symbols are distinct on P18. |
| Harvard 20 (16) | `H20`; OpenNGC identity, UCC exact alias Collinder 408 | Open cluster; 5.1′ | Yes | `already_present` | Already selected by the normal Pocket policy; the earlier report's “not in catalogue” result was stale. No duplicate or forced-list entry needed. |
| Stock 1 (14) | `Stock 1`; VII/92A, UCC exact alias | Open cluster; 60′ | No | `added` | Established, well-sized cluster with a strong visual-observing history. |
| Cr 350 (14) | `Cr 350`; VII/92A, UCC exact alias | Open cluster; 45′ | No | `added` | Reliable identity and suitable Pocket-sized extent. |
| Cr 140 (14) | `Cr 140`; VII/92A, UCC exact alias | Open cluster; 42′ | No | `added` | Reliable identity and suitable Pocket-sized extent. |
| Mel 31 (13) | No accepted normalized physical-cluster record; UCC row has `bad_oc=y` | Open-cluster candidate | No | `other` | UCC flags it as a likely non-cluster (`C3=DD`, UTI 0.04); do not select without independent evidence. |
| B 59 (13) | `B 59`; VII/220A row, uncertain auxiliary position match (6.84′) | Dark nebula; 60′ | No | `ambiguous_identity` | The imported identity remains uncertain within the Pipe complex; defer until the match and representation can be checked together. |
| B 103 (13) | `B 103`; VII/220A stable designation | Dark nebula; 4′ | No | `added` | Exact source designation and 13 observations support a useful locator label. It is rendered at the existing minimum symbol size; the printed marker does not imply a 4′-accurate outline. |
| Trumpler 24 (12) | No accepted normalized record; UCC entry held as uncertain against Cr 316 (19.33′) | Open-cluster candidate; no visual extent | No | `ambiguous_identity` | UCC quality is mixed (C3 BC, UTI 0.34); keep it out until its identity relative to Cr 316 is resolved. |
| Cr 316 (12) | `Cr 316`; VII/92A, UCC exact alias | Open cluster; 105′ | No | `added` | A useful broad cluster marker; the earlier 120′ band and Standard-selection restriction do not justify exclusion. Trumpler 24 remains deferred separately. |
| Mel 186 (11) | `Mel 186`; VII/92A, aliases Collinder 359 / UCC Melotte 186 | Open cluster; 240′ | No | `added` | A known, very broad and sparse naked-eye region. Its 4° circle is legible on P19 and provides orientation; large extent alone is not disqualifying. |
| Cr 463 (11) | `Cr 463`; VII/92A, UCC exact alias | Open cluster; 36′ | No | `added` | Reliable identity, suitable extent and observing history. |
| B 78 (10) | `B 78`; VII/220A row, uncertain auxiliary position match (8.15′) | Dark nebula; 180′ | No | `ambiguous_identity` | Pipe-region association remains uncertain; a broad circular outline is not an adequate substitute for the connected cloud shape. |
| Stock 7 (9) | `Stock 7`; new UCC object, aliases MWSC 202 / FoF 2320 | Open cluster; visual extent missing | No | `added` | UCC C3 AA, UTI 0.80, P_dup 0.16, `bad_oc=n`; observed nine times. `r_50=13.9′` is not used as a diameter. |
| Cr 121 (9) | `Cr 121`; VII/92A alias OCL 619 | Open cluster; 49′ | No | `added` | Established and suitably sized; earlier non-selection by Standard is not an exclusion reason. |
| Cr 135 (8) | `Cr 135`; VII/92A, UCC exact alias | Open cluster; 49′ | No | `added` | Established and suitably sized; earlier non-selection by Standard is not an exclusion reason. |
| Cr 367 (8) | `Cr 367`; VII/92A, UCC exact alias | Open cluster; 37′ | No | `added` | Established and suitably sized; earlier non-selection by Standard is not an exclusion reason. |

## Outcome and visual check

- Candidates reviewed: **32**.
- Newly activated in Pocket: **20**.
- Already selected in Pocket and retained: **3** (B 143, NGC 1977, Harvard 20).
- Deferred or rejected: **9** (six uncertain dark-nebula matches, Kemble 1, Mel 31 and Trumpler 24).
- UCC targets newly found and added: **Trumpler 2, Stephenson 1 and Stock 7**. Their UCC member radii were not converted into apparent diameters.
- Pocket selected physical DSO count: **1,113 → 1,133**.
- Standard: **2,999 → 3,017**; Deep: **10,480 → 10,483**. These changes are the intended Pocket-to-later-edition inheritance.

A targeted Pocket proof was built for all 16 charts containing the reviewed
targets (or their immediate overlapping fields), with 200 dpi previews:

- PDF: `build/pocket-candidate-review-20261013/pocket/atlas.pdf`
- Per-chart previews: `build/pocket-candidate-review-20261013/pocket/charts/`
- Manifest and chart-level validation summary:
  `build/pocket-candidate-review-20261013/pocket/manifest.json`

All 20 newly curated targets have visible labels in the proof. The 16-chart
proof recorded one hard validation issue on P23: Alnilam's label overlaps the
Cr 70 cluster extent, which legitimately contains that member star. Visual
inspection shows the label remains readable and the boundary remains clear.
P28 has one unplaced constellation name (Lupus); it is not a DSO-label loss and
the chart has no hard issue. Other reviewed charts in the proof have no hard
issues. The proof is a targeted sample, not a complete Pocket-atlas build.

The curation change is limited to the existing `nightsky_pocket_classics`
observing-list fixture. No catalogue records, coordinates, measured extents,
selection thresholds, symbols or optimizer behavior were changed.
