"""Tests for review request construction."""

from __future__ import annotations

from pathlib import Path

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.labels import build_dso_labels
from nightsky_atlas.review.build import build_review_request
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)


def make_scene():
    star = Star(
        id="TYC 1-8-1",
        ra_deg=187.5,
        dec_deg=12.0,
        magnitude=3.0,
        provenance=Provenance(catalogue="TEST", source_id="1-8-1"),
    )
    faint = Star(
        id="TYC 1-8-2",
        ra_deg=187.6,
        dec_deg=12.1,
        magnitude=11.0,
        provenance=Provenance(catalogue="TEST", source_id="1-8-2"),
    )
    dso = DeepSkyObject(
        id="NGC4486",
        ra_deg=187.5,
        dec_deg=12.0,
        object_type=DsoType.GALAXY,
        provenance=Provenance(catalogue="TEST", source_id="NGC4486"),
        magnitude=8.0,
        cross_ids=("M87",),
    )
    return build_scene(CHART, [star, faint], [dso])


def test_build_review_request() -> None:
    scene = make_scene()
    labels = build_dso_labels(scene, TRANSFORM, STYLE)
    request = build_review_request(
        page_id="standard:test",
        scene=scene,
        labels=labels,
        transform=TRANSFORM,
        diagnostics={"hard_issue_count": 0.0},
        images=("review.png",),
    )
    kinds = {element.kind for element in request.elements}
    assert kinds == {"star", "dso", "label"}
    assert request.page_id == "standard:test"
    assert "select_candidate" in request.permitted_actions
    ids = {element.id for element in request.elements}
    assert "star:TYC 1-8-1" in ids
    assert "star:TYC 1-8-2" not in ids  # faint stars omitted
    assert "dso:NGC4486" in ids
    assert "label:dso:NGC4486" in ids


def test_review_request_is_serializable() -> None:
    scene = make_scene()
    labels = build_dso_labels(scene, TRANSFORM, STYLE)
    request = build_review_request(
        page_id="standard:test",
        scene=scene,
        labels=labels,
        transform=TRANSFORM,
        diagnostics={},
        images=("review.png",),
    )
    payload = request.to_dict()
    assert payload["images"] == ["review.png"]
    assert isinstance(payload["elements"], list)
    assert payload["elements"][0]["kind"] in {"star", "dso", "label"}


def test_label_elements_list_available_candidates() -> None:
    scene = make_scene()
    labels = build_dso_labels(scene, TRANSFORM, STYLE)
    request = build_review_request(
        page_id="standard:test",
        scene=scene,
        labels=labels,
        transform=TRANSFORM,
        diagnostics={},
        images=("review.png",),
    )
    label_elements = [element for element in request.elements if element.kind == "label"]
    assert label_elements
    assert all(element.candidates for element in label_elements)
    # No element carries display-name variants yet, so the reviewer is not
    # invited to request them, and unsupported leader-line actions stay hidden.
    assert "select_display_name_variant" not in request.permitted_actions
    assert "use_leader_line" not in request.permitted_actions
    assert "remove_leader_line" not in request.permitted_actions