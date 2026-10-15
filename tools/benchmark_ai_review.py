"""Run the optional AI review benchmark independently of the atlas CLI."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from nightsky_atlas.ai.base import MockReviewer
from nightsky_atlas.ai.benchmark import load_cases, run_benchmark
from nightsky_atlas.ai.config import load_ai_config
from nightsky_atlas.ai.credentials import load_env_file
from nightsky_atlas.ai.openrouter import OpenRouterReviewer
from nightsky_atlas.ai.recorded import RecordedReviewer
from nightsky_atlas.atlas.config import ConfigError
from nightsky_atlas.catalog.sample import StarCatalogueError


def main(argv: Sequence[str] | None = None) -> int:
    load_env_file()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--edition", choices=("pocket", "standard", "deep"))
    parser.add_argument("--cases", type=Path, default=Path("benchmarks/ai_review/cases.yaml"))
    parser.add_argument("--atlas", type=Path)
    parser.add_argument("--style", type=Path)
    parser.add_argument(
        "--star-store", type=Path, default=Path("data/processed/stars/tycho2.sqlite")
    )
    parser.add_argument("--stars", type=Path, default=Path("data/fixtures/stars/test_virgo.csv"))
    parser.add_argument("--dsos", type=Path)
    parser.add_argument("--outdir", type=Path, default=Path("benchmarks/ai_review/results"))
    parser.add_argument("--model", help="OpenRouter model to benchmark")
    parser.add_argument("--ai-config", type=Path, default=Path("ai.yaml"))
    parser.add_argument("--recorded", type=Path, help="replay recorded review results")
    args = parser.parse_args(argv)
    edition = args.edition or "standard"
    try:
        cases = load_cases(args.cases)
        if args.recorded is not None:
            reviewer = RecordedReviewer.from_file(args.recorded)
        elif args.model is not None:
            timeout_s, max_retries = 60.0, 3
            if args.ai_config.exists():
                config = load_ai_config(args.ai_config)
                timeout_s, max_retries = config.timeout_s, config.max_retries
            reviewer = OpenRouterReviewer(
                model=args.model, timeout_s=timeout_s, max_retries=max_retries
            )
        else:
            reviewer = MockReviewer()
        report = run_benchmark(
            cases,
            reviewer,
            atlas_path=args.atlas or Path("atlas") / f"{edition}.yaml",
            style_path=args.style or Path("styles") / f"{edition}.yaml",
            star_store=args.star_store,
            stars_csv=args.stars,
            dsos_path=args.dsos,
            outdir=args.outdir,
        )
        out = args.outdir / "report.json"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            json.dumps(report.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        summary = report.to_dict()["summary"]
        print(
            f"cases={summary['cases']} schema={summary['schema_compliance']:.2f} "
            f"detected={summary['detected']}/{summary['known_problems']} "
            f"false_positives={summary['false_positives']} cost=${summary['total_cost_usd']:.4f}"
            f" -> {out}"
        )
        return 0
    except (ConfigError, StarCatalogueError, OSError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
