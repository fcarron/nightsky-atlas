"""Register all atlas fonts from package assets with the active Fontconfig instance."""

from __future__ import annotations

import ctypes
import ctypes.util
from pathlib import Path

_registered = False


def register_bundled_fonts() -> None:
    """Register bundled atlas fonts and validate their intended matches."""
    global _registered
    if _registered:
        return
    library_name = ctypes.util.find_library("fontconfig")
    if library_name is None:
        raise RuntimeError("Fontconfig is required to load the bundled atlas fonts")
    fontconfig = ctypes.CDLL(library_name)
    fontconfig.FcInitLoadConfigAndFonts.restype = ctypes.c_void_p
    fontconfig.FcConfigSetCurrent.argtypes = [ctypes.c_void_p]
    fontconfig.FcConfigSetCurrent.restype = ctypes.c_int
    fontconfig.FcConfigParseAndLoadFromMemory.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
    ]
    fontconfig.FcConfigParseAndLoadFromMemory.restype = ctypes.c_int
    fontconfig.FcConfigAppFontAddFile.argtypes = [ctypes.c_void_p, ctypes.c_char_p]
    fontconfig.FcConfigAppFontAddFile.restype = ctypes.c_int
    fontconfig.FcConfigBuildFonts.argtypes = [ctypes.c_void_p]
    fontconfig.FcConfigBuildFonts.restype = ctypes.c_int
    fontconfig.FcPatternCreate.restype = ctypes.c_void_p
    fontconfig.FcPatternAddString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_char_p,
    ]
    fontconfig.FcPatternAddInteger.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    fontconfig.FcConfigSubstitute.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int]
    fontconfig.FcDefaultSubstitute.argtypes = [ctypes.c_void_p]
    fontconfig.FcFontMatch.argtypes = [
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_int),
    ]
    fontconfig.FcFontMatch.restype = ctypes.c_void_p
    fontconfig.FcPatternGetString.argtypes = [
        ctypes.c_void_p,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.POINTER(ctypes.c_char_p),
    ]
    fontconfig.FcPatternGetString.restype = ctypes.c_int
    fontconfig.FcPatternDestroy.argtypes = [ctypes.c_void_p]
    config = fontconfig.FcInitLoadConfigAndFonts()
    if not config:
        raise RuntimeError("Fontconfig could not load its configuration")
    reject_system_lato = (
        b'<fontconfig><selectfont><rejectfont><pattern>'
        b'<patelt name="family"><string>Lato</string></patelt>'
        b'</pattern></rejectfont></selectfont></fontconfig>'
    )
    if not fontconfig.FcConfigParseAndLoadFromMemory(config, reject_system_lato, 1):
        raise RuntimeError("Fontconfig could not exclude system-installed Lato fonts")
    font_dir = Path(__file__).parents[1] / "assets" / "fonts"
    font_files = (
        "SourceSans3-Variable.ttf",
        "Lato-Regular.ttf",
        "Lato-Bold.ttf",
    )
    for name in font_files:
        path = (font_dir / name).resolve()
        if not path.is_file() or not fontconfig.FcConfigAppFontAddFile(config, str(path).encode()):
            raise RuntimeError(f"could not register bundled font: {path}")
    if not fontconfig.FcConfigBuildFonts(config):
        raise RuntimeError("Fontconfig could not rebuild its font set")
    if not fontconfig.FcConfigSetCurrent(config):
        raise RuntimeError("Fontconfig could not activate the atlas font configuration")

    expected_matches = (
        ("Source Sans 3", 80, "SourceSans3-Variable.ttf"),
        ("Source Sans 3", 180, "SourceSans3-Variable.ttf"),
        ("Lato", 80, "Lato-Regular.ttf"),
        ("Lato", 200, "Lato-Bold.ttf"),
    )
    for family, weight, filename in expected_matches:
        pattern = fontconfig.FcPatternCreate()
        if not pattern:
            raise RuntimeError("Fontconfig could not create a font match pattern")
        match = None
        try:
            if not fontconfig.FcPatternAddString(pattern, b"family", family.encode()):
                raise RuntimeError(f"Fontconfig could not match {family}")
            if not fontconfig.FcPatternAddInteger(pattern, b"weight", weight):
                raise RuntimeError(f"Fontconfig could not match {family} weight {weight}")
            fontconfig.FcConfigSubstitute(config, pattern, 0)
            fontconfig.FcDefaultSubstitute(pattern)
            result = ctypes.c_int()
            match = fontconfig.FcFontMatch(config, pattern, ctypes.byref(result))
            matched_path = ctypes.c_char_p()
            if (
                not match
                or fontconfig.FcPatternGetString(
                    match,
                    b"file",
                    0,
                    ctypes.byref(matched_path),
                )
                != 0
            ):
                raise RuntimeError(f"Fontconfig could not resolve bundled font {family}")
            expected_path = (font_dir / filename).resolve()
            actual_path = Path(matched_path.value.decode()).resolve()
            if actual_path != expected_path:
                raise RuntimeError(
                    f"{family} resolved to {actual_path}, expected bundled font {expected_path}"
                )
        finally:
            if match:
                fontconfig.FcPatternDestroy(match)
            fontconfig.FcPatternDestroy(pattern)
    import gi

    gi.require_version("PangoCairo", "1.0")
    gi.require_version("PangoFc", "1.0")
    from gi.repository import PangoCairo, PangoFc

    PangoFc.FontMap.config_changed(PangoCairo.font_map_get_default())
    _registered = True
