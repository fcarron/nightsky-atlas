"""OpenRouter reviewer implementation.

This is the first external :class:`~nightsky_atlas.ai.base.ChartReviewer`.
Nothing outside this module imports OpenRouter-specific structures
(``AGENTS.md`` section 18.1).  The API key is read from the environment; it is
never logged or committed.
"""

from __future__ import annotations

import base64
import json
import mimetypes
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from nightsky_atlas.ai.config import AIConfig
from nightsky_atlas.review.models import ReviewRequest
from nightsky_atlas.review.schema import ReviewResult, validate_review

__all__ = ["OpenRouterError", "OpenRouterReviewer", "ReviewUsage"]

_DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"
_API_KEY_ENV = "OPENROUTER_API_KEY"

_SYSTEM_PROMPT = (
    "You are a meticulous star-atlas cartographer reviewing one printed chart. "
    "Identify only genuine presentation problems. Astronomy and chart geometry "
    "are immutable. You may request only whitelisted layout actions; never give "
    "arbitrary page coordinates. If no action is clearly correct, omit it. "
    "Respond with a single JSON object and nothing else."
)


@dataclass(frozen=True, slots=True)
class ReviewUsage:
    """Usage and cost metadata for one review request."""

    model: str
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    cost_usd: float | None = None
    latency_s: float | None = None


class OpenRouterError(ValueError):
    """Raised when an OpenRouter request or response cannot be used."""


def _data_url(path: str) -> str:
    data = Path(path).read_bytes()
    mime = mimetypes.guess_type(path)[0] or "image/png"
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:{mime};base64,{encoded}"


def _element_lines(request: ReviewRequest) -> str:
    lines: list[str] = []
    for element in request.elements:
        parts = [element.id, element.kind]
        if element.text:
            parts.append(f'text="{element.text}"')
        if element.bounds is not None:
            parts.append(
                f"box=({element.bounds.left_mm:.1f},{element.bounds.top_mm:.1f},"
                f"{element.bounds.width_mm:.1f},{element.bounds.height_mm:.1f})"
            )
        if element.candidates:
            parts.append(f"candidates=[{','.join(element.candidates)}]")
        if element.display_name_variants:
            parts.append(
                f"variants=[{','.join(element.display_name_variants)}]"
            )
        if element.current_candidate is not None:
            parts.append(f"current_candidate={element.current_candidate}")
        if element.allowed_distances:
            parts.append(f"distances=[{','.join(element.allowed_distances)}]")
        if element.fine_adjust_radius_mm is not None:
            parts.append(f"fine_adjust_radius_mm={element.fine_adjust_radius_mm:.1f}")
        if element.constellation_line_conflict:
            parts.append("constellation_line_conflict=true")
        lines.append(" ".join(parts))
    return "\n".join(lines)


def _user_prompt(request: ReviewRequest) -> str:
    return (
        f"Page: {request.page_id}\n"
        f"Permitted actions: {', '.join(request.permitted_actions)}\n"
        "Issue types: ambiguous_association, overlapping_labels, unreadable_label, "
        "wrong_position, missing_label, constellation_line_overlap, "
        "label_too_close_to_symbol, label_cluster_too_dense, poor_visual_balance, "
        "leader_line_needed, display_name_too_long, other\n"
        f"Current diagnostics: {json.dumps(request.diagnostics, sort_keys=True)}\n\n"
        "Elements (id kind [text] [box left,top,width,height in mm] "
        "[candidates=...] [variants=...]):\n"
        f"{_element_lines(request)}\n\n"
        "Action fields: select_candidate uses candidate=N|NE|E|SE|S|SW|W|NW from "
        "the listed candidates. move_label uses preferred_direction plus optional "
        "distance=near|medium|far and max_offset_mm<=3. fine_adjust_label uses "
        "offset_x_mm and offset_y_mm within the listed radius; the engine snaps "
        "this intent to a legal 0.5-mm local placement. show_optional_label and "
        "hide_optional_label take no extra field. request_line_knockout may only "
        "be used for constellation_line_overlap. If no listed option is clearly "
        "better, omit the action.\n\n"
        "Return JSON: {\"page_score\": 0-10, \"issues\": [{\"element_id\": str, "
        "\"issue_type\": str, \"severity\": 1-10, \"action\": {\"type\": str, "
        "\"candidate\": \"N|NE|E|SE|S|SW|W|NW\", \"preferred_direction\": "
        "\"N|NE|E|SE|S|SW|W|NW\", \"distance\": \"near|medium|far\", "
        "\"offset_x_mm\": number, \"offset_y_mm\": number} }]}"
    )


