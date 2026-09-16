# AI review

NightSky Atlas can optionally review rendered pages with a vision model.
AI is advisory: it proposes whitelisted presentation actions, and the
deterministic validator decides whether they are accepted
(`AGENTS.md` sections 18 and 19). A page is always buildable with AI disabled.

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

## Benchmark

Cases live in `benchmarks/ai_review/cases.yaml` (12 cases: Virgo, Cygnus and a
sparse field, in `raw` and `optimized` modes, at magnitude limits 8.5-9.5).
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

A bounded live run on the raw Virgo page applied 46 accepted actions
(8 rejected by the validator), reducing hard violations from 300 to 191 and
soft cost from 282k to 165k for $0.0020, then stopped with no accepted changes.

## Reproducibility

- Every iteration records both layout hashes, the review result, accepted and
  rejected actions, and usage cost (`write_history`).
- `RecordedReviewer` replays a recorded sequence offline; a replay reproduces
  the same final layout hash (covered by tests).
- AI responses are validated strictly; unknown element references are dropped
  individually and recorded in `last_dropped_elements`.