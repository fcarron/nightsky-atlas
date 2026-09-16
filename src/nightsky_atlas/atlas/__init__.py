"""Atlas edition definitions, tiling and typed configuration loading."""

from __future__ import annotations

from nightsky_atlas.atlas.config import (
    AtlasConfig,
    ChartConfig,
    ConfigError,
    TilingConfig,
    load_atlas_config,
)
from nightsky_atlas.atlas.tiling import (
    CoverageReport,
    TilingSpec,
    coverage_report,
    tile_sky,
    with_neighbours,
)

__all__ = [
    "AtlasConfig",
    "ChartConfig",
    "ConfigError",
    "CoverageReport",
    "TilingConfig",
    "TilingSpec",
    "coverage_report",
    "load_atlas_config",
    "tile_sky",
    "with_neighbours",
]