class OpenRouterReviewer:
    """Review charts through OpenRouter's chat completions API."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        base_url: str = _DEFAULT_BASE_URL,
        timeout_s: float = 60.0,
        max_retries: int = 3,
        retry_backoff_s: float = 0.5,
        client: httpx.Client | None = None,
    ) -> None:
        resolved_key = api_key or os.environ.get(_API_KEY_ENV)
        if not resolved_key:
            raise OpenRouterError(f"{_API_KEY_ENV} is not set")
        self.model = model
        self._api_key = resolved_key
        self._endpoint = f"{base_url.rstrip('/')}/chat/completions"
        self._max_retries = max_retries
        self._retry_backoff_s = retry_backoff_s
        self._client = client or httpx.Client(timeout=timeout_s)
        self.last_usage: ReviewUsage | None = None
        self.last_dropped_elements: tuple[str, ...] = ()

    @classmethod
    def from_config(cls, config: AIConfig, **overrides: Any) -> OpenRouterReviewer:
        """Build a reviewer from validated configuration."""
        return cls(
            model=config.reviewer_model,
            timeout_s=config.timeout_s,
            max_retries=config.max_retries,
            **overrides,
        )

    def _messages(self, request: ReviewRequest) -> list[dict[str, Any]]:
        content: list[dict[str, Any]] = [{"type": "text", "text": _user_prompt(request)}]
        for image in request.images:
            content.append(
                {"type": "image_url", "image_url": {"url": _data_url(image)}}
            )
        return [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": content},
        ]

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _post(self, payload: dict[str, Any]) -> httpx.Response:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post(
                    self._endpoint, headers=self._headers(), json=payload
                )
                if response.status_code == 429 or response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"transient status {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                if response.status_code >= 400:
                    raise OpenRouterError(
                        f"OpenRouter returned {response.status_code}: {response.text[:300]}"
                    )
                return response
            except OpenRouterError:
                raise
            except (httpx.TimeoutException, httpx.TransportError, httpx.HTTPStatusError) as exc:
                last_error = exc
                if attempt < self._max_retries:
                    if self._retry_backoff_s:
                        time.sleep(self._retry_backoff_s * (2**attempt))
                    continue
                break
        raise OpenRouterError(f"OpenRouter request failed: {last_error}")

    def review(self, request: ReviewRequest) -> ReviewResult:
        """Send an image review request and return a validated result."""
        known_ids = {element.id for element in request.elements}
        payload = {
            "model": self.model,
            "messages": self._messages(request),
            "response_format": {"type": "json_object"},
            "temperature": 0.0,
        }
        started = time.perf_counter()
        response = self._post(payload)
        latency = time.perf_counter() - started
        data = response.json()

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise OpenRouterError(f"unexpected OpenRouter response shape: {exc}") from exc

        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError) as exc:
            raise OpenRouterError("reviewer did not return valid JSON") from exc

        # Models occasionally invent element IDs.  Reject those issues
        # individually (never the whole review) so a valid review can still be
        # used, and record them for diagnostics.
        self.last_dropped_elements = ()
        if isinstance(parsed, dict) and isinstance(parsed.get("issues"), list):
            issues = parsed["issues"]
            unknown = tuple(
                str(issue.get("element_id"))
                for issue in issues
                if isinstance(issue, dict) and issue.get("element_id") not in known_ids
            )
            if unknown:
                parsed = dict(parsed)
                parsed["issues"] = [
                    issue
                    for issue in issues
                    if isinstance(issue, dict) and issue.get("element_id") in known_ids
                ]
                self.last_dropped_elements = unknown

        result = validate_review(parsed, known_element_ids=known_ids)

        usage = data.get("usage") or {}
        self.last_usage = ReviewUsage(
            model=str(data.get("model", self.model)),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            cost_usd=usage.get("cost"),
            latency_s=latency,
        )
        return result
