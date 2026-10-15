import math
import struct
import zlib
from pathlib import Path

import cairo
import numpy as np
from generate_magellanic_cloud_contours import (
    _boundary_loops,
    _fits_image,
    _largest_central_component,
    _remove_smc_foreground_cluster,
    _signed_area,
)
from scipy.ndimage import gaussian_filter, median_filter

OUT = Path("build/magellanic-contour-comparison")
OUT.mkdir(parents=True, exist_ok=True)
COLORS = [(0.18, 0.42, 0.78), (0.12, 0.63, 0.51), (0.86, 0.36, 0.18)]
VARIANTS = [
    ("Density reference", "density", [("density", 0.25), ("density", 0.45), ("density", 0.65)]),
    ("Combined B on density", "density", [("density", 0.25), ("density", 0.50), ("flux", 0.55)]),
    ("Combined B on G flux", "flux", [("density", 0.25), ("density", 0.50), ("flux", 0.55)]),
    ("Flux core C on G flux", "flux", [("density", 0.25), ("flux", 0.35), ("flux", 0.60)]),
]


def field(cloud, src):
    source_suffix = "gflux" if src == "flux" else "density"
    path = Path(f"data/third_party/gaia_dr3_magellanic/{cloud}-{source_suffix}.fits")
    arr, h = _fits_image(path)
    if cloud == "SMC":
        arr = _remove_smc_foreground_cluster(arr, h)
    px = math.sqrt(abs(float(h["CDELT1"]) * float(h["CDELT2"])))
    mw = max(3, round(0.30 / px))
    mw += mw % 2 == 0
    log = np.log1p(np.maximum(arr, 0))
    smooth = gaussian_filter(median_filter(log, size=mw, mode="nearest"), sigma=5.0, mode="nearest")
    x, y = np.meshgrid(np.arange(arr.shape[1]), np.arange(arr.shape[0]))
    mx, my = max(12, int(arr.shape[1] * 0.12)), max(12, int(arr.shape[0] * 0.12))
    corners = ((x < mx) | (x >= arr.shape[1] - mx)) & ((y < my) | (y >= arr.shape[0] - my))
    design = np.column_stack((np.ones(int(corners.sum())), x[corners], y[corners]))
    vals = smooth[corners]
    keep = np.ones(len(vals), bool)
    for _ in range(6):
        coef = np.linalg.lstsq(design[keep], vals[keep], rcond=None)[0]
        res = vals - design @ coef
        med = np.median(res[keep])
        mad = np.median(abs(res[keep] - med))
        if mad <= 1e-12:
            break
        next_keep = abs(res - med) <= 3.5 * 1.4826 * mad
        if next_keep.sum() < 30 or np.array_equal(next_keep, keep):
            break
        keep = next_keep
    bg = coef[0] + coef[1] * x + coef[2] * y
    excess = np.maximum(smooth - bg, 0)
    radius = np.hypot(x - (arr.shape[1] - 1) / 2, y - (arr.shape[0] - 1) / 2)
    peak = np.percentile(excess[radius <= min(arr.shape) * 0.10], 99.5)
    return arr, smooth, excess, peak, h


def png_gray(data, path):
    low, high = np.percentile(data, [8, 99.6])
    normalized = np.clip((data - low) / (high - low), 0, 1)
    gray = (255 * (1 - normalized * 0.92)).astype("uint8")
    height, width = gray.shape
    raw = b"".join(
        b"\0" + bytes(np.repeat(gray[row, :, None], 3, axis=1).ravel()) for row in range(height)
    )

    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 6))
        + chunk(b"IEND", b"")
    )


def render(cloud):
    cached = {source: field(cloud, source) for source in ("density", "flux")}
    paths = {}
    for source in ("density", "flux"):
        path = OUT / f"{cloud.lower()}-{source}-background.png"
        png_gray(cached[source][1], path)
        paths[source] = cairo.ImageSurface.create_from_png(str(path))
    width_px, height_px = 500, 500
    pad, top, bottom = 18, 72, 34
    width, height = 4 * width_px + 5 * pad, top + height_px + bottom
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    context = cairo.Context(surface)
    context.set_source_rgb(1, 1, 1)
    context.paint()
    for index, (title, background, choices) in enumerate(VARIANTS):
        x = pad + index * (width_px + pad)
        context.set_source_rgb(0.1, 0.1, 0.1)
        context.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD)
        context.set_font_size(15)
        context.move_to(x, 24)
        context.show_text(f"{cloud} · {title}")
        context.set_source_rgb(0.23, 0.23, 0.23)
        context.select_font_face("Sans", cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_NORMAL)
        context.set_font_size(12)
        context.move_to(x, 46)
        context.show_text(f"Gaia DR3 {background} values")
        context.set_source_surface(paths[background], x, top)
        context.paint()
        context.save()
        context.translate(x, top)
        for level, (source, fraction) in enumerate(choices):
            excess, peak = cached[source][2:4]
            mask = _largest_central_component(excess >= peak * fraction)
            loops = _boundary_loops(mask)
            loop = max(loops, key=lambda points: abs(_signed_area(points)))
            context.set_source_rgb(*COLORS[level])
            context.set_line_width(2.5 if level == 0 else 2.1)
            context.move_to(*loop[0])
            for point in loop[1:]:
                context.line_to(*point)
            context.close_path()
            context.stroke()
        context.restore()
    destination = OUT / f"{cloud.lower()}-contour-comparison.png"
    surface.write_to_png(str(destination))
    print(destination)


for cloud in ("LMC", "SMC"):
    render(cloud)
