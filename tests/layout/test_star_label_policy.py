from __future__ import annotations

from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.catalog.models import Provenance, Star
from nightsky_atlas.catalog.star_names import StarName, load_star_names
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.layout.geometry import circle_rect_edge_distance_mm
from nightsky_atlas.layout.labels import build_star_labels
from nightsky_atlas.render.symbols import StarSizeModel
from nightsky_atlas.scene.builder import build_scene

ROOT = Path(__file__).resolve().parents[2]
STYLE = load_style_config(ROOT / "styles/standard.yaml")
POCKET_STYLE = load_style_config(ROOT / "styles/pocket.yaml")
DEEP_STYLE = load_style_config(ROOT / "styles/deep.yaml")
EYEPIECE_STYLE = load_style_config(ROOT / "styles/eyepiece.yaml")
NAMES = load_star_names(ROOT / "data/fixtures/starnames")
CHART = ChartDefinition(
    id="names",
    center_ra_deg=90.0,
    center_dec_deg=0.0,
    width_deg=20.0,
    height_deg=14.0,
)
TRANSFORM = PageTransform(
    chart=CHART, page=PageGeometry(width_mm=297.0, height_mm=210.0, margin_mm=12.0)
)


def labels_for(
    hip: int,
    magnitude: float,
    names: dict[int, StarName] | None = None,
    *,
    style=STYLE,
):
    star = Star(
        id=f"TYC {hip}-1-1",
        ra_deg=90.0,
        dec_deg=0.0,
        magnitude=magnitude,
        hip_id=f"HIP {hip}",
        provenance=Provenance(catalogue="TEST", source_id=str(hip)),
    )
    return build_star_labels(build_scene(CHART, [star]), TRANSFORM, style, names or NAMES)


def label_for(
    hip: int,
    magnitude: float,
    names: dict[int, StarName] | None = None,
    *,
    style=STYLE,
):
    labels = labels_for(hip, magnitude, names, style=style)
    return labels[0] if labels else None


def test_iconic_name_and_systematic_designation_form_one_label() -> None:
    sirius = label_for(32349, -1.46)
    deneb = label_for(102098, 1.25)
    assert sirius is not None and sirius.text == "Sirius α"
    assert deneb is not None and deneb.text == "Deneb α"
    assert NAMES[102098].display_variants(STYLE.label.star_labels, 1.25) == (
        ("Deneb α", "combined"),
    )
    deneb_labels = labels_for(102098, 1.25)
    assert len(deneb_labels) == 1
    assert deneb_labels[0].id == "label:star:TYC 102098-1-1"
    assert deneb_labels[0].text == "Deneb α"
    assert all(candidate.display_text is None for candidate in deneb_labels[0].candidates)
    assert all(candidate.variant_rank == 0 for candidate in deneb_labels[0].candidates)
    assert NAMES[102098].full_bayer_designation == "α Cyg"
    assert NAMES[102098].full_flamsteed_designation == "50 Cyg"


@pytest.mark.parametrize(
    ("hip", "expected"),
    [
        (102098, "Deneb α"),
        (91262, "Vega α"),
        (24436, "Rigel β"),
        (27989, "Betelgeuse α"),
        (21421, "Aldebaran α"),
        (69673, "Arcturus α"),
        (100453, "Sadr γ"),
        (102488, "Aljanah ε"),
    ],
)
def test_standard_core_combined_names(hip: int, expected: str) -> None:
    assert NAMES[hip].canonical_display_variant() == (expected, "combined")


@pytest.mark.parametrize(
    ("hip", "expected"),
    [
        (102098, "Deneb α"),
        (100453, "Sadr γ"),
        (102488, "Aljanah ε"),
        (100345, "Dabih β"),
    ],
)
def test_pocket_keeps_bayer_with_proper_name(hip: int, expected: str) -> None:
    labels = labels_for(hip, 2.0, style=POCKET_STYLE)
    assert len(labels) == 1
    assert labels[0].text == expected


