# Project state

Handoff snapshot. The authoritative plan remains `AGENTS.md`.

## Progress

- M0–M14 complete. M15.1–M15.4 complete. M15.5 in progress (alpha built, field test pending).
- M11.4 and M13.3 complete (live AI review through OpenRouter).
- `make check`: Ruff clean, 278 tests passing.

## Frozen Standard geometry (M14.1)

- Page A4 landscape 297 x 210 mm, margin 12 mm (printable 273 x 186 mm).
- Field 27 x 18.5 deg, ~10.05 mm/deg, stereographic, north up / east left.
- Stellar limit magnitude 9.0; deep-sky limit magnitude 12.0 (unknown-magnitude objects kept).
- Tiling: declination bands with 3 deg overlap; coverage sampled at 2 deg; **135 charts**, ids `standard-NNN`, N/S/E/W neighbour references.
- Coverage: 0 gaps at 1 deg sampling, maximum overlap 6.
- Star style: min 0.2 / max 2.4 mm, bright magnitude 0.0 / faint magnitude 9.0.
- Label candidates: 3 concentric rings, ring gap 3.0 mm.

## Data

- Tycho-2 (CDS I/259), **CC-BY-NC-3.0 IGO** (non-commercial). `data/raw/tycho2` + SQLite store, 2,539,913 stars.
- OpenNGC, **CC-BY-SA-4.0**. Processed JSON, 13,372 objects.
- Git-ignored: `data/raw/`, `data/processed/`, `build/`, `.env`, `benchmarks/ai_review/generated|results/`.

## AI review

- Default model `qwen/qwen3.7-flash`; `min_action_severity: 6`; key in git-ignored `.env` (`OPENROUTER_API_KEY`).
- Benchmark: 12 cases, schema compliance 1.00, detected 118/556, 40 false positives, $0.0073.
- Replay via `RecordedReviewer`; the loop records per-iteration layout hashes, review results and cost.

## Alpha artifacts (M15.5)

- `build/standard-alpha/standard/atlas.pdf` (9.2 MB, 135 charts + front matter).
- Per-page `build/standard-alpha/standard/charts/<id>/chart.pdf` and `preview.png`.
- `build/standard-alpha/standard/manifest.json` with per-page diagnostics, limits and data-source manifests.
- 5,061 / 5,622 labels placed.

## Open issues

- 14 hard violations on 6 dense pages: standard-007, 008, 009, 020, 059, 060 (Milky Way / Virgo-Coma).
- Polar pages reuse the standard field and stereographic projection; coverage is complete but distortion near the pole is larger.
- `git_commit` in manifests is null until the repository has commits.

## CLI

`data fetch-stars|import-stars|fetch-openngc|import-openngc`,
`chart render|validate|review|magnitude-scale`,
`atlas tile|coverage|build`,
`benchmark ai-review`.

## Next

1. M15.5 print/field test of representative pages.
2. M16: M16.1 manual overrides, M16.2 atlas-wide issue report, M16.3 preflight, M16.4 `docs/DATA_SOURCES.md`.
3. M17 Pocket, M18 Deep data expansion, M19 extended structures, M20 Deep atlas.
