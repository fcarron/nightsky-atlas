# Interactive label editor

NightSky Atlas includes an optional local browser editor for reviewing and
correcting one chart at a time. It uses the normal chart scene, placement
candidates, validator, and Cairo renderer. Astronomical positions and symbols
remain read-only. With no editor overrides, normal atlas builds are unchanged.

## Start

Build the normal catalogue inputs first. For example, the production star store
and combined DSO catalogue are expected at `data/processed/stars/tycho2.sqlite`
and `data/processed/dso/catalogue.json`. Then run:

```bash
.venv/bin/nightsky review editor --edition pocket --chart P11
```

Add `--style styles/color/pocket.yaml` for the regular color style.
The editor uses the atlas build helpers for main and detail chart baselines,
including detail-label transfer, per-detail profiles and main-chart star-label
exclusions.

Use `--edition standard` or `--edition deep` for those atlases. Chart codes such
as `P11`, `S004`, and `D087`, or internal chart IDs, are accepted. Detail charts
can be opened by ID or code, for example `PD01`. The default editor workspace
is `build/label-editor/<edition>/<chart-id>/`; a different workspace can be
selected with `--outdir`. Existing overrides can be loaded with `--overrides`
(a YAML file or directory). The interface listens only on `127.0.0.1` by
default. Stop it with Ctrl-C.

If the star store is missing, the command reports its path and asks for a
catalogue build or an explicit `--star-store PATH`. DSO data may be specified
with `--dsos PATH`; otherwise the regular chart input defaults are used.

## Workflow

The editor offers four modes: **As is**, **AI only**, **Human only**, and
**AI + Human**. The mode controls editing actions; it does not change the
baseline layout. Human placement uses page millimetres, supports candidate
selection, free offsets, multi-label selection/movement, locks, leader lines,
undo/redo, and reset. During a drag, the preview reuses the rendered label
pixels, so its typeface and weight match the final chart. A corrected label can
be dragged again without unlocking it; the lock keeps the automatic optimizer
from moving it, while human edits remain available. The selected label's object
is highlighted in orange. Right-click a label for quick leader-line, lock, and
restore actions. Ctrl/Cmd+Z undoes, Ctrl/Cmd+Shift+Z or Ctrl/Cmd+Y redoes, and
the arrow keys nudge the selection (Shift+arrow moves by 1 mm). Releasing a drag
submits the move for full validation and redraw. Zoom and pan affect only the
browser view. Bounding boxes and object anchors can be shown as review aids.
Enabling a leader line locks the label automatically. A manual position change
also locks it so the atlas optimizer preserves it. Users can explicitly unlock
a label, but an unlocked manual position cannot be saved as fixed.

The header distinguishes the deterministic baseline, saved workspace overrides,
and an unsaved local draft. A fresh editor session starts with an empty undo
history; saved overrides are loaded as the session's clean starting state. Each
edit is autosaved to a separate local draft file, never to the atlas override.
If the editor is reopened, a matching draft is recovered and Undo returns to
the saved starting state. Drafts tied to a different chart baseline or saved
override are left untouched and reported. Saving corrections promotes the
current presentation to the workspace override and removes its draft. Accepting
as-is explicitly confirms and removes workspace overrides so the automatic
baseline is what gets recorded. Mode changes and view changes do not modify the
layout.

The region-selection rectangle is drawn in page coordinates. Click selects one
label; Shift-click toggles it in a group. Drag moves the selected label or group
in millimetres. Locked labels can still be deliberately repositioned by hand;
the lock only protects them from automatic optimizer and AI changes. Validation
issues, warnings, density hints, and possible ambiguities remain separate; a
leader-line routing failure is a hard geometry issue, visible before save or
export.

Changes are rendered immediately with the production renderer and checked by
the existing layout validator. Validation issues remain visible while editing;
the user may still choose to accept the unchanged baseline. An explicit
leader line is checked against the production routing algorithm and cannot be
saved or exported if it has no legal route.

AI is optional and only contacted after the user requests a suggestion. Pass an
enabled existing AI configuration with `--ai-config PATH`. The selected,
unlocked labels are the only editable targets; other labels are included as
fixed context. Suggestions are previewed and validated as one combined result,
then explicitly accepted or discarded. A proposal that adds hard issues remains
available for side-by-side review but cannot be accepted. The editor does not call AI during
startup, manual editing, or normal atlas builds. AI requests use the configured
review provider and may send the chart preview and selected chart-label context
to that provider.

“Accept as is” records a review decision without keeping an override file.
“Save corrections” writes a stable-ID YAML override and a separate local
`review.json`. Review records are tied to a fingerprint of the deterministic
baseline; a record is ignored if the chart baseline changes. Existing workspace
overrides load automatically. The review record is editorial metadata and is
not part of catalogue data. If an external `--overrides` file or directory was
loaded, “Accept as is” is disabled by the backend: restart without that source
to review the unchanged baseline. The source override is never deleted by the
editor.

## Apply a saved correction

The editor prints the workspace override path. Apply it through the ordinary
chart build, for example:

```bash
.venv/bin/nightsky chart render \
  --edition pocket --chart pocket-011 --optimize --write-layout \
  --overrides build/label-editor/pocket/pocket-011/overrides.yaml \
  --outdir build/reviewed-pocket
```

The override is processed by the existing layout and PDF pipeline; it does not
patch rendered PDF text. Review metadata remains local in the editor workspace.

## First validation case

The initial practical case is Pocket Virgo: `P11`, `P20`, `P21`, and `PD01`. It is
intended for placement review and regression checks, not as a new set of
chart-specific rules. Preview images, PDFs, and override experiments belong
under ignored `build/` output and should not be committed as source data.
