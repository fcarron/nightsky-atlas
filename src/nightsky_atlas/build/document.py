"""Compose editorial pages, overview maps and PDF navigation for atlas builds."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import cairo

from nightsky_atlas.atlas.config import (
    AtlasConfig,
    DetailChartConfig,
    StyleConfig,
)
from nightsky_atlas.atlas.directory import (
    ChartDirectoryEntry,
    DetailChartDirectoryEntry,
    build_chart_directory,
    build_detail_chart_directory,
)
from nightsky_atlas.atlas.index import AtlasIndex
from nightsky_atlas.atlas.overview import OverviewMap, build_overview
from nightsky_atlas.build.chart import (
    ChartInputs,
)
from nightsky_atlas.build.progress import Progress
from nightsky_atlas.catalog.models import DeepSkyObject, DsoType, Star
from nightsky_atlas.catalog.observing_lists import build_membership_index
from nightsky_atlas.catalog.sample import load_sample_stars
from nightsky_atlas.catalog.selection import select_dso
from nightsky_atlas.catalog.star_names import (
    DEFAULT_FIXTURE_DIR as STAR_NAMES_FIXTURE_DIR,
)
from nightsky_atlas.catalog.star_names import (
    StarName,
)
from nightsky_atlas.catalog.store import QueryBox, StarStore
from nightsky_atlas.chart.models import ChartDefinition, PageGeometry
from nightsky_atlas.chart.page import PageTransform
from nightsky_atlas.chart.presentation import (
    presentation_from_edition,
)
from nightsky_atlas.render.atlas_index import draw_atlas_index_pages
from nightsky_atlas.render.chart_directory import (
    draw_chart_directory_pages,
    draw_detail_chart_directory_pages,
)
from nightsky_atlas.render.front_matter import (
    draw_credits_page,
    draw_field_guide,
    draw_introduction,
)
from nightsky_atlas.render.overview import (
    draw_overview_page,
    draw_overview_spread_page,
)
from nightsky_atlas.render.pdf_navigation import PdfNavigation
from nightsky_atlas.units import mm_to_pt


def _load_overview_stars(
    star_store: str | Path | None,
    stars_csv: str | Path | None,
    magnitude_limit: float,
) -> tuple[Star, ...]:
    """Load the bright-star foreground for the overview pages.

    The overview needs the whole sky, not one chart, so it queries the store
    with a full-sky box instead of the per-chart path.
    """
    if star_store is not None:
        with StarStore.open(star_store) as store:
            stars = store.query_box(
                QueryBox(0.0, 360.0, -90.0, 90.0), magnitude_limit=magnitude_limit
            )
        return tuple(stars)
    if stars_csv is not None:
        return tuple(
            star for star in load_sample_stars(stars_csv) if star.magnitude <= magnitude_limit
        )
    return ()


def _draw_front_matter_pages(
    cr: cairo.Context[cairo.Surface],
    surface: cairo.Surface,
    atlas: AtlasConfig,
    style: StyleConfig,
    main_charts: tuple[ChartDefinition, ...],
    scale_chart: ChartDefinition,
    pdf_navigation: PdfNavigation,
    outline_parent_id: int,
) -> int:
    """Write the two opening pages shared by all editions."""
    page = atlas.page.to_geometry()
    mm_per_degree = PageTransform(
        scale_chart,
        page,
        scale_mm_per_degree=atlas.mm_per_degree,
    ).mm_per_deg
    draw_introduction(cr, atlas, style, main_charts)
    pdf_navigation.mark_page(surface, cr, "introduction", label="Introduction")
    pdf_navigation.add_page_outline(surface, outline_parent_id, "Introduction", "introduction")
    surface.show_page()

    draw_field_guide(cr, atlas, style, len(main_charts), mm_per_degree)
    pdf_navigation.mark_page(surface, cr, "field-guide", label="Field Guide")
    pdf_navigation.add_page_outline(
        surface, outline_parent_id, "Field Guide & Symbol Key", "field-guide"
    )
    surface.show_page()
    return 2


def _draw_build_credits_page(
    cr: cairo.Context[cairo.Surface],
    surface: cairo.Surface,
    atlas: AtlasConfig,
    style: StyleConfig,
    data_sources: list[dict[str, Any]],
    geometry_inputs: dict[str, str | None],
    geometry_catalogues: dict[str, list[str]],
    inputs: ChartInputs,
    star_names: dict[int, StarName],
    pdf_navigation: PdfNavigation,
    outline_parent_id: int,
) -> None:
    """Append credits derived from the data and geometry used in this build."""
    page = atlas.page.to_geometry()
    family = style.typography.sans_family
    selected_dsos = _selected_dsos(inputs)
    left_sections, right_sections = _credits_columns(
        data_sources=data_sources,
        geometry_catalogues=geometry_catalogues,
        used_dso_catalogues=frozenset(
            catalogue
            for dso in selected_dsos
            for catalogue in (
                dso.provenance.catalogue,
                *(record.catalogue_id for record in dso.catalogue_records),
            )
        ),
        star_name_source=geometry_inputs["star_names"] if star_names else None,
        has_iau_star_names=any(name.curated_name for name in star_names.values()),
        has_galaxies=any(dso.object_type == DsoType.GALAXY for dso in selected_dsos),
    )
    draw_credits_page(
        cr,
        page,
        family,
        left_sections,
        right_sections,
        edition=atlas.resolved_edition().name,
        catalogue_data_label="source-specific dates in the build manifest",
    )
    pdf_navigation.mark_page(surface, cr, "credits", label="Data Sources & Credits")
    pdf_navigation.add_page_outline(surface, outline_parent_id, "Data Sources & Credits", "credits")
    surface.show_page()


def _selected_dsos(inputs: ChartInputs) -> tuple[DeepSkyObject, ...]:
    """Return physical targets selected by the edition policy for attribution."""
    membership_index = build_membership_index(inputs.observing_lists, inputs.dsos)
    if inputs.selection_policy is None:
        return inputs.dsos
    selected = []
    for dso in inputs.dsos:
        decision = select_dso(
            dso,
            index=membership_index,
            policy=inputs.selection_policy,
        )
        if decision.visible or decision.forced:
            selected.append(dso)
    return tuple(selected)


def _credits_columns(
    *,
    data_sources: list[dict[str, Any]],
    geometry_catalogues: dict[str, list[str]],
    used_dso_catalogues: frozenset[str],
    star_name_source: str | None,
    has_iau_star_names: bool,
    has_galaxies: bool,
) -> tuple[
    tuple[tuple[str, tuple[str, ...]], ...],
    tuple[tuple[str, tuple[str, ...]], ...],
]:
    """Prepare concise, build-specific source credits from the input manifests."""
    by_kind = {item["kind"]: item for item in data_sources}
    left: list[tuple[str, tuple[str, ...]]] = []
    right: list[tuple[str, tuple[str, ...]]] = []

    star_entries: list[str] = []
    star_source = by_kind.get("stars", {}).get("manifest") or {}
    if star_source.get("catalogue") == "TYC2":
        star_entries.append("Tycho-2 — Høg et al. (2000), ESA; CC BY-NC 3.0 IGO")
        supplement = star_source.get("bright_star_supplement") or {}
        if supplement.get("catalogue") == "HIP":
            star_entries.append(
                "Hipparcos — ESA (1997), Lindegren/Kovalevsky teams; CC BY-NC 3.0 IGO"
            )
    elif star_source.get("source"):
        star_entries.append(f"Stars — {star_source['source']}")
    faint_source = by_kind.get("faint_stars", {}).get("manifest") or {}
    if faint_source.get("catalogue") == "UCAC4":
        star_entries.append("UCAC4 — Zacharias et al. (2013), USNO; APASS V")
    elif faint_source.get("source"):
        star_entries.append(f"Faint-star supplement — {faint_source['source']}")
    if star_entries:
        left.append(("Star catalogues", tuple(star_entries)))

    dso_source = by_kind.get("deep_sky", {}).get("manifest") or {}
    manifest_sources = {
        str(item.get("catalogue_id")): item
        for item in dso_source.get("sources", ())
        if isinstance(item, dict) and item.get("catalogue_id")
    }
    active_ids = set(used_dso_catalogues)
    dso_entries: list[str] = []
    if "OpenNGC" in active_ids:
        dso_entries.append("OpenNGC — Mattia Verga & contributors; CC BY-SA 4.0; adapted")

    group_specs = (
        (
            ("VII/20", "VII/7A", "VII/9", "VII/21", "VII/220A"),
            {
                "VII/20": "Sharpless (1959)",
                "VII/7A": "Lynds LDN (1962)",
                "VII/9": "Lynds LBN (1965)",
                "VII/21": "van den Bergh (1966)",
                "VII/220A": "Barnard (1927)",
            },
            "Nebula catalogues",
        ),
        (
            ("VII/92A:Collinder", "VII/92A:Melotte", "VII/92A:Stock"),
            {
                "VII/92A:Collinder": "Collinder",
                "VII/92A:Melotte": "Melotte",
                "VII/92A:Stock": "Stock",
            },
            "Open clusters — Lyngå (1987)",
        ),
        (
            ("IV/24:AbellPN", "IV/24:CuratedPN"),
            {
                "IV/24:AbellPN": "Kohoutek (2001)",
                "IV/24:CuratedPN": "Kohoutek (2001)",
            },
            "Planetary nebulae",
        ),
        (
            ("VII/202:Palomar", "VII/202:Terzan"),
            {"VII/202:Palomar": "Palomar", "VII/202:Terzan": "Terzan"},
            "Globular clusters — Harris (1996)",
        ),
        (
            ("VII/213", "VII/74A", "VII/155"),
            {
                "VII/213": "Hickson (1982)",
                "VII/74A": "Arp (1966)",
                "VII/155": "de Vaucouleurs et al. (1991)",
            },
            "Galaxy catalogues",
        ),
    )
    grouped_ids: set[str] = set()
    for ids, labels, heading in group_specs:
        grouped_ids.update(ids)
        included = list(dict.fromkeys(labels[item] for item in ids if item in active_ids))
        if included:
            citation = "; ".join(included)
            if " — " in heading:
                citation = f"{', '.join(included)} — {heading.split(' — ')[-1]}"
            dso_entries.append(citation)
    for catalogue_id in sorted(active_ids - grouped_ids - {"OpenNGC"}):
        metadata = manifest_sources.get(catalogue_id, {})
        name = metadata.get("name") or catalogue_id
        if catalogue_id.lower() == "ucc" or "unified cluster" in str(name).lower():
            dso_entries.append(
                "Unified Cluster Catalogue — Perren et al. (2023); data licence not stated"
            )
        else:
            dso_entries.append(str(name))
    if not dso_entries and dso_source.get("source"):
        dso_entries.append(f"Deep-sky catalogue — {dso_source['source']}")
    dso_entries.append(
        "Herschel 400 — Wikipedia (CC BY-SA 4.0); Messier/Caldwell lists supply designations"
    )
    if dso_entries:
        left.append(("Deep-sky catalogues", tuple(dso_entries)))
    if has_galaxies:
        left.append(
            (
                "Galaxy visibility",
                ("Galaxy visibility classes follow a Crumey (2014)-based model.",),
            )
        )

    wds = by_kind.get("double_stars", {}).get("manifest") or {}
    if wds:
        left.append(
            (
                "Double stars",
                (
                    "Washington Double Star Catalog — Mason et al., USNO",
                    "This research has made use of the Washington Double Star Catalog "
                    "maintained at the U.S. Naval Observatory.",
                ),
            )
        )

    line_sources = set(geometry_catalogues.get("constellation_lines", ()))
    boundary_sources = set(geometry_catalogues.get("constellation_boundaries", ()))
    outline_sources = set(geometry_catalogues.get("outlines", ()))
    milky_way_sources = set(geometry_catalogues.get("milky_way", ()))
    magellanic_sources = set(geometry_catalogues.get("magellanic_clouds", ()))
    cartography: list[str] = []
    if "Stellarium Western (Sky & Telescope)" in line_sources:
        cartography.append(
            "Constellation figures — Stellarium Western (Sky & Telescope); "
            "Krizak, Piskor & Stellarium Team; CC BY-SA 2.0"
        )
    elif line_sources:
        cartography.extend(f"Constellation figures — {item}" for item in sorted(line_sources))
    if "d3-celestial" in boundary_sources:
        cartography.append("Constellation boundaries — IAU; d3-celestial, Olaf Frohn; BSD-3-Clause")
    elif boundary_sources:
        cartography.extend(
            f"Constellation boundaries — {item}" for item in sorted(boundary_sources)
        )
    if "nightsky-atlas-authored" in outline_sources:
        cartography.append("Schematic nebula outlines — NightSky Atlas; CC BY 4.0")
    if milky_way_sources:
        cartography.append(
            "Milky Way contours — d3-celestial, Olaf Frohn; source José R. Vieira; BSD-3-Clause"
        )
    if magellanic_sources:
        cartography.append(
            "Magellanic Cloud contours — Gaia DR3 density and G-flux HiPS; "
            "ESA/Gaia/DPAC, CDS/CNRS via hips2fits; ODbL 1.0"
        )
    if cartography:
        right.append(("Constellations & cartography", tuple(cartography)))

    if (
        star_name_source is not None
        and Path(star_name_source).resolve() == STAR_NAMES_FIXTURE_DIR.resolve()
    ):
        name_sources = ["d3-celestial star-name data (Olaf Frohn), BSD-3-Clause"]
        if has_iau_star_names:
            name_sources.append("spellings checked against IAU Catalog of Star Names")
        right.append(("Star names", ("; ".join(name_sources),)))
    elif star_name_source:
        right.append(("Star names", (f"Star-name input — {Path(star_name_source).name}",)))

    service_entries: list[str] = []
    if manifest_sources and active_ids.intersection(manifest_sources):
        source_url = dso_source.get("acknowledgement")
        service_entries.append("VizieR — CDS, Strasbourg, France")
        if source_url:
            service_entries.append(str(source_url))
    if service_entries:
        right.append(("Catalogue services", tuple(service_entries)))

    return tuple(left), tuple(right)


@dataclass(frozen=True, slots=True)
class AtlasPdf:
    """The combined Cairo document owned by the composing parent process."""

    atlas: AtlasConfig
    style: StyleConfig
    surface: cairo.PDFSurface
    context: cairo.Context
    navigation: PdfNavigation
    outline_root: int

    @property
    def page(self) -> PageGeometry:
        return self.atlas.page.to_geometry()


@dataclass(frozen=True, slots=True)
class OpeningPages:
    """Opening-page counts, directory entries and reusable locator maps."""

    front_matter_pages: int
    chart_directory: tuple[ChartDirectoryEntry, ...]
    detail_chart_directory: tuple[DetailChartDirectoryEntry, ...]
    chart_directory_pages: int
    overviews: dict[str, OverviewMap]
    overview_page_info: list[dict[str, Any]]


def open_atlas_pdf(
    path: Path,
    atlas: AtlasConfig,
    style: StyleConfig,
    charts: tuple[ChartDefinition, ...],
    details: tuple[DetailChartConfig, ...],
) -> AtlasPdf:
    """Create the combined PDF and establish all navigable destinations."""
    page = atlas.page.to_geometry()
    edition = atlas.resolved_edition()
    surface = cairo.PDFSurface(str(path), mm_to_pt(page.width_mm), mm_to_pt(page.height_mm))
    context = cairo.Context(surface)
    chart_codes = {
        chart.id: presentation_from_edition(chart, edition).chart_code for chart in charts
    }
    pdf_navigation = PdfNavigation(
        frozenset((*chart_codes.values(), *(detail.code for detail in details))),
        frozenset(
            {
                "introduction",
                "field-guide",
                "overview-north",
                "overview-south",
                "overview-both",
                "credits",
                "index-dso",
                "index-stars",
                "index-constellations",
                "index-cross-references",
                "chart-directory",
                "detail-directory",
            }
        ),
    )
    outline_root = pdf_navigation.add_outline(
        surface,
        cairo.PDF_OUTLINE_ROOT,
        edition.name,
        chart_codes[charts[0].id],
        open_item=True,
    )
    assert outline_root is not None
    return AtlasPdf(atlas, style, surface, context, pdf_navigation, outline_root)


def draw_directories(
    document: AtlasPdf,
    chart_directory: tuple[ChartDirectoryEntry, ...],
    detail_chart_directory: tuple[DetailChartDirectoryEntry, ...],
) -> int:
    """Draw main and detail directories together at the configured position."""
    count = draw_chart_directory_pages(
        document.context,
        document.surface,
        chart_directory,
        document.page,
        document.style,
        document.atlas.resolved_edition(),
        document.navigation,
        outline_parent_id=document.outline_root,
    )
    return count + draw_detail_chart_directory_pages(
        document.context,
        document.surface,
        detail_chart_directory,
        document.page,
        document.style,
        document.atlas.resolved_edition(),
        document.navigation,
        outline_parent_id=document.outline_root,
    )


def write_opening_pages(
    document: AtlasPdf,
    inputs: ChartInputs,
    charts: tuple[ChartDefinition, ...],
    all_charts: tuple[ChartDefinition, ...],
    detail_charts: tuple[DetailChartConfig, ...],
    *,
    star_store: str | Path | None,
    stars_csv: str | Path | None,
    write_front_matter: bool,
    write_overviews: bool,
    progress: Progress,
) -> OpeningPages:
    """Write the introduction, front directories and overviews; retain locator maps."""
    atlas, style = document.atlas, document.style
    context, surface = document.context, document.surface
    pdf_navigation, outline_root = document.navigation, document.outline_root
    page, edition = document.page, atlas.resolved_edition()
    front_matter_pages = 0
    if write_front_matter:
        with progress.step("front matter", detail=True):
            front_matter_pages = _draw_front_matter_pages(
                context,
                surface,
                atlas,
                style,
                tuple(charts),
                charts[0],
                pdf_navigation,
                outline_root,
            )

    chart_directory = ()
    detail_chart_directory = ()
    chart_directory_pages = 0
    if write_front_matter:
        chart_directory = build_chart_directory(charts, edition)
        detail_chart_directory = build_detail_chart_directory(detail_charts, all_charts, edition)
        if atlas.chart_directory_position == "front":
            with progress.step("chart directory", detail=True):
                chart_directory_pages = draw_directories(
                    document, chart_directory, detail_chart_directory
                )

    overviews: dict[str, OverviewMap] = {}
    overview_page_info: list[dict[str, Any]] = []
    write_overview_pages = write_overviews and style.overview.enabled and atlas.tiling is not None
    if write_overview_pages or style.locator.enabled:
        with progress.step("build overview maps"):
            overview_stars: tuple[Star, ...] = ()
            if write_overview_pages and style.overview.show_stars:
                overview_stars = _load_overview_stars(
                    star_store,
                    stars_csv,
                    style.overview.star_limit_magnitude,
                )
            for hemisphere in ("north", "south"):
                overviews[hemisphere] = build_overview(
                    all_charts,
                    hemisphere=hemisphere,
                    constellations=inputs.constellations,
                    edition=edition,
                    bright_stars=overview_stars,
                    equatorial_extension_deg=style.overview.equatorial_extension_deg,
                )
    if write_overview_pages:
        with progress.step("overview pages", detail=True):
            if style.overview.hemispheres_per_page == 2:
                draw_overview_spread_page(
                    context,
                    overviews["north"],
                    overviews["south"],
                    page,
                    style,
                    pdf_navigation,
                )
                overview_outline = pdf_navigation.add_page_outline(
                    surface, outline_root, "Sky Overviews", "overview-both", open_item=False
                )
                assert overview_outline is not None
                pdf_navigation.mark_page(surface, context, "overview-both", label="Sky Overviews")
                pdf_navigation.add_page_outline(
                    surface, overview_outline, "Northern Sky", "overview-both"
                )
                pdf_navigation.add_page_outline(
                    surface, overview_outline, "Southern Sky", "overview-both"
                )
                surface.show_page()
                overview_page_info.append(
                    {
                        "hemisphere": "both",
                        "title": "Northern and southern sky",
                        "chart_count": overviews["north"].chart_count
                        + overviews["south"].chart_count,
                        "star_count": len(overviews["north"].stars) + len(overviews["south"].stars),
                    }
                )
            else:
                overview_outline = None
                for hemisphere in ("north", "south"):
                    overview = overviews[hemisphere]
                    page_id = f"overview-{hemisphere}"
                    draw_overview_page(context, overview, page, style, pdf_navigation)
                    pdf_navigation.mark_page(
                        surface,
                        context,
                        page_id,
                        label=(
                            "Northern Sky Overview"
                            if hemisphere == "north"
                            else "Southern Sky Overview"
                        ),
                    )
                    if hemisphere == "north":
                        overview_outline = pdf_navigation.add_page_outline(
                            surface, outline_root, "Sky Overviews", page_id
                        )
                        assert overview_outline is not None
                    else:
                        assert overview_outline is not None
                    pdf_navigation.add_page_outline(
                        surface,
                        overview_outline,
                        "Northern Sky" if hemisphere == "north" else "Southern Sky",
                        page_id,
                    )
                    surface.show_page()
                    overview_page_info.append(
                        {
                            "hemisphere": hemisphere,
                            "title": overview.title,
                            "chart_count": overview.chart_count,
                            "star_count": len(overview.stars),
                        }
                    )

    return OpeningPages(
        front_matter_pages,
        chart_directory,
        detail_chart_directory,
        chart_directory_pages,
        overviews,
        overview_page_info,
    )


def write_closing_pages(
    document: AtlasPdf,
    opening: OpeningPages,
    atlas_index: AtlasIndex,
    inputs: ChartInputs,
    star_names: dict[int, StarName],
    *,
    selected_sources: list[dict[str, Any]],
    geometry_inputs: dict[str, str | None],
    geometry_catalogues: dict[str, list[str]],
    write_front_matter: bool,
    progress: Progress,
) -> tuple[int, int, int]:
    """Append credits, index and back directories in the established PDF order."""
    atlas, style = document.atlas, document.style
    context, surface = document.context, document.surface
    pdf_navigation, outline_root = document.navigation, document.outline_root
    page, edition = document.page, atlas.resolved_edition()
    chart_directory_pages = opening.chart_directory_pages
    credits_page_count = 0
    if write_front_matter:
        with progress.step("append data sources and credits", detail=True):
            _draw_build_credits_page(
                context,
                surface,
                atlas,
                style,
                selected_sources,
                geometry_inputs,
                geometry_catalogues,
                inputs,
                star_names,
                pdf_navigation,
                outline_root,
            )
            credits_page_count = 1

    with progress.step("append atlas index", detail=True):
        index_pages = draw_atlas_index_pages(
            context,
            surface,
            atlas_index,
            page,
            style,
            edition,
            pdf_navigation,
            outline_parent_id=outline_root,
        )

    if write_front_matter and atlas.chart_directory_position == "back":
        with progress.step("append chart directory", detail=True):
            chart_directory_pages = draw_directories(
                document, opening.chart_directory, opening.detail_chart_directory
            )

    return credits_page_count, index_pages, chart_directory_pages
