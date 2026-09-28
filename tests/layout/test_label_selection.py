"""Tests for the deterministic label selection pass."""

from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import LabelSelectionStyle, load_style_config
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Provenance, Star
from nightsky_atlas.catalog.selection import SelectionPolicy
from nightsky_atlas.catalog.star_names import StarName
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.labels import build_dso_labels, build_star_labels
from nightsky_atlas.layout.selection import select_labels
from nightsky_atlas.scene.builder import build_scene

REPO_ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(REPO_ROOT / "styles" / "standard.yaml")

CHART = ChartDefinition(
    id="test", center_ra_deg=187.5, center_dec_deg=12.0, width_deg=20.0, height_deg=14.0
)
PAGE = PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
TRANSFORM = PageTransform(chart=CHART, page=PAGE)


def make_dso(
    object_id: str,
    ra_deg: float,
    dec_deg: float,
    *,
    magnitude: float = 11.0,
    cross_ids: tuple[str, ...] = (),
    object_type: DsoType = DsoType.GALAXY,
) -> DeepSkyObject:
    return DeepSkyObject(
        id=object_id,
        ra_deg=ra_deg,
        dec_deg=dec_deg,
        object_type=object_type,
        provenance=Provenance(catalogue="TEST", source_id=object_id),
        magnitude=magnitude,
        cross_ids=cross_ids,
    )


def clustered_scene(*, object_type: DsoType = DsoType.GALAXY_CLUSTER) -> tuple:
    dsos = [
        make_dso(
            "NGC4486",
            187.5,
            12.0,
            magnitude=9.0,
            cross_ids=("M87",),
            object_type=object_type,
        )
    ]
    for index in range(24):
        dsos.append(
            make_dso(
                f"NGC{9000 + index}",
                187.5 + 0.02 * index,
                12.0 + 0.01 * index,
                object_type=object_type,
            )
        )
    scene = build_scene(CHART, (), dsos)
    return scene, build_dso_labels(scene, TRANSFORM, STYLE)


def test_high_priority_labels_survive_dense_field() -> None:
    scene, labels = clustered_scene()
    selected = select_labels(labels, scene, TRANSFORM, STYLE)
    ids = {label.id for label in selected}
    assert "label:dso:NGC4486" in ids
    assert len(selected) < len(labels)


def test_herschel400_designation_survives_dense_field() -> None:
    objects = [
        make_dso(f"NGC{9000 + index}", 187.5 + 0.02 * index, 12.0 + 0.01 * index,
                 object_type=DsoType.OPEN_CLUSTER)
        for index in range(24)
    ]
    target = objects[12]
    scene = build_scene(
        CHART,
        (),
        objects,
        observing_index={target.id: frozenset({"herschel400"})},
        selection_policy=SelectionPolicy(forced_lists=frozenset({"herschel400"})),
    )
    labels = build_dso_labels(scene, TRANSFORM, STYLE)
    selected = select_labels(labels, scene, TRANSFORM, STYLE)
    target_label = next(label for label in selected if label.target_id == target.id)
    assert target_label.text == "9012"
    assert target_label.mandatory
    assert all(label.mandatory for label in selected if label.id.startswith("label:dso:"))


def test_extreme_dso_density_restores_conservative_local_budget() -> None:
    scene, labels = clustered_scene()
    adaptive = select_labels(labels, scene, TRANSFORM, STYLE)
    relaxed_selection = STYLE.label.selection.model_copy(
        update={"dso_dense_start_neighbors": 1000, "dso_dense_full_neighbors": 1001}
    )
    relaxed_style = STYLE.model_copy(
        update={"label": STYLE.label.model_copy(update={"selection": relaxed_selection})}
    )
    relaxed = select_labels(labels, scene, TRANSFORM, relaxed_style)
    assert len(adaptive) < len(relaxed)
    assert any(label.id == "label:dso:NGC4486" for label in adaptive)


def test_dso_density_transition_must_increase() -> None:
    with pytest.raises(ValueError, match="must exceed"):
        LabelSelectionStyle(dso_dense_start_neighbors=12, dso_dense_full_neighbors=6)


def test_dense_field_thins_ordinary_labels_but_sparse_field_keeps_them() -> None:
    _scene, dense_labels = clustered_scene()
    dense = select_labels(dense_labels, _scene, TRANSFORM, STYLE)

    sparse_dsos = [
        make_dso("NGC1000", 183.0, 8.0, object_type=DsoType.GALAXY_CLUSTER),
        make_dso("NGC2000", 192.0, 16.0, object_type=DsoType.GALAXY_CLUSTER),
    ]
    sparse_scene = build_scene(CHART, (), sparse_dsos)
    sparse_labels = build_dso_labels(sparse_scene, TRANSFORM, STYLE)
    sparse = select_labels(sparse_labels, sparse_scene, TRANSFORM, STYLE)

    assert len(dense) < len(dense_labels) / 2
    assert len(sparse) == len(sparse_labels)


