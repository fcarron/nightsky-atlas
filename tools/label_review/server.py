from __future__ import annotations

import argparse
import json
import math
import random
import re
import struct
import threading
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

APP_ROOT = Path(__file__).resolve().parent
REPO_ROOT = APP_ROOT.parents[1]
ASSET_ROOT = APP_ROOT / "cases" / "assets"
DEFAULT_MANIFEST = APP_ROOT / "cases.json"
DEFAULT_RESPONSES = REPO_ROOT / "build" / "label-review" / "curated-2026-10-01.jsonl"
MAX_REQUEST_BYTES = 16_384
CLICK_TOLERANCE_MM = 1.0
CASE_ID_PATTERN = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
SESSION_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]{1,80}$")


class ReviewError(ValueError):
    pass


def _png_size(path: Path) -> tuple[int, int]:
    with path.open("rb") as file:
        header = file.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ReviewError(f"Bild ist keine gültige PNG-Datei: {path.name}")
    return struct.unpack(">II", header[16:24])


def _asset_path(relative_path: object) -> Path:
    if not isinstance(relative_path, str) or not relative_path:
        raise ReviewError("Jeder Fall braucht zwei relative PNG-Bildpfade.")
    path = Path(relative_path)
    if path.is_absolute():
        raise ReviewError(f"Absolute Bildpfade sind nicht erlaubt: {relative_path}")
    resolved = (APP_ROOT / path).resolve()
    if not resolved.is_relative_to(ASSET_ROOT.resolve()):
        raise ReviewError(f"Bildpfad liegt außerhalb von cases/assets: {relative_path}")
    if not resolved.is_file():
        raise ReviewError(f"Bilddatei fehlt: {relative_path}")
    return resolved