def test_bayer_flamsteed_and_tycho_suppression() -> None:
    assert label_for(999, 3.5, {999: StarName(999, bayer="β", constellation="And")}).text == "β"
    assert (
        label_for(998, 4.5, {998: StarName(998, flamsteed="61", constellation="Cyg")}).text == "61"
    )
    assert label_for(997, 4.0, {997: StarName(997, name="Obscure")}) is None


def test_star_label_candidates_start_at_configured_own_star_gap() -> None:
    magnitude = 3.5
    label = label_for(999, magnitude, {999: StarName(999, bayer="β", constellation="And")})
    assert label is not None
    radius_mm = StarSizeModel.from_style(STYLE.star).radius_mm(magnitude)
    for candidate in label.candidates:
        if candidate.ring == 0:
            assert min(
                circle_rect_edge_distance_mm(TRANSFORM.center_page, radius_mm, glyph)
                for glyph in candidate.glyph_bounds
            ) == pytest.approx(
                STYLE.label.star_clearance.associated.preferred_min_mm,
                abs=0.01,
            )


def test_obscure_name_does_not_suppress_bayer() -> None:
    name = StarName(
        996,
        name="Rare",
        bayer="ε",
        constellation="Lyr",
        curated_name="Rare",
        proper_name_tier="extended",
    )
    assert label_for(996, 4.0, {996: name}).text == "ε"


def test_variable_and_customary_flamsteed() -> None:
    assert label_for(77442, 5.9).text == "R CrB"
    assert label_for(19849, 4.4).text == "ο2"
    assert NAMES[19849].full_flamsteed_designation == "40 Eri"


def test_standard_keeps_bayer_with_canonical_name_without_flamsteed() -> None:
    deneb = NAMES[102098]
    texts = [text for text, _ in deneb.display_variants(STYLE.label.star_labels, 1.25)]
    assert texts == ["Deneb α"]
    assert "50" not in texts
    assert deneb.full_flamsteed_designation == "50 Cyg"


def test_canonical_bayer_precedes_flamsteed_even_with_preference_override() -> None:
    name = StarName(
        992,
        bayer="ο",
        flamsteed="40",
        constellation="Eri",
        preferred_designation="flamsteed",
    )
    assert name.canonical_display_variant() == ("ο", "bayer")


def test_nearby_cross_boundary_bayer_labels_stay_compact_and_distinct() -> None:
    names = {
        1: StarName(1, bayer="δ", constellation="Cyg"),
        2: StarName(2, bayer="δ", constellation="Lac"),
    }
    stars = [
        Star(
            id=f"TYC {number}-1-1",
            ra_deg=ra,
            dec_deg=0.0,
            magnitude=4.0,
            hip_id=f"HIP {number}",
            provenance=Provenance(catalogue="TEST", source_id=str(number)),
        )
        for number, ra in ((1, 90.0), (2, 90.8))
    ]
    labels = build_star_labels(build_scene(CHART, stars), TRANSFORM, STYLE, names)
    assert {label.text for label in labels} == {"δ"}
    assert {label.semantic_key for label in labels} == {"star:bayer:δ Cyg", "star:bayer:δ Lac"}
    far_stars = [
        stars[0],
        Star(
            id="TYC 2-1-1",
            ra_deg=94.0,
            dec_deg=0.0,
            magnitude=4.0,
            hip_id="HIP 2",
            provenance=Provenance(catalogue="TEST", source_id="2"),
        ),
    ]
    far_labels = build_star_labels(build_scene(CHART, far_stars), TRANSFORM, STYLE, names)
    assert {label.text for label in far_labels} == {"δ"}


def test_tier_filter_and_no_catalogue_ids() -> None:
    policy = STYLE.label.star_labels.model_copy(
        update={
            "proper_names": STYLE.label.star_labels.proper_names.model_copy(
                update={"standard": False, "extended": False}
            )
        }
    )
    style = STYLE.model_copy(
        update={"label": STYLE.label.model_copy(update={"star_labels": policy})}
    )
    name = StarName(
        995,
        name="Rare",
        bayer="γ",
        constellation="And",
        curated_name="Rare",
        proper_name_tier="standard",
    )
    assert label_for(995, 4.5, {995: name}, style=style) is None
    for hip in (32349, 102098, 77442, 19849):
        label = label_for(hip, 4.0)
        assert label is not None
        assert not label.text.startswith(("HIP", "HD", "TYC"))


def test_standard_name_and_bayer_are_one_logical_label() -> None:
    name = StarName(
        994,
        name="Less familiar",
        curated_name="Less familiar",
        proper_name_tier="standard",
        bayer="β",
        constellation="And",
    )
    labels = labels_for(994, 2.5, {994: name})
    assert len(labels) == 1
    assert labels[0].text == "Less familiar β"
    assert labels[0].semantic_key == "star:name:Less familiar"


def test_combined_name_policy_cannot_change_canonical_label_text() -> None:
    policy = STYLE.label.star_labels.model_copy(update={"combined_names": True})
    variants = NAMES[102098].display_variants(policy, 1.25)
    disabled = STYLE.label.star_labels.model_copy(update={"combined_names": False})
    assert variants == NAMES[102098].display_variants(disabled, 1.25)


@pytest.mark.parametrize("edition_style", [POCKET_STYLE, STYLE, DEEP_STYLE, EYEPIECE_STYLE])
def test_same_star_uses_identical_canonical_text_across_editions(edition_style) -> None:
    star = Star(
        id="TYC 1-1-1",
        ra_deg=90.0,
        dec_deg=0.0,
        magnitude=3.5,
        hip_id="HIP 999",
        provenance=Provenance(catalogue="TEST", source_id="same-star"),
    )
    name = StarName(
        999,
        curated_name="Almach",
        proper_name_tier="core",
        bayer="γ",
        flamsteed="57",
        constellation="And",
    )
    result = build_star_labels(build_scene(CHART, [star]), TRANSFORM, edition_style, {999: name})
    assert result[0].text == "Almach γ"


def test_flamsteed_only_label_has_no_constellation_suffix() -> None:
    name = StarName(998, flamsteed="61", constellation="Cyg")
    assert label_for(998, 4.5, {998: name}).text == "61"


def test_edition_can_hide_canonical_label_without_changing_its_text() -> None:
    proper_names = STYLE.label.star_labels.proper_names.model_copy(
        update={"standard": False}
    )
    policy = STYLE.label.star_labels.model_copy(update={"proper_names": proper_names})
    style = STYLE.model_copy(
        update={"label": STYLE.label.model_copy(update={"star_labels": policy})}
    )
    name = StarName(
        996,
        curated_name="Rare",
        proper_name_tier="standard",
        bayer="ε",
        constellation="Lyr",
    )
    assert label_for(996, 4.0, {996: name}, style=style) is None


def test_malformed_designations_do_not_render() -> None:
    name = StarName(993, bayer="not-greek", flamsteed="0", constellation="Cyg")
    assert label_for(993, 4.0, {993: name}) is None


def test_same_hip_crossmatch_produces_one_logical_label() -> None:
    stars = [
        Star(
            id=f"TYC 1-{index}-1",
            ra_deg=90.0,
            dec_deg=0.0,
            magnitude=2.0 + index,
            hip_id="HIP 32349",
            provenance=Provenance(catalogue="TEST", source_id=str(index)),
        )
        for index in (1, 2)
    ]
    labels = build_star_labels(build_scene(CHART, stars), TRANSFORM, STYLE, NAMES)
    assert len(labels) == 1
    assert labels[0].text == "Sirius α"
    assert {label.target_id for label in labels} == {"TYC 1-1-1"}
    assert build_star_labels(build_scene(CHART, stars), TRANSFORM, STYLE, NAMES) == labels
