# Product

This document holds the product vision, audience, quality bar and deferred
scope. `AGENTS.md` links here; it is not needed for every coding task.

## Vision

NightSky Atlas generates beautiful, practical paper star charts intended for use
at a telescope rather than as an interactive planetarium.

The desired quality level is inspired by the functional strengths of classic
printed atlases:

- Pocket Sky Atlas: fast field use, low clutter, practical overview;
- Sky Atlas 2000.0: strong balance between detail and usability;
- Uranometria 2000.0: deep coverage suitable for serious deep-sky observing.

NightSky Atlas must not copy the visual design, page layout or copyrighted
creative expression of any existing atlas. These atlases are references for
functional quality and information density only.

The main editions, all built from the same engine:

1. **Pocket** — compact and fast to use at the telescope.
2. **Standard** — the primary general-purpose Dobsonian atlas.
3. **Deep** — high-density deep-sky atlas approaching
   Uranometria-class depth.

Eyepiece (40 mm/°) and Eyepiece Deep (80 mm/°) are experimental configurations;
Eyepiece Deep currently contains test fields rather than a full-sky atlas.

### Edition roles and current main-chart settings

These settings come from the current configurations, not from matching historic
atlases. Publication acceptance still requires printed and telescope review.

- **Pocket:** 5 mm/°; stellar limit mag 7.5;
  selected visually relevant DSO set; large fields; very low label clutter;
  A4/A5-oriented print use.
- **Standard:** 10 mm/°; stellar limit mag 9.0;
  richer DSO content; A4 landscape pages;
  focused on 8–16 inch Dobsonian star-hopping.
- **Deep:** 20 mm/°; stellar limit mag 10.5; much
  larger DSO catalogue; more precise galaxy geometry; large nebula outlines;
  higher chart count; Uranometria-like depth without copying its design.

## Non-goals

NightSky Atlas is not intended to become:

- a planetarium;
- a telescope-control application;
- an observation-session planner;
- a SkySafari replacement;
- a photographic sky simulator;
- a real-time sky renderer;
- a general GIS package;
- a web-first application.

An observation planner is a separate project. The atlas generator may later
expose reusable chart-generation functionality, but architecture must not be
distorted for that hypothetical use case during initial development.

## Primary user and field-use requirements

The primary user is a visual observer using a Dobsonian telescope. The printed
chart therefore optimizes for:

- star-hopping;
- recognition of stellar patterns;
- low-light readability;
- unambiguous object labels;
- useful deep-sky object selection;
- predictable chart overlap;
- rapid navigation between adjacent pages;
- high print quality;
- black-and-white or restrained-color printing;
- robustness when red light is used in the field.

A chart that is mathematically correct but visually cluttered is a failure.
A chart that looks attractive on screen but is awkward during star-hopping is
also a failure.

## Quality bar

- **Level A — technically correct:** correct coordinates and projection, valid
  PDF, no hard layout failures. Necessary but not sufficient.
- **Level B — practically usable:** readable labels, recognizable star
  patterns, useful DSO density, working navigation, usable under red light.
  The minimum for a released atlas.
- **Level C — publication quality:** visually balanced pages, excellent
  typography, very low ambiguity, readable difficult dense fields, consistent
  visual rhythm, minimal or zero manual cleanup. The long-term objective.

## Definition of MVP

Two publication-intent A4 test charts (Virgo/Coma and Cygnus), each with:

- real stars and real OpenNGC DSO data;
- stereographic projection;
- meaningful star magnitude sizing;
- semantic DSO symbols;
- Pango-quality labels;
- deterministic label optimization;
- chart border/grid/basic furniture;
- vector PDF, preview PNG, review PNG, serialized layout JSON;
- hard validation with zero unresolved violations.

AI review is implemented but is **not** required for the basic MVP.
**AI-MVP** is reached when a cheap OpenRouter vision model can review those
pages, return schema-valid issue/action data, and produce some demonstrably
useful automatic label improvements without corrupting geometry.

## First release candidate (Standard)

- complete sky coverage and stable chart numbering;
- final source/provenance documentation;
- complete deterministic build from a clean checkout plus prepared data;
- no hard validation errors;
- successful AI review, or an explicitly recorded skip/override policy per page;
- deterministic replay of accepted AI decisions;
- atlas-wide PDF generation, printed field testing;
- all known high-severity cartographic issues fixed or explicitly accepted.

## Success

The project succeeds when an observer can take the generated atlas to a
Dobsonian telescope and treat it as a real observing tool rather than a software
demo.

The strongest technical success criterion:

> A complete atlas can be regenerated automatically from source data and
> configuration, and the resulting pages require little or no manual label
> cleanup while remaining beautiful, readable and reliable at the telescope.

## Deferred features

Intentionally deferred until the core atlas is proven:

- illustrative constellation artwork (stick figures are implemented);
- colour-rich artistic Milky Way rendering (grayscale contours are implemented);
- eyepiece mirror/orientation modes (separate from the experimental editions);
- interactive web viewer;
- desktop GUI;
- user-specific custom atlas wizard;
- automatic production inclusion of arbitrary external observing lists
  (explicit curated/forced memberships and local coverage audits are implemented);
- finder-circle / telescope-FOV overlays;
- variable-star specialist charts;
- photographic plate overlays;
- automatic translated editions;
- print-on-demand integration.

Agents must not implement these merely because they seem useful.
