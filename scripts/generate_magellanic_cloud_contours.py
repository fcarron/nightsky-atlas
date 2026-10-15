"""Generate compact Magellanic Cloud contour polygons from Gaia DR3 density FITS cutouts."""

from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.ndimage import (
    binary_closing,
    binary_fill_holes,
    gaussian_filter,
    label,
    median_filter,
)

DEFAULT_CUTOUTS = {
    "LMC": Path("data/third_party/gaia_dr3_magellanic/LMC-density.fits"),
    "SMC": Path("data/third_party/gaia_dr3_magellanic/SMC-density.fits"),
}
DEFAULT_FLUX_CUTOUTS = {
    "LMC": Path("data/third_party/gaia_dr3_magellanic/LMC-gflux.fits"),
    "SMC": Path("data/third_party/gaia_dr3_magellanic/SMC-gflux.fits"),
}
DEFAULT_OUTPUT = Path("data/third_party/gaia_dr3_magellanic/contours.geojson")
CONTOUR_RECIPE = {
    "LMC": (("density", 0.25), ("density", 0.50), ("flux", 0.55)),
    "SMC": (("density", 0.25), ("density", 0.45), ("density", 0.65)),
}
DSO_IDS = {"LMC": "ESO056-115", "SMC": "NGC0292"}
SMC_FOREGROUND_CLUSTER = (6.022333333333333, -72.08144444444444)


def _fits_image(path: Path) -> tuple[np.ndarray, dict[str, Any]]:
    raw = path.read_bytes()
    offset = 0
    header: dict[str, Any] = {}
    while True:
        card = raw[offset : offset + 80].decode("ascii")
        offset += 80
        if card.startswith("END"):
            break
        if card[8:10] != "= ":
            continue
        key = card[:8].strip()
        value = card[10:].split("/", 1)[0].strip()
        if value.startswith("'"):
            header[key] = value.strip("' ")
        else:
            try:
                header[key] = int(value)
            except ValueError:
                try:
                    header[key] = float(value.replace("D", "E"))
                except ValueError:
                    header[key] = value
    offset = ((offset + 2879) // 2880) * 2880
    if header.get("NAXIS") != 2 or header.get("BITPIX") != -32:
        raise ValueError(f"expected a 2-D float32 FITS cutout: {path}")
    width, height = int(header["NAXIS1"]), int(header["NAXIS2"])
    if width < 64 or height < 64:
        raise ValueError(f"FITS cutout is unexpectedly small: {path}")
    count = width * height
    data = np.frombuffer(raw, dtype=">f4", count=count, offset=offset).astype(np.float64)
    data = data.reshape(height, width)
    data = data * float(header.get("BSCALE", 1.0)) + float(header.get("BZERO", 0.0))
    if not np.isfinite(data).all():
        raise ValueError(f"FITS cutout contains non-finite values: {path}")
    return data, header


def _background_excess(
    image: np.ndarray, sigma_px: float, median_window_px: int
) -> tuple[np.ndarray, float]:
    height, width = image.shape
    y, x = np.indices(image.shape, dtype=np.float64)
    log_signal = np.log1p(np.maximum(image, 0.0))
    local_median = median_filter(log_signal, size=median_window_px, mode="nearest")
    smooth = gaussian_filter(local_median, sigma=sigma_px, mode="nearest")
    margin_x = max(12, int(width * 0.12))
    margin_y = max(12, int(height * 0.12))
    corners = ((x < margin_x) | (x >= width - margin_x)) & (
        (y < margin_y) | (y >= height - margin_y)
    )
    design = np.column_stack((np.ones(int(corners.sum())), x[corners], y[corners]))
    values = smooth[corners]
    keep = np.ones(len(values), dtype=bool)
    coefficients = np.zeros(3)
    for _ in range(6):
        coefficients = np.linalg.lstsq(design[keep], values[keep], rcond=None)[0]
        residual = values - design @ coefficients
        median = float(np.median(residual[keep]))
        mad = float(np.median(np.abs(residual[keep] - median)))
        if mad <= 1e-12:
            break
        next_keep = np.abs(residual - median) <= 3.5 * 1.4826 * mad
        if next_keep.sum() < 30 or np.array_equal(next_keep, keep):
            break
        keep = next_keep
    background = coefficients[0] + coefficients[1] * x + coefficients[2] * y
    excess = np.maximum(smooth - background, 0.0)
    central_radius_px = min(height, width) * 0.10
    radius = np.hypot(x - (width - 1) / 2, y - (height - 1) / 2)
    center_values = excess[radius <= central_radius_px]
    peak = float(np.percentile(center_values, 99.5))
    if peak <= 0.0:
        raise ValueError("Gaia source map has no positive central excess")
    return excess, peak


def _icrs_to_pixel(ra_deg: float, dec_deg: float, header: dict[str, Any]) -> tuple[float, float]:
    ra, dec = math.radians(ra_deg), math.radians(dec_deg)
    ra0, dec0 = math.radians(float(header["CRVAL1"])), math.radians(float(header["CRVAL2"]))
    delta_ra = (ra - ra0 + math.pi) % (2.0 * math.pi) - math.pi
    denominator = math.sin(dec0) * math.sin(dec) + math.cos(dec0) * math.cos(dec) * math.cos(
        delta_ra
    )
    xi = math.cos(dec) * math.sin(delta_ra) / denominator
    eta = (
        math.cos(dec0) * math.sin(dec) - math.sin(dec0) * math.cos(dec) * math.cos(delta_ra)
    ) / denominator
    if "CD1_1" in header:
        cd = np.array(
            [
                [float(header["CD1_1"]), float(header.get("CD1_2", 0.0))],
                [float(header.get("CD2_1", 0.0)), float(header["CD2_2"])],
            ]
        )
    else:
        pc = np.array(
            [
                [float(header.get("PC1_1", 1.0)), float(header.get("PC1_2", 0.0))],
                [float(header.get("PC2_1", 0.0)), float(header.get("PC2_2", 1.0))],
            ]
        )
        cd = np.diag([float(header["CDELT1"]), float(header["CDELT2"])]) @ pc
    pixel_offset = np.linalg.solve(cd, np.degrees([xi, eta]))
    return (
        float(header["CRPIX1"]) + pixel_offset[0] - 1.0,
        float(header["CRPIX2"]) + pixel_offset[1] - 1.0,
    )


def _remove_smc_foreground_cluster(image: np.ndarray, header: dict[str, Any]) -> np.ndarray:
    log_density = np.log1p(np.maximum(image, 0.0))
    x_center, y_center = _icrs_to_pixel(*SMC_FOREGROUND_CLUSTER, header)
    pixel_scale = math.sqrt(abs(float(header["CDELT1"]) * float(header["CDELT2"])))
    y, x = np.indices(image.shape, dtype=np.float64)
    radius_deg = np.hypot(x - x_center, y - y_center) * pixel_scale
    weight = np.clip((0.75 - radius_deg) / (0.75 - 0.40), 0.0, 1.0)
    smooth_field = gaussian_filter(log_density, sigma=15.0, mode="nearest")
    corrected = log_density * (1.0 - weight) + smooth_field * weight
    return np.maximum(np.expm1(corrected), 0.0)


def _largest_central_component(mask: np.ndarray) -> np.ndarray:
    mask = binary_closing(mask, structure=np.ones((3, 3), dtype=bool))
    components, _ = label(mask, structure=np.ones((3, 3), dtype=bool))
    height, width = mask.shape
    center_y, center_x = (height - 1) // 2, (width - 1) // 2
    component_id = int(components[center_y, center_x])
    if component_id == 0:
        radius = min(height, width) * 0.10
        y, x = np.indices(mask.shape)
        central = components[np.hypot(x - center_x, y - center_y) <= radius]
        counts = np.bincount(central.ravel())
        component_id = int(np.argmax(counts[1:]) + 1) if len(counts) > 1 else 0
    if component_id == 0:
        raise ValueError("no central connected Gaia density contour was found")
    component = binary_fill_holes(components == component_id)
    if np.any(component[[0, -1], :]) or np.any(component[:, [0, -1]]):
        raise ValueError("selected Gaia contour reaches the FITS cutout boundary")
    return component


def _boundary_loops(mask: np.ndarray) -> list[list[tuple[float, float]]]:
    height, width = mask.shape
    edges: list[tuple[tuple[int, int], tuple[int, int]]] = []
    padded = np.pad(mask, 1, constant_values=False)
    for row, col in zip(*np.nonzero(mask), strict=True):
        row += 1
        col += 1
        if not padded[row - 1, col]:
            edges.append(((col - 1, row - 1), (col, row - 1)))
        if not padded[row, col + 1]:
            edges.append(((col, row - 1), (col, row)))
        if not padded[row + 1, col]:
            edges.append(((col, row), (col - 1, row)))
        if not padded[row, col - 1]:
            edges.append(((col - 1, row), (col - 1, row - 1)))
    outgoing: dict[tuple[int, int], list[int]] = defaultdict(list)
    for index, (start, _) in enumerate(edges):
        outgoing[start].append(index)
    unused = set(range(len(edges)))
    loops: list[list[tuple[float, float]]] = []
    direction = {(1, 0): 0, (0, 1): 1, (-1, 0): 2, (0, -1): 3}
    while unused:
        first_index = min(unused)
        first, last = edges[first_index]
        path = [first, last]
        unused.remove(first_index)
        while last != first:
            options = [idx for idx in outgoing.get(last, ()) if idx in unused]
            if not options:
                raise ValueError("Gaia contour boundary is not a closed polygon")
            previous_dir = direction[(last[0] - path[-2][0], last[1] - path[-2][1])]
            options.sort(
                key=lambda idx: (
                    (
                        direction[(edges[idx][1][0] - last[0], edges[idx][1][1] - last[1])]
                        - previous_dir
                    )
                    % 4
                    not in (1, 0),
                    (
                        direction[(edges[idx][1][0] - last[0], edges[idx][1][1] - last[1])]
                        - previous_dir
                    )
                    % 4,
                    idx,
                )
            )
            selected = options[0]
            unused.remove(selected)
            last = edges[selected][1]
            path.append(last)
            if len(path) > len(edges) + 2:
                raise ValueError("Gaia contour boundary did not close")
        if len(path) >= 5:
            loops.append([(float(x), float(y)) for x, y in path[:-1]])
    if not loops:
        raise ValueError("Gaia contour contains no polygon boundary")
    return loops


def _point_line_distance(
    point: tuple[float, float], start: tuple[float, float], end: tuple[float, float]
) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    if dx == 0.0 and dy == 0.0:
        return math.dist(point, start)
    scale = max(
        0.0,
        min(1.0, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)),
    )
    return math.dist(point, (start[0] + scale * dx, start[1] + scale * dy))