def load_manifest(path: Path = DEFAULT_MANIFEST) -> dict:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ReviewError(f"Case-Manifest fehlt: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ReviewError(f"Case-Manifest ist ungültiges JSON: {exc}") from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("cases"), list):
        raise ReviewError("Case-Manifest braucht ein cases-Array.")
    if not isinstance(raw.get("seed"), (int, str)):
        raise ReviewError("Case-Manifest braucht einen ganzzahligen oder Text-Seed.")
    dpi = raw.get("dpi")
    if not isinstance(dpi, (int, float)) or dpi <= 0:
        raise ReviewError("Case-Manifest braucht einen positiven dpi-Wert.")
    if not isinstance(raw.get("require_calibration", False), bool):
        raise ReviewError("require_calibration muss true oder false sein.")

    case_ids: set[str] = set()
    for case in raw["cases"]:
        if not isinstance(case, dict):
            raise ReviewError("Jeder Eintrag in cases muss ein Objekt sein.")
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not CASE_ID_PATTERN.fullmatch(case_id):
            raise ReviewError(f"Ungültige case_id: {case_id!r}")
        if case_id in case_ids:
            raise ReviewError(f"case_id kommt mehrfach vor: {case_id}")
        case_ids.add(case_id)
        for field in ("chart_id", "chart_code", "label_id", "object_id", "label_text", "question"):
            if not isinstance(case.get(field), str) or not case[field].strip():
                raise ReviewError(f"{case_id}: Feld {field} fehlt oder ist leer.")
        if not isinstance(case.get("accuracy_evaluable", True), bool):
            raise ReviewError(f"{case_id}: accuracy_evaluable muss true oder false sein.")
        crop = case.get("crop")
        if not isinstance(crop, dict):
            raise ReviewError(f"{case_id}: crop-Metadaten fehlen.")
        box = crop.get("box_px")
        page_size = crop.get("page_size_px")
        print_size = crop.get("print_size_mm")
        if (
            not isinstance(box, list)
            or len(box) != 4
            or not all(isinstance(value, int) for value in box)
            or not isinstance(page_size, list)
            or len(page_size) != 2
            or not all(isinstance(value, int) for value in page_size)
            or not isinstance(print_size, list)
            or len(print_size) != 2
            or not all(isinstance(value, (int, float)) and value > 0 for value in print_size)
        ):
            raise ReviewError(f"{case_id}: crop braucht box_px, page_size_px und print_size_mm.")
        x, y, width, height = box
        if (
            width <= 0
            or height <= 0
            or x < 0
            or y < 0
            or x + width > page_size[0]
            or y + height > page_size[1]
        ):
            raise ReviewError(f"{case_id}: Ausschnitt liegt außerhalb der Quellseite.")
        expected_mm = (width * 25.4 / float(dpi), height * 25.4 / float(dpi))
        if any(
            abs(float(value) - expected) > 0.08
            for value, expected in zip(print_size, expected_mm, strict=True)
        ):
            raise ReviewError(f"{case_id}: physische Bildgröße passt nicht zu Pixelmaßen und dpi.")

        variants = case.get("variants")
        if not isinstance(variants, list) or len(variants) != 2:
            raise ReviewError(f"{case_id}: genau zwei Varianten sind erforderlich.")
        variant_ids: set[str] = set()
        registration_ids: set[str] = set()
        target_points: list[tuple[float, float]] = []
        for variant in variants:
            if not isinstance(variant, dict):
                raise ReviewError(f"{case_id}: Varianten müssen JSON-Objekte sein.")
            variant_id = variant.get("variant_id")
            if (
                not isinstance(variant_id, str)
                or not variant_id.strip()
                or variant_id in variant_ids
            ):
                raise ReviewError(f"{case_id}: Varianten-IDs fehlen oder sind doppelt.")
            variant_ids.add(variant_id)
            if variant.get("crop_box_px") != box or variant.get("source_page_size_px") != page_size:
                raise ReviewError(
                    f"{case_id}: Varianten verwenden nicht denselben Quellenausschnitt."
                )
            registration_id = variant.get("registration_id")
            if not isinstance(registration_id, str) or not registration_id:
                raise ReviewError(f"{case_id}: registration_id fehlt.")
            registration_ids.add(registration_id)
            image_path = _asset_path(variant.get("image"))
            image_width, image_height = _png_size(image_path)
            if (image_width, image_height) != (width, height):
                raise ReviewError(
                    f"{case_id}: {image_path.name} hat {image_width}×{image_height} px; "
                    f"erwartet sind {width}×{height} px für denselben Ausschnitt."
                )
            target = variant.get("target_px")
            if (
                not isinstance(target, list)
                or len(target) != 2
                or not all(
                    isinstance(value, (int, float)) and math.isfinite(value) for value in target
                )
                or not 0 <= target[0] < width
                or not 0 <= target[1] < height
            ):
                raise ReviewError(f"{case_id}: Zielpunkt muss innerhalb des Bildes liegen.")
            target_points.append((float(target[0]), float(target[1])))
            source_page = variant.get("source_page")
            if not isinstance(source_page, str) or not source_page.strip():
                raise ReviewError(f"{case_id}: Quellseite fehlt als Herkunftsnachweis.")
        if len(registration_ids) != 1:
            raise ReviewError(f"{case_id}: Varianten haben verschiedene Registrierungen.")
        target_delta = math.hypot(
            target_points[0][0] - target_points[1][0],
            target_points[0][1] - target_points[1][1],
        )
        if target_delta > 0.25:
            raise ReviewError(f"{case_id}: Zielpunkte der Varianten liegen nicht übereinander.")
    if not raw["cases"]:
        raise ReviewError("Das Case-Manifest enthält keine Fälle.")
    return raw


def _read_records(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ReviewError(f"Ungültige JSONL-Zeile {line_number}: {exc}") from exc
        if isinstance(item, dict):
            records.append(item)
    return records


def _presentation(manifest: dict) -> tuple[list[dict], dict[str, dict[str, str]]]:
    rng = random.Random(str(manifest["seed"]))
    cases = list(manifest["cases"])
    rng.shuffle(cases)
    flip_ids = {case["case_id"] for case in cases[: len(cases) // 2]}
    assignments: dict[str, dict[str, str]] = {}
    for case in cases:
        variants = case["variants"]
        first, second = variants
        if case["case_id"] in flip_ids:
            first, second = second, first
        assignments[case["case_id"]] = {"A": first["variant_id"], "B": second["variant_id"]}
    return cases, assignments


def _public_session(manifest: dict, session_id: str, responses_path: Path) -> dict:
    records = _read_records(responses_path)
    completed = {item.get("case_id") for item in records if item.get("session_id") == session_id}
    cases = []
    for case in manifest["_ordered_cases"]:
        cases.append(
            {
                "case_id": case["case_id"],
                "chart_code": case["chart_code"],
                "question": case["question"],
                "print_width_mm": case["crop"]["print_size_mm"][0],
                "print_height_mm": case["crop"]["print_size_mm"][1],
                "image_a": f"/image/{case['case_id']}/A.png",
                "image_b": f"/image/{case['case_id']}/B.png",
                "completed": case["case_id"] in completed,
            }
        )
    return {
        "seed": manifest["seed"],
        "require_calibration": manifest.get("require_calibration", False),
        "cases": cases,
        "completed": sorted(completed),
    }


def summarize(path: Path) -> str:
    records = _read_records(path)
    if not records:
        return "Noch keine Antworten gespeichert."
    preferences: dict[str, int] = {}
    clicks: dict[str, list[int]] = {}
    skipped = 0
    controls = 0
    non_evaluable = 0
    for record in records:
        if record.get("control"):
            controls += 1
        if record.get("accuracy_evaluable") is False:
            non_evaluable += 1
        preference = record.get("preference")
        if preference == "skip":
            skipped += 1
        elif preference in ("A", "B"):
            variant_id = record.get("variant_assignment", {}).get(preference, "unknown")
            preferences[variant_id] = preferences.get(variant_id, 0) + 1
        elif preference in ("equal", "both_bad"):
            preferences[preference] = preferences.get(preference, 0) + 1
        for slot in ("A", "B"):
            click = record.get("clicks", {}).get(slot)
            if click is None or click.get("correct") is None:
                continue
            variant_id = record.get("variant_assignment", {}).get(slot, "unknown")
            bucket = clicks.setdefault(variant_id, [0, 0])
            bucket[1] += 1
            bucket[0] += bool(click.get("correct"))
    lines = [
        f"Antworten: {len(records)}",
        f"Übersprungen: {skipped}",
        f"Kontrollfälle beantwortet: {controls}",
        f"Klickwertung ausgesetzt: {non_evaluable}",
        "",
        "Symbolzuordnung je Variante:",
    ]
    for variant_id, (correct, total) in sorted(clicks.items()):
        lines.append(f"  {variant_id}: {correct}/{total} korrekt")
    lines.extend(("", "Präferenz:"))
    for key, count in sorted(preferences.items()):
        lines.append(f"  {key}: {count}")
    return "\n".join(lines)


def make_handler(
    manifest: dict, assignments: dict[str, dict[str, str]], responses_path: Path, port: int
):
    lock = threading.Lock()
    variants_by_case = {
        case["case_id"]: {item["variant_id"]: item for item in case["variants"]}
        for case in manifest["cases"]
    }
    cases_by_id = {case["case_id"]: case for case in manifest["cases"]}

    class Handler(BaseHTTPRequestHandler):
        server_version = "NightSkyLabelReview/1"

        def log_message(self, format: str, *args: object) -> None:
            print(f"[{self.log_date_time_string()}] {format % args}")

        def _json(self, status: int, value: dict) -> None:
            data = json.dumps(value, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _text(self, status: int, value: str) -> None:
            data = value.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:
            route = urlsplit(self.path)
            if route.path == "/api/config":
                self._json(200, {"require_calibration": manifest.get("require_calibration", False)})
                return
            if route.path == "/":
                self._static("index.html", "text/html; charset=utf-8")
                return
            if route.path == "/app.css":
                self._static("app.css", "text/css; charset=utf-8")
                return
            if route.path == "/app.js":
                self._static("app.js", "text/javascript; charset=utf-8")
                return
            if route.path == "/api/session":
                session_id = parse_qs(route.query).get("session_id", [""])[0]
                if not SESSION_ID_PATTERN.fullmatch(session_id):
                    self._json(400, {"error": "Ungültige Sitzungs-ID."})
                    return
                self._json(200, _public_session(manifest, session_id, responses_path))
                return
            match = re.fullmatch(r"/image/([a-z0-9-]+)/([AB])\.png", route.path)
            if match:
                case_id, slot = match.groups()
                case = cases_by_id.get(case_id)
                if case is None:
                    self._text(404, "Unbekannter Fall.")
                    return
                variant_id = assignments[case_id][slot]
                image_path = _asset_path(variants_by_case[case_id][variant_id]["image"])
                data = image_path.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self.wfile.write(data)
                return
            self._text(404, "Nicht gefunden.")

        def _static(self, name: str, content_type: str) -> None:
            path = APP_ROOT / name
            data = path.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def do_POST(self) -> None:
            if self.path != "/api/answer":
                self._json(404, {"error": "Nicht gefunden."})
                return
            expected_origin = f"http://127.0.0.1:{port}"
            origin = self.headers.get("Origin")
            if origin not in (None, expected_origin):
                self._json(403, {"error": "Nur Anfragen von dieser lokalen App sind erlaubt."})
                return
            if self.headers.get("Host") != f"127.0.0.1:{port}":
                self._json(403, {"error": "Die App akzeptiert nur Verbindungen über 127.0.0.1."})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > MAX_REQUEST_BYTES:
                    raise ReviewError("Antwort hat eine ungültige Größe.")
                payload = json.loads(self.rfile.read(length))
                record = self._make_record(payload)
                with lock:
                    if any(
                        item.get("session_id") == record["session_id"]
                        and item.get("case_id") == record["case_id"]
                        for item in _read_records(responses_path)
                    ):
                        self._json(
                            409,
                            {"error": "Dieser Fall wurde in dieser Sitzung bereits gespeichert."},
                        )
                        return
                    responses_path.parent.mkdir(parents=True, exist_ok=True)
                    with responses_path.open("a", encoding="utf-8") as output:
                        output.write(
                            json.dumps(record, ensure_ascii=False, separators=(",", ":")) + "\n"
                        )
                self._json(201, {"saved": True})
            except (ReviewError, json.JSONDecodeError, TypeError, ValueError) as exc:
                self._json(400, {"error": str(exc)})

        def _make_record(self, payload: object) -> dict:
            if not isinstance(payload, dict):
                raise ReviewError("Antwort muss ein JSON-Objekt sein.")
            case_id = payload.get("case_id")
            session_id = payload.get("session_id")
            if not isinstance(case_id, str) or case_id not in cases_by_id:
                raise ReviewError("Unbekannter Fall.")
            if not isinstance(session_id, str) or not SESSION_ID_PATTERN.fullmatch(session_id):
                raise ReviewError("Ungültige Sitzungs-ID.")
            preference = payload.get("preference")
            if preference not in ("A", "B", "equal", "both_bad", "skip"):
                raise ReviewError("Ungültige Präferenz.")
            clicks = payload.get("clicks", {})
            if not isinstance(clicks, dict):
                raise ReviewError("Klickdaten sind ungültig.")
            case = cases_by_id[case_id]
            variants = variants_by_case[case_id]
            slot_assignment = assignments[case_id]
            width = case["crop"]["box_px"][2]
            height = case["crop"]["box_px"][3]
            dpi = float(manifest["dpi"])
            saved_clicks: dict[str, dict | None] = {}
            if preference != "skip":
                for slot in ("A", "B"):
                    point = clicks.get(slot)
                    if not isinstance(point, dict):
                        raise ReviewError(f"Bitte das Symbol in Bild {slot} anklicken.")
                    x = point.get("x")
                    y = point.get("y")
                    if (
                        not isinstance(x, (int, float))
                        or not isinstance(y, (int, float))
                        or not math.isfinite(x)
                        or not math.isfinite(y)
                        or not 0 <= x <= 1
                        or not 0 <= y <= 1
                    ):
                        raise ReviewError(f"Klickposition in Bild {slot} ist ungültig.")
                    variant_id = slot_assignment[slot]
                    target = variants[variant_id]["target_px"]
                    dx_mm = (x * width - target[0]) * 25.4 / dpi
                    dy_mm = (y * height - target[1]) * 25.4 / dpi
                    saved_clicks[slot] = {
                        "x_rel": round(float(x), 6),
                        "y_rel": round(float(y), 6),
                        "correct": (
                            math.hypot(dx_mm, dy_mm) <= CLICK_TOLERANCE_MM
                            if case.get("accuracy_evaluable", True)
                            else None
                        ),
                    }
            else:
                saved_clicks = {"A": None, "B": None}
            note = payload.get("note", "")
            if not isinstance(note, str) or len(note) > 1000:
                raise ReviewError("Notiz darf höchstens 1000 Zeichen enthalten.")
            elapsed_ms = payload.get("elapsed_ms", 0)
            if not isinstance(elapsed_ms, int) or not 0 <= elapsed_ms <= 86_400_000:
                raise ReviewError("Bearbeitungszeit ist ungültig.")
            px_per_mm = payload.get("px_per_mm")
            calibrated = payload.get("calibrated") is True
            if manifest.get("require_calibration", False) and not calibrated:
                raise ReviewError("Diese Bewertungsrunde braucht eine 50-mm-Anzeigekalibrierung.")
            if calibrated and px_per_mm is None:
                raise ReviewError("Für eine kalibrierte Antwort fehlt der px/mm-Wert.")
            if px_per_mm is not None and (
                not isinstance(px_per_mm, (int, float))
                or not math.isfinite(px_per_mm)
                or not 1 <= px_per_mm <= 20
            ):
                raise ReviewError("Anzeige-Kalibrierung muss zwischen 1 und 20 CSS-px/mm liegen.")
            return {
                "saved_utc": datetime.now(UTC).isoformat(),
                "experiment_id": manifest["experiment_id"],
                "seed": manifest["seed"],
                "session_id": session_id,
                "case_id": case_id,
                "chart_id": case["chart_id"],
                "chart_code": case["chart_code"],
                "label_id": case["label_id"],
                "object_id": case["object_id"],
                "variant_assignment": dict(slot_assignment),
                "clicks": saved_clicks,
                "preference": preference,
                "elapsed_ms": elapsed_ms,
                "note": note.strip(),
                "px_per_mm": px_per_mm,
                "calibrated": calibrated,
                "control": bool(case.get("control", False)),
                "accuracy_evaluable": case.get("accuracy_evaluable", True),
            }

    return Handler


def serve(port: int, responses_path: Path, manifest_path: Path) -> None:
    manifest = load_manifest(manifest_path)
    ordered, assignments = _presentation(manifest)
    manifest["_ordered_cases"] = ordered
    responses_path = responses_path.resolve()
    build_root = (REPO_ROOT / "build").resolve()
    if not responses_path.is_relative_to(build_root):
        raise ReviewError(f"Antwortdatei muss unter {build_root} liegen.")
    responses_path.parent.mkdir(parents=True, exist_ok=True)
    handler = make_handler(manifest, assignments, responses_path, port)
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    print(f"Case-Manifest: {manifest_path}")
    print(f"Antworten: {responses_path}")
    print(f"Seed: {manifest['seed']}; Reihenfolge und A/B-Zuweisung bleiben reproduzierbar.")
    print(f"Öffne http://127.0.0.1:{port}/  (mit Strg+C beenden)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nReview-App beendet.")
    finally:
        server.server_close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Lokale Blindbewertung von Kartenvarianten")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("serve", help="lokale Review-App starten")
    run.add_argument("--port", type=int, default=8765)
    run.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    run.add_argument("--responses", type=Path, default=DEFAULT_RESPONSES)
    report = commands.add_parser("summary", help="JSONL-Antworten lokal auswerten")
    report.add_argument("--responses", type=Path, default=DEFAULT_RESPONSES)
    args = parser.parse_args()
    try:
        if args.command == "serve":
            if not 1024 <= args.port <= 65535:
                raise ReviewError("Port muss zwischen 1024 und 65535 liegen.")
            serve(args.port, args.responses, args.manifest)
            return 0
        if args.command == "summary":
            print(summarize(args.responses))
            return 0
    except ReviewError as exc:
        parser.exit(2, f"Fehler: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
