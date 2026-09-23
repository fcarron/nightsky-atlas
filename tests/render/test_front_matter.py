from pathlib import Path

import pytest

from nightsky_atlas.atlas.config import load_style_config
from nightsky_atlas.render.front_matter import legend_symbols
from nightsky_atlas.render.symbols import compact_star_reference_magnitudes

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("edition", "mm_per_degree", "galaxy_width_mm", "globular_width_mm"),
    (
        ("pocket", 5.0, 2.4, 1.2),
        ("standard", 10.0, 4.0, 2.0),
        ("deep", 20.0, 8.0, 4.0),
    ),
)
def test_legend_uses_edition_dso_geometry(
    edition: str,
    mm_per_degree: float,
    galaxy_width_mm: float,
    globular_width_mm: float,
) -> None:
    style = load_style_config(REPO_ROOT / "styles" / f"{edition}.yaml")
    symbols = {item.name: item for item in legend_symbols(style, mm_per_degree)}

    assert len(symbols) == 8
    assert symbols["Galaxy"].extent.width_mm == pytest.approx(galaxy_width_mm)
    assert symbols["Globular cluster"].extent.width_mm == pytest.approx(globular_width_mm)
    assert symbols["Planetary nebula"].extent.width_mm > mm_per_degree * 6.0 / 60.0
    assert symbols["Other / unknown"].angular_size_arcmin is None


@pytest.mark.parametrize(
    ("limit", "expected"),
    (
        (7.5, (0.0, 2.0, 4.0, 6.0, 7.5)),
        (9.0, (0.0, 2.0, 4.0, 6.0, 8.0, 9.0)),
        (10.0, (0.0, 2.0, 4.0, 6.0, 8.0, 10.0)),
        (11.0, (0.0, 2.0, 4.0, 6.0, 8.0, 10.0, 11.0)),
    ),
)
def test_compact_magnitude_scale_uses_intervals_and_exact_limit(
    limit: float, expected: tuple[float, ...]
) -> None:
    assert compact_star_reference_magnitudes(limit) == expected
