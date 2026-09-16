"""AI reviewer configuration.

Model names and providers live in configuration, never in layout logic
(``AGENTS.md`` section 18.2).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

__all__ = ["AIConfig", "AIConfigError", "load_ai_config"]


class AIConfigError(ValueError):
    """Raised when AI configuration is missing, malformed or invalid."""


class AIConfig(BaseModel):
    """Configuration for the optional AI review subsystem."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    enabled: bool = False
    provider: Literal["openrouter"] = "openrouter"
    reviewer_model: str
    fallback_models: list[str] = Field(default_factory=list)
    max_iterations: int = Field(default=4, ge=1)
    max_cost_per_chart_usd: float = Field(default=0.05, gt=0.0)
    min_target_score: float = Field(default=9.0, ge=0.0, le=10.0)
    min_action_severity: int = Field(default=6, ge=1, le=10)
    timeout_s: float = Field(default=60.0, gt=0.0)
    max_retries: int = Field(default=3, ge=0)

    @field_validator("reviewer_model")
    @classmethod
    def _model_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("reviewer_model must not be blank")
        return value


def load_ai_config(path: str | Path) -> AIConfig:
    """Load and validate AI configuration from a YAML file."""
    resolved = Path(path)
    if not resolved.exists():
        raise AIConfigError(f"AI configuration not found: {resolved}")
    try:
        raw = yaml.safe_load(resolved.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise AIConfigError(f"invalid YAML in {resolved}: {exc}") from exc
    if not isinstance(raw, dict):
        raise AIConfigError(f"AI configuration root must be a mapping: {resolved}")
    try:
        return AIConfig.model_validate(raw)
    except ValidationError as exc:
        raise AIConfigError(f"invalid AI configuration {resolved}:\n{exc}") from exc