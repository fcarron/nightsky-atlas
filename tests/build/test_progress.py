"""Tests for build progress reporting."""

from __future__ import annotations

import io

from nightsky_atlas.build.progress import Progress, null_progress


def test_info_and_detail_levels() -> None:
    stream = io.StringIO()
    progress = Progress(verbose=False, stream=stream)
    progress.info("built")
    progress.detail("hidden")
    output = stream.getvalue()
    assert "built" in output
    assert "hidden" not in output


def test_verbose_emits_detail() -> None:
    stream = io.StringIO()
    progress = Progress(verbose=True, stream=stream)
    progress.detail("stage")
    assert "stage" in stream.getvalue()


def test_step_reports_elapsed_detail() -> None:
    stream = io.StringIO()
    progress = Progress(verbose=True, stream=stream)
    with progress.step("phase", detail=True):
        pass
    assert "phase:" in stream.getvalue()


def test_disabled_reporter_is_silent() -> None:
    stream = io.StringIO()
    progress = Progress(verbose=True, enabled=False, stream=stream)
    progress.info("nope")
    progress.detail("nope")
    assert stream.getvalue() == ""


def test_null_progress_is_silent() -> None:
    progress = null_progress()
    assert progress.enabled is False
