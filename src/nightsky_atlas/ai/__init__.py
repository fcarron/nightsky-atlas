"""Optional AI review subsystem."""

from __future__ import annotations

from nightsky_atlas.ai.actions import ApplyResult, apply_review_actions
from nightsky_atlas.ai.base import ChartReviewer, MockReviewer
from nightsky_atlas.ai.config import AIConfig, AIConfigError, load_ai_config
from nightsky_atlas.ai.credentials import load_env_file
from nightsky_atlas.ai.loop import (
    AILoopResult,
    IterationRecord,
    optimize_with_ai,
    write_history,
)
from nightsky_atlas.ai.openrouter import OpenRouterError, OpenRouterReviewer, ReviewUsage
from nightsky_atlas.ai.recorded import (
    RecordedReviewer,
    ReviewReplayError,
    write_recorded_reviews,
)

__all__ = [
    "AIConfig",
    "AIConfigError",
    "AILoopResult",
    "ApplyResult",
    "ChartReviewer",
    "IterationRecord",
    "MockReviewer",
    "OpenRouterError",
    "OpenRouterReviewer",
    "RecordedReviewer",
    "ReviewReplayError",
    "ReviewUsage",
    "apply_review_actions",
    "load_ai_config",
    "load_env_file",
    "optimize_with_ai",
    "write_history",
    "write_recorded_reviews",
]