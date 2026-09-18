# AI review

NightSky Atlas can optionally review rendered pages with a vision model.
AI is advisory: it proposes whitelisted presentation actions, and the
deterministic validator decides whether they are accepted. A page is always
buildable with AI disabled. `AGENTS.md` links here; the design spans
architecture sections 17–21.

## Review rendering

AI review needs a machine-friendly representation in addition to the clean
chart. For each chart generate:

1. clean preview PNG;
2. annotated review PNG;
3. compact review metadata JSON.

Annotations should let a vision model identify elements reliably without hiding
the underlying chart: short label IDs, subtle bounding boxes, anchor markers,
numbered high-density regions. Review annotations are never included in final
PDFs.

Support one full-page preview for global balance and automatically generated
high-density crops for fine collision analysis. Crops retain a mapping to page
coordinates and element IDs. Do not implement crop-based review before
full-page structured review works.

- `ReviewRequest` includes only what a reviewer needs: page ID, image(s),
  visible relevant element metadata, permitted actions, current quality
  diagnostics and schema/prompt version. It avoids dumping an enormous full
  layout. Each label element also lists the candidate positions it may
  actually be moved to (and display-name variants when the label has any), and
  only actions the layout model can honour are advertised, so the reviewer is
  never invited to invent a candidate or name variant.
- `ReviewResult` is strictly validated: referenced element IDs, issue types,
  severities, action type and candidate values. Malformed reviews must never
  alter a layout.

## Provider abstraction

```python
class ChartReviewer(Protocol):
    def review(self, request: ReviewRequest) -> ReviewResult:
        ...
```

OpenRouter is the first external implementation. The rest of the application
must not import OpenRouter-specific request structures. Implementations:
`MockReviewer`, `OpenRouterReviewer`, `RecordedReviewer` (deterministic replay of
previously accepted AI responses).

## Structured output only

The AI reviewer must return a validated structured schema. Never parse prose
such as "move the M51 label a bit to the left". Require, for example:

```json
{
  "page_score": 8.8,
  "issues": [
    {
      "element_id": "label:dso:NGC5194",
      "issue_type": "ambiguous_association",
      "severity": 7,
      "action": { "type": "select_candidate", "candidate": "SW" }
    }
  ]
}
```

All responses must pass schema validation before they affect layout.

## Allowed actions

Initial whitelist:

```text
select_candidate
show_optional_label
hide_optional_label
use_leader_line
remove_leader_line
select_display_name_variant
```

Later, tightly bounded offset adjustments may be added. Any unknown action is
rejected. An action is only *advertised* to the reviewer once the layout model
can honour it: `use_leader_line`/`remove_leader_line` stay hidden until labels
carry leader-line state, and `select_display_name_variant` is only offered when
an element lists variants.

After every AI change:

1. apply permitted actions to a copied layout;
2. run deterministic validation;
3. compute cost metrics;
4. reject changes that introduce hard violations;
5. reject a direct move that raises the soft cost (in the optimization loop) —
   a colliding or unavailable `select_candidate` is first repaired to the
   label's cheapest hard-clean candidate;
6. render again only if accepted.

AI is advisory, never authoritative over geometry.

## Optimization loop

```text
layout_0 = deterministic_layout(scene)
validate(layout_0)
render(layout_0)

for iteration in range(max_iterations):
    review = reviewer.review(rendered_page, metadata)
    if review has no significant issues:
        break
    proposal = apply_allowed_actions(layout, review)
    if proposal violates hard constraints:
        reject invalid actions
    if proposal is accepted:
        layout = proposal
        render(layout)
    else:
        stop or request another review depending on policy
```

Termination conditions must include: no significant issues; minimum quality
score reached; no accepted changes; iteration limit; cost budget reached;
repeated layout hash detected. Infinite AI loops are forbidden.

## Cost control

Designed for hundreds of atlas pages. Track per request: provider, model, input
token estimate/actual usage, output tokens, cost, latency, page ID, review
iteration and prompt/schema version. Persist an audit log.

A tiered policy (cheap vision reviewer, escalate uncertain/problematic pages to
a stronger reviewer) is intended later, but must not be implemented until
reviewer benchmarking exists.

## Benchmark suite

Model choice must be empirical. The benchmark set covers difficult sky regions:
Virgo/Coma galaxy fields, Cygnus Milky Way fields, Sagittarius dense fields,
Orion extended-nebula region, M31 region, Pleiades/bright-star labels, a sparse
high-galactic-latitude field and a chart-edge-heavy field.

A fixture contains: rendered page, layout document, known layout problems,
expected acceptable actions, forbidden actions and human quality notes.
Evaluate true issue detection, false positives, valid element references, action
usefulness, schema compliance, repeatability and cost per page. Prefer the
cheapest model meeting quality requirements.

## Default reviewer

| Setting | Value |
| --- | --- |
| Provider | OpenRouter |
| Model | `qwen/qwen3.7-flash` |
| Credential | `OPENROUTER_API_KEY` (env or git-ignored `.env`) |
| Min action severity | 6 |
| Max iterations | 4 |
| Max cost per chart | $0.05 |

The model name is configuration, not code (`ai.yaml`).

## Benchmark results

Cases live in `benchmarks/ai_review/cases.yaml` (12 cases: Virgo, Cygnus and a
sparse field, in `raw` and `optimized` modes, at magnitude limits 8.5–9.5).
Known problems are the hard violations of each layout.

```bash
nightsky benchmark ai-review --model qwen/qwen3.7-flash
nightsky benchmark ai-review --recorded <results.json>   # deterministic replay
```

Measured on 2026-09-16 (12 cases):

| Metric | Value |
| --- | --- |
| Schema compliance | 1.00 |
| Known problems detected | 118 / 556 |
| False positives | 40 (mostly on already-clean optimized pages) |
| Total cost | $0.0073 |
| Wall time | ~6.6 min |

`raw` pages are reviewed usefully (e.g. 41/154 Virgo problems, 8 false
positives); clean `optimized` pages attract a handful of low-severity false
positives, which the severity-6 acceptance rule suppresses.

A bounded live run on the raw Virgo page applied 46 accepted actions (8 rejected
by the validator), reducing hard violations from 300 to 191 and soft cost from
282k to 165k for $0.0020, then stopped with no accepted changes.

## Reproducibility

- Every iteration records both layout hashes, the review result, accepted and
  rejected actions, and usage cost (`write_history`).
- `RecordedReviewer` replays a recorded sequence offline; a replay reproduces
  the same final layout hash (covered by tests).
- AI responses are validated strictly; unknown element references are dropped
  individually and recorded in `last_dropped_elements`.