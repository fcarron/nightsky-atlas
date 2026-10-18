"""Tests for strict typed configuration loading."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

from nightsky_atlas.atlas.config import (
    ConfigError,
    load_atlas_config,
    load_style_config,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
ATLAS_FIXTURE = REPO_ROOT / "atlas" / "standard.yaml"
STYLE_FIXTURE = REPO_ROOT / "styles" / "standard.yaml"


def write_yaml(path: Path, data: Any) -> Path:
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


def valid_atlas_dict() -> dict[str, Any]:
    return {
        "id": "standard",
        "page": {"width_mm": 297.0, "height_mm": 210.0, "margin_mm": 12.0},
        "charts": [
            {
                "id": "test-virgo",
                "center_ra_deg": 187.5,
                "center_dec_deg": 12.0,
                "width_deg": 20.0,
                "height_deg": 14.0,
            }
        ],
    }


def valid_style_dict() -> dict[str, Any]:
    return {
        "id": "standard",
        "star": {
            "min_diameter_mm": 0.2,
            "max_diameter_mm": 1.6,
            "bright_magnitude": 0.0,
            "faint_magnitude": 10.0,
        },
        "label": {"font_family": "DejaVu Sans", "font_size_pt": 6.0},
    }


def test_shipped_atlas_fixture_loads() -> None:
    config = load_atlas_config(ATLAS_FIXTURE)
    assert config.id == "standard"
    assert config.page.width_mm == pytest.approx(297.0)
    assert config.page.margin_mm == pytest.approx(12.0)
    assert config.stellar_limit_magnitude == pytest.approx(9.0)
    assert [chart.id for chart in config.charts] == [
        "test-virgo",
        "test-cygnus",
        "test-veil",
        "test-sparse",
        "test-orion",
        "test-pole",
    ]
    assert config.charts[0].projection == "stereographic"


def test_shipped_atlas_declares_visible_edition() -> None:
    config = load_atlas_config(ATLAS_FIXTURE)
    edition = config.resolved_edition()
    assert edition.name == "Standard"
    assert edition.code == "S"


def test_missing_edition_falls_back_to_registry(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "atlas.yaml", valid_atlas_dict())
    config = load_atlas_config(path)
    assert config.resolved_edition().name == "Standard"
    assert config.resolved_edition().code == "S"


@pytest.mark.parametrize(
    ("section", "settings", "error"),
    [
        pytest.param(
            "edition", {"name": "Standard", "code": "  "}, "code", id="edition-rejects-blank-code"
        ),
        pytest.param(
            "edition",
            {"name": "Standard", "code": "S", "colour": "blue"},
            "colour",
            id="edition-rejects-unknown-key",
        ),
        pytest.param("tiling", {"strategy": "bands"}, "tiling", id="unknown-top-level-key-fails"),
        pytest.param("page", {"width_mm": -297.0}, None, id="negative-page-dimension-fails"),
        pytest.param(
            "visibility",
            {"integrated_magnitude_limit": 10.0, "reference_magnitude": 11.0},
            None,
            id="visibility-reference-outside-limit-fails",
        ),
        pytest.param(
            "visibility", {"aperture_inches": 12.0}, None, id="visibility-unknown-key-fails"
        ),
    ],
)
def test_invalid_atlas_configuration(
    tmp_path: Path, section: str, settings: dict[str, Any], error: str | None
) -> None:
    data = valid_atlas_dict()
    data.setdefault(section, {}).update(settings)
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError, match=error):
        load_atlas_config(path)


def test_shipped_style_fixture_loads() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.id == "standard"
    assert config.star.min_diameter_mm == pytest.approx(0.28)
    assert config.star.label_magnitude_limit == pytest.approx(5.5)
    assert config.label.font_size_pt == pytest.approx(6.0)
    assert config.constellation.lines.enabled is True
    assert config.constellation.boundaries.enabled is True
    assert config.dso.outline_line_width_mm > 0.0
    assert config.dso.outline_dash_mm > 0.0


@pytest.mark.parametrize(
    "diameter_curve",
    (
        [[0.0, 1.0], [0.0, 0.8]],
        [[0.0, 0.8], [9.0, 1.0]],
        [[0.0, 1.0], [8.0, 0.4]],
    ),
)
def test_star_diameter_curve_is_strictly_validated(
    tmp_path: Path, diameter_curve: list[list[float]]
) -> None:
    data = valid_style_dict()
    data["star"]["diameter_curve"] = diameter_curve
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_style_config(path)
    assert "diameter_curve" in str(excinfo.value)


def test_shipped_style_declares_subdued_furniture() -> None:
    config = load_style_config(STYLE_FIXTURE)
    furniture = config.furniture
    assert furniture.scale_bar.length_deg == pytest.approx(5.0)
    assert furniture.scale_bar.thickness_mm <= 0.2
    # Navigation is deliberately larger than the coordinate labels so it is
    # findable while flipping pages, but mid-grey and never bolder than sky
    # content.
    assert furniture.navigation.font_size_pt > config.grid.label_font_size_pt
    assert furniture.navigation.font_size_pt <= furniture.title_font_size_pt
    assert furniture.navigation.gray >= config.grid.label_gray
    assert not furniture.magnitude_legend.enabled


@pytest.mark.parametrize(
    ("section", "settings", "error"),
    [
        pytest.param(
            "furniture",
            {"magnitude_legend": {"magnitudes": []}},
            "magnitudes",
            id="magnitude-legend-rejects-manual-magnitudes",
        ),
        pytest.param("star", {"colour": "red"}, "colour", id="unknown-nested-key-fails"),
        pytest.param("star", {"max_diameter_mm": 0.1}, None, id="max-diameter-below-min-fails"),
        pytest.param(
            "grid",
            {"ra_step_deg": 2.0, "label_ra_step_deg": 3.0},
            "label_ra_step_deg",
            id="grid-label-step-must-align-with-line-step",
        ),
        pytest.param(
            "label",
            {"dso_labels": {"messier": {"weight": "heavy"}}},
            "weight",
            id="dso-label-invalid-weight-fails",
        ),
        pytest.param(
            "dso",
            {"line_width_mm": 0.3, "bold_line_width_mm": 0.2},
            None,
            id="dso-bold-line-width-must-not-be-thinner",
        ),
        pytest.param(
            "dso",
            {"globular_cluster": {"fallback_diameter_mm": 1.0, "min_diameter_mm": 2.0}},
            None,
            id="dso-extent-min-above-fallback-fails",
        ),
        pytest.param(
            "dso",
            {
                "open_cluster": {
                    "fallback_diameter_mm": 2.0,
                    "min_diameter_mm": 1.4,
                    "max_diameter_mm": 1.0,
                }
            },
            None,
            id="dso-extent-max-below-min-fails",
        ),
        pytest.param(
            "dso",
            {
                "globular_cluster": {
                    "fallback_diameter_mm": 1.5,
                    "min_diameter_mm": 1.2,
                    "radius_mm": 1.0,
                }
            },
            "radius_mm",
            id="dso-extent-unknown-key-fails",
        ),
        pytest.param(
            "label",
            {"dso_labels": {"messier": {"font_size": 8.0}}},
            "font_size",
            id="dso-label-unknown-key-fails",
        ),
        pytest.param(
            "double_stars",
            {"min_component_separation_mm": 0.7, "colour": "red"},
            None,
            id="double-star-style-rejects-unknown-key",
        ),
        pytest.param(
            "double_stars",
            {"unresolved_clearance_mm": -0.1},
            None,
            id="double-star-min-separation-must-be-positive",
        ),
        pytest.param(
            "variable_stars",
            {"enabled": True, "ring_gap_mm": 0.2, "color": "red"},
            None,
            id="variable-star-marker-style-rejects-unknown-keys",
        ),
    ],
)
def test_invalid_style_configuration(
    tmp_path: Path, section: str, settings: dict[str, Any], error: str | None
) -> None:
    data = valid_style_dict()
    data.setdefault(section, {}).update(settings)
    path = write_yaml(tmp_path / "style.yaml", data)
    with pytest.raises(ConfigError, match=error):
        load_style_config(path)


def test_valid_dict_loads(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "atlas.yaml", valid_atlas_dict())
    config = load_atlas_config(path)
    assert config.charts[0].rotation_deg == pytest.approx(0.0)


def test_missing_required_key_fails(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    del data["page"]["height_mm"]
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError) as excinfo:
        load_atlas_config(path)
    assert "height_mm" in str(excinfo.value)


def test_unknown_projection_fails(tmp_path: Path) -> None:
    data = valid_atlas_dict()
    data["charts"][0]["projection"] = "mercator"
    path = write_yaml(tmp_path / "atlas.yaml", data)
    with pytest.raises(ConfigError):
        load_atlas_config(path)


def test_grid_label_step_multiple_is_valid(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["grid"] = {"ra_step_deg": 2.0, "label_ra_step_deg": 10.0}
    path = write_yaml(tmp_path / "style.yaml", data)
    config = load_style_config(path)
    assert config.grid.label_ra_step_deg == pytest.approx(10.0)
    assert config.grid.label_dec_step_deg is None


def test_shipped_atlas_declares_visibility_limits() -> None:
    config = load_atlas_config(ATLAS_FIXTURE)
    limits = config.visibility.to_limits()
    assert limits.integrated_magnitude_limit == pytest.approx(13.5)
    assert limits.surface_brightness_limit == pytest.approx(23.5)
    assert limits.min_axis_arcmin == pytest.approx(1.5)


def test_shipped_style_requests_labels_without_magnitude_cutoff() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.label.dso_label_magnitude_limit is None
    assert config.label.selection.dso_low_density_budget > config.label.selection.low_density_budget


def test_shipped_style_declares_dso_label_hierarchy() -> None:
    config = load_style_config(STYLE_FIXTURE)
    labels = config.label.dso_labels
    assert labels.normal_size_pt == pytest.approx(6.5)
    assert labels.messier.size_factor == pytest.approx(1.0)
    assert labels.messier.weight == "bold"
    assert labels.herschel400.weight == "bold"
    assert labels.normal.weight == "normal"


def test_dso_label_regular_weight_alias(tmp_path: Path) -> None:
    data = valid_style_dict()
    data["label"]["dso_labels"] = {"herschel400": {"weight": "regular"}}
    path = write_yaml(tmp_path / "style.yaml", data)
    config = load_style_config(path)
    assert config.label.dso_labels.herschel400.weight == "normal"


def test_shipped_style_declares_bold_dso_stroke() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.dso.bold_line_width_mm > config.dso.line_width_mm


def test_shipped_style_declares_dso_extent_classes() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.dso.galaxy.use_angular_size is True
    assert config.dso.globular_cluster.use_angular_size is True
    assert config.dso.open_cluster.use_angular_size is True
    assert config.dso.planetary_nebula.use_angular_size is True
    assert (
        config.dso.globular_cluster.min_diameter_mm
        <= config.dso.globular_cluster.fallback_diameter_mm
    )


def test_missing_file_fails(tmp_path: Path) -> None:
    with pytest.raises(ConfigError):
        load_atlas_config(tmp_path / "does-not-exist.yaml")


def test_empty_file_fails(tmp_path: Path) -> None:
    path = tmp_path / "empty.yaml"
    path.write_text("", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_atlas_config(path)


def test_non_mapping_root_fails(tmp_path: Path) -> None:
    path = tmp_path / "list.yaml"
    path.write_text("- a\n- b\n", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_atlas_config(path)


def test_shipped_style_declares_double_star_marker() -> None:
    config = load_style_config(STYLE_FIXTURE)
    assert config.double_stars.enabled is True
    actual_limits = [
        (item.max_sep_arcsec, item.max_secondary_mag) for item in config.double_stars.limits
    ]
    assert actual_limits == [(30.0, 11.5), (120.0, 9.5), (200.0, 9.0)]
    assert config.double_stars.minimum_separation_arcsec == pytest.approx(0.5)
    assert config.double_stars.unresolved_clearance_mm == pytest.approx(0.15)
    assert config.double_stars.marginal_clearance_mm == pytest.approx(0.8)
    assert config.double_stars.marker_length_factor == pytest.approx(1.8)
    assert config.double_stars.min_marker_length_mm == pytest.approx(0.8)
    assert config.double_stars.marker_line_width_mm == pytest.approx(0.15)
    assert config.variable_stars.enabled is True
    assert config.variable_stars.ring_gap_mm == pytest.approx(0.18)
    assert config.variable_stars.line_width_mm == pytest.approx(0.10)


@pytest.mark.parametrize(
    ("edition", "expected"),
    [
        ("pocket", ((30.0, 10.5), (120.0, 8.5), (200.0, 8.5))),
        ("standard", ((30.0, 11.5), (120.0, 9.5), (200.0, 9.0))),
        ("deep", ((30.0, 12.5), (120.0, 10.5), (200.0, 10.0), (300.0, 9.0))),
        ("eyepiece", ((30.0, 12.5), (120.0, 10.5), (200.0, 10.0), (300.0, 9.0))),
        ("eyepiece_deep", ((30.0, 12.5), (120.0, 10.5), (200.0, 10.0), (300.0, 9.0))),
    ],
)
def test_double_star_profile_limits_are_configured(edition: str, expected: tuple) -> None:
    config = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    actual = tuple(
        (limit.max_sep_arcsec, limit.max_secondary_mag) for limit in config.double_stars.limits
    )
    assert actual == expected
    assert config.double_stars.minimum_separation_arcsec == pytest.approx(0.5)


def test_deep_double_star_marker_is_finer_than_pocket() -> None:
    pocket = load_style_config(REPO_ROOT / "styles" / "pocket.yaml").double_stars
    deep = load_style_config(REPO_ROOT / "styles" / "deep.yaml").double_stars
    assert deep.marker_line_width_mm < pocket.marker_line_width_mm


def test_double_star_style_defaults_when_omitted(tmp_path: Path) -> None:
    path = write_yaml(tmp_path / "style.yaml", valid_style_dict())
    config = load_style_config(path)
    assert config.double_stars.enabled is True
    assert config.double_stars.unresolved_clearance_mm == pytest.approx(0.15)
