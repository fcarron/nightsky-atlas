# Third-party licenses and attribution

NightSky Atlas source code is MIT-licensed. The third-party data below retains
its own license; MIT does not replace it.

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
