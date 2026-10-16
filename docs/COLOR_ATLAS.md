# Color Atlas Styles

Color is an opt-in rendering style. The regular `styles/pocket.yaml`,
`styles/standard.yaml` and `styles/deep.yaml` presets remain black and white.
Use the corresponding files in `styles/color/` to build a color atlas.

The selected treatment uses the harmonized DSO palette, five discrete
Milky Way fill levels in Pocket and two levels in Standard and Deep. Medium and
large open-cluster fills are reduced by size: alpha 0.48 for medium symbols and
0.18 for large symbols; small clusters retain their normal fill. Galaxy fill
strength now fades smoothly with rendered major-axis size: full strength through
2.5 mm, reaching alpha 0.18 at 7 mm. The dark galaxy outline remains fully
opaque. Bright nebula, dark nebula and supernova-remnant schematic square fills
also fade smoothly by rendered size: they retain full strength through 3 mm and
reach alpha 0.08 at 16 mm. Their solid or dashed black outlines stay opaque.
Irregular curated nebula contours use their own geometry and are not attenuated.
The Magellanic Clouds use the same light blue family as the Milky Way, with
edition-specific fill strength.

Build Pocket with:

```bash
.venv/bin/nightsky atlas build --edition pocket \
  --style styles/color/pocket.yaml
```

Use `styles/color/standard.yaml` or `styles/color/deep.yaml` for those editions.
The color style changes appearance only; it inherits each edition's geometry,
object selection and label rules.