def test_rendered_galaxies_request_labels_and_bypass_density_thinning() -> None:
    scene, labels = clustered_scene(object_type=DsoType.GALAXY)
    selected = select_labels(labels, scene, TRANSFORM, STYLE)

    assert len(selected) == len(labels)


def test_semantic_duplicates_collapse_to_one_label() -> None:
    stars = [
        Star(
            id="TYC 1-1-1",
            ra_deg=187.5,
            dec_deg=12.0,
            magnitude=3.0,
            provenance=Provenance(catalogue="TEST", source_id="a"),
            hip_id="HIP 1",
        ),
        Star(
            id="HIP 2",
            ra_deg=187.6,
            dec_deg=12.1,
            magnitude=5.0,
            provenance=Provenance(catalogue="TEST", source_id="b"),
            hip_id="HIP 2",
        ),
    ]
    names = {
        1: StarName(hip_number=1, name="Ruchba", curated_name="Ruchba", proper_name_tier="core"),
        2: StarName(hip_number=2, name="Ruchba", curated_name="Ruchba", proper_name_tier="core"),
    }
    scene = build_scene(CHART, stars)
    labels = build_star_labels(scene, TRANSFORM, STYLE, names)
    assert len(labels) == 2
    selected = select_labels(labels, scene, TRANSFORM, STYLE)
    assert len(selected) == 1
    assert selected[0].target_id == "TYC 1-1-1"


def test_same_compact_bayer_from_different_constellations_is_not_a_duplicate() -> None:
    stars = [
        Star(
            id=f"TYC {number}-1-1",
            ra_deg=ra,
            dec_deg=12.0,
            magnitude=4.0,
            provenance=Provenance(catalogue="TEST", source_id=str(number)),
            hip_id=f"HIP {number}",
        )
        for number, ra in ((1, 184.0), (2, 191.0))
    ]
    names = {
        1: StarName(1, bayer="δ", constellation="Vir"),
        2: StarName(2, bayer="δ", constellation="Com"),
    }
    scene = build_scene(CHART, stars)
    labels = build_star_labels(scene, TRANSFORM, STYLE, names)
    assert [label.text for label in labels] == ["δ", "δ"]
    assert {label.semantic_key for label in labels} == {"star:bayer:δ Vir", "star:bayer:δ Com"}
    selected = select_labels(labels, scene, TRANSFORM, STYLE)
    assert len(selected) == 2


def test_selection_can_be_disabled() -> None:
    scene, labels = clustered_scene()
    style = STYLE.model_copy(
        update={
            "label": STYLE.label.model_copy(
                update={"selection": LabelSelectionStyle(enabled=False)}
            )
        }
    )
    selected = select_labels(labels, scene, TRANSFORM, style)
    assert [label.id for label in selected] == [label.id for label in labels]
    assert all(label.mandatory for label in selected)


def test_protected_ids_are_always_kept() -> None:
    scene, labels = clustered_scene()
    unprotected = select_labels(labels, scene, TRANSFORM, STYLE)
    unprotected_ids = {label.id for label in unprotected}
    dropped = [label.id for label in labels if label.id not in unprotected_ids]
    assert dropped, "expected the dense field to drop some ordinary labels"
    protected = dropped[0]
    selected = select_labels(labels, scene, TRANSFORM, STYLE, protected_ids=[protected])
    assert protected in {label.id for label in selected}


def test_selection_is_deterministic() -> None:
    scene, labels = clustered_scene()
    first = select_labels(labels, scene, TRANSFORM, STYLE)
    second = select_labels(labels, scene, TRANSFORM, STYLE)
    assert [label.id for label in first] == [label.id for label in second]


def test_selected_star_and_dso_labels_become_mandatory() -> None:
    dso_scene = build_scene(CHART, (), [make_dso("NGC1000", 187.5, 12.0)])
    dso = select_labels(build_dso_labels(dso_scene, TRANSFORM, STYLE), dso_scene, TRANSFORM, STYLE)
    star = Star(
        id="HIP 1",
        ra_deg=187.5,
        dec_deg=12.0,
        magnitude=4.0,
        provenance=Provenance(catalogue="TEST", source_id="star"),
        hip_id="HIP 1",
    )
    star_scene = build_scene(CHART, (star,))
    stars = select_labels(
        build_star_labels(
            star_scene,
            TRANSFORM,
            STYLE,
            {1: StarName(1, bayer="α", constellation="Vir")},
        ),
        star_scene,
        TRANSFORM,
        STYLE,
    )
    assert dso and stars
    assert dso[0].mandatory and stars[0].mandatory