def _rdp(points: list[tuple[float, float]], tolerance_px: float) -> list[tuple[float, float]]:
    if len(points) <= 3:
        return points
    split = max(
        range(1, len(points) - 1),
        key=lambda i: _point_line_distance(points[i], points[0], points[-1]),
    )
    distance = _point_line_distance(points[split], points[0], points[-1])
    if distance <= tolerance_px:
        return [points[0], points[-1]]
    left = _rdp(points[: split + 1], tolerance_px)
    right = _rdp(points[split:], tolerance_px)
    return left[:-1] + right


def _simplify_closed(
    points: list[tuple[float, float]], tolerance_px: float
) -> list[tuple[float, float]]:
    start_index = max(range(len(points)), key=lambda i: points[i][0])
    rotated = points[start_index:] + points[:start_index]
    opposite = max(range(1, len(rotated)), key=lambda i: math.dist(rotated[0], rotated[i]))
    first = _rdp(rotated[: opposite + 1], tolerance_px)
    second = _rdp(rotated[opposite:] + [rotated[0]], tolerance_px)
    result = first[:-1] + second[:-1]
    return result if len(result) >= 3 else points


def _pixel_to_icrs(pixel_x: float, pixel_y: float, header: dict[str, Any]) -> tuple[float, float]:
    dx = pixel_x - float(header["CRPIX1"])
    dy = pixel_y - float(header["CRPIX2"])
    if "CD1_1" in header:
        xi_deg = float(header["CD1_1"]) * dx + float(header.get("CD1_2", 0.0)) * dy
        eta_deg = float(header.get("CD2_1", 0.0)) * dx + float(header["CD2_2"]) * dy
    else:
        pc11 = float(header.get("PC1_1", 1.0))
        pc12 = float(header.get("PC1_2", 0.0))
        pc21 = float(header.get("PC2_1", 0.0))
        pc22 = float(header.get("PC2_2", 1.0))
        xi_deg = float(header["CDELT1"]) * (pc11 * dx + pc12 * dy)
        eta_deg = float(header["CDELT2"]) * (pc21 * dx + pc22 * dy)
    xi, eta = math.radians(xi_deg), math.radians(eta_deg)
    rho = math.hypot(xi, eta)
    ra0, dec0 = math.radians(float(header["CRVAL1"])), math.radians(float(header["CRVAL2"]))
    if rho == 0.0:
        return float(header["CRVAL1"]) % 360.0, float(header["CRVAL2"])
    c = math.atan(rho)
    dec = math.asin(math.cos(c) * math.sin(dec0) + eta * math.sin(c) * math.cos(dec0) / rho)
    ra = ra0 + math.atan2(
        xi * math.sin(c),
        rho * math.cos(dec0) * math.cos(c) - eta * math.sin(dec0) * math.sin(c),
    )
    return math.degrees(ra) % 360.0, math.degrees(dec)


def _extract_cloud(
    cloud_id: str,
    density_path: Path,
    flux_path: Path,
    *,
    sigma_px: float = 5.0,
    simplify_px: float = 1.0,
) -> list[dict[str, Any]]:
    sources: dict[str, tuple[np.ndarray, float, dict[str, Any], int]] = {}
    for source_id, path in (("density", density_path), ("flux", flux_path)):
        image, header = _fits_image(path)
        if header.get("RADESYS") != "ICRS" or header.get("CTYPE1") != "RA---TAN":
            raise ValueError(f"expected ICRS TAN FITS WCS in {path}")
        if source_id == "flux" and sources["density"][0].shape != image.shape:
            raise ValueError(f"density and G-flux cutouts have different dimensions for {cloud_id}")
        if source_id == "flux" and any(
            not math.isclose(float(header[key]), float(sources["density"][2][key]), abs_tol=1e-9)
            for key in ("CRVAL1", "CRVAL2", "CRPIX1", "CRPIX2", "CDELT1", "CDELT2")
        ):
            raise ValueError(f"density and G-flux cutouts have different WCS for {cloud_id}")
        pixel_scale = math.sqrt(abs(float(header["CDELT1"]) * float(header["CDELT2"])))
        median_window_px = max(3, round(0.30 / pixel_scale))
        if median_window_px % 2 == 0:
            median_window_px += 1
        if cloud_id == "SMC":
            image = _remove_smc_foreground_cluster(image, header)
        excess, peak = _background_excess(image, sigma_px, median_window_px)
        sources[source_id] = (excess, peak, header, median_window_px)
    features: list[dict[str, Any]] = []
    for level, (source_id, fraction) in enumerate(CONTOUR_RECIPE[cloud_id], start=1):
        excess, peak, header, median_window_px = sources[source_id]
        mask = _largest_central_component(excess >= peak * fraction)
        loops = _boundary_loops(mask)
        loop = max(loops, key=lambda item: abs(_signed_area(item)))
        simplified = _simplify_closed(loop, simplify_px)
        coordinates = [list(_pixel_to_icrs(x + 0.5, y + 0.5, header)) for x, y in simplified]
        coordinates.append(coordinates[0])
        features.append(
            {
                "type": "Feature",
                "id": f"magellanic:{cloud_id.lower()}:level-{level}",
                "properties": {
                    "cloud_id": cloud_id,
                    "dso_id": DSO_IDS[cloud_id],
                    "level": level,
                    "source_map": source_id,
                    "threshold_fraction_of_central_excess": fraction,
                    "threshold_log_excess": peak * fraction,
                    "smoothing_sigma_px": sigma_px,
                    "local_median_window_px": median_window_px,
                    "local_median_window_deg": median_window_px
                    * math.sqrt(abs(float(header["CDELT1"]) * float(header["CDELT2"]))),
                    "simplification_tolerance_px": simplify_px,
                },
                "geometry": {"type": "Polygon", "coordinates": [coordinates]},
            }
        )
    return features


def _signed_area(points: list[tuple[float, float]]) -> float:
    return (
        sum(
            x1 * y2 - x2 * y1
            for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1], strict=True)
        )
        / 2.0
    )


def generate(
    output: Path,
    cutouts: dict[str, Path],
    sigma_px: float,
    simplify_px: float,
    flux_cutouts: dict[str, Path] | None = None,
) -> dict[str, Any]:
    flux_cutouts = flux_cutouts or DEFAULT_FLUX_CUTOUTS
    features: list[dict[str, Any]] = []
    for cloud_id in ("LMC", "SMC"):
        features.extend(
            _extract_cloud(
                cloud_id,
                cutouts[cloud_id],
                flux_cutouts[cloud_id],
                sigma_px=sigma_px,
                simplify_px=simplify_px,
            )
        )
    result = {
        "type": "FeatureCollection",
        "source": {
            "catalogue": "Gaia DR3 density and G-band flux maps via CDS HiPS",
            "product_ids": ["CDS/P/DM/I/355/gaiadr3", "CDS/P/DM/flux-G/I/355/gaiadr3"],
            "product_release_dates": ["2022-06-15T09:24Z", "2022-06-16T14:31Z"],
            "data_provenance_id": "ivo://CDS/I/355/gaiadr3",
            "hiPS_creator": "Boch T. (CDS); CNRS/Université de Strasbourg",
            "copyright": "ESA/Gaia mission/DPAC; CDS/CNRS/Université de Strasbourg",
            "license": "ODbL-1.0",
            "attribution": (
                "Gaia DR3 (ESA/Gaia/DPAC); Gaia density HiPS "
                "(CDS, CNRS/Université de Strasbourg), ODbL-1.0"
            ),
            "processing": {
                "background": (
                    "robust linear plane fit to locally median-filtered log1p source-map "
                    "values in the four outer 12% corner regions, then subtracted"
                ),
                "smoothing": (
                    "0.30-degree local median filter followed by a Gaussian filter "
                    "in log1p source-map space"
                ),
                "contours": (
                    "each central connected contour is extracted independently from the "
                    "source map and threshold in the per-cloud recipe; no nesting is imposed"
                ),
                "smc_foreground_suppression": {
                    "object": "NGC 104 / 47 Tucanae, separate foreground globular cluster",
                    "center_icrs_deg": list(SMC_FOREGROUND_CLUSTER),
                    "full_replacement_radius_deg": 0.40,
                    "taper_radius_deg": 0.75,
                    "method": "linear taper toward a 15-pixel Gaussian-smoothed log-density field",
                },
                "recipe": {
                    cloud: [
                        {"level": index, "source_map": source, "threshold_fraction": fraction}
                        for index, (source, fraction) in enumerate(recipe, start=1)
                    ]
                    for cloud, recipe in CONTOUR_RECIPE.items()
                },
                "smoothing_sigma_px": sigma_px,
                "simplification_tolerance_px": simplify_px,
                "coordinate_conversion": "FITS TAN WCS to ICRS RA/Dec degrees",
            },
        },
        "features": features,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lmc", type=Path, default=DEFAULT_CUTOUTS["LMC"])
    parser.add_argument("--smc", type=Path, default=DEFAULT_CUTOUTS["SMC"])
    parser.add_argument("--lmc-gflux", type=Path, default=DEFAULT_FLUX_CUTOUTS["LMC"])
    parser.add_argument("--smc-gflux", type=Path, default=DEFAULT_FLUX_CUTOUTS["SMC"])
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--sigma-px", type=float, default=5.0)
    parser.add_argument("--simplify-px", type=float, default=1.0)
    args = parser.parse_args()
    result = generate(
        args.output,
        {"LMC": args.lmc, "SMC": args.smc},
        args.sigma_px,
        args.simplify_px,
        {"LMC": args.lmc_gflux, "SMC": args.smc_gflux},
    )
    print(f"wrote {len(result['features'])} contour polygons to {args.output}")
    for feature in result["features"]:
        count = len(feature["geometry"]["coordinates"][0]) - 1
        props = feature["properties"]
        print(
            f"{props['cloud_id']} level {props['level']}: "
            f"source={props['source_map']}; "
            f"threshold={props['threshold_fraction_of_central_excess']:.2f}; "
            f"vertices={count}"
        )


if __name__ == "__main__":
    main()
