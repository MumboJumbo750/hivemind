#!/usr/bin/env python3
"""
Kartograph Frontend-Scanner — analysiert Vue-Dateien auf Design-System-Compliance.

Scannt frontend/src/**/*.vue und aktualisiert seed/wiki/frontend-component-architektur.md
mit aktuellen Metriken.

Verwendung:
    python scripts/kartograph_scan.py              # nur Scan-Report
    python scripts/kartograph_scan.py --update     # aktualisiert Wiki-Datei
"""
from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FRONTEND_SRC = REPO_ROOT / "frontend" / "src"
WIKI_FILE = REPO_ROOT / "seed" / "wiki" / "frontend-component-architektur.md"


# ─── Regex-Patterns ───────────────────────────────────────────────────────────

# Hardcoded hex colors: #abc, #aabbcc, #aabbccdd (in <style> blocks only)
RE_HEX_COLOR = re.compile(r"#[0-9a-fA-F]{3,8}\b")
# rgba() with literal values (not var())
RE_RGBA = re.compile(r"rgba\s*\(\s*\d")
# Hardcoded px in padding/margin/gap
RE_HARDCODED_PX = re.compile(r"(?:padding|margin|gap)\s*:\s*[^;]*\d+px")
# Hardcoded border-radius in px
RE_HARDCODED_RADIUS = re.compile(r"border-radius\s*:\s*[^;]*\d+px")
# Local .btn- definitions
RE_LOCAL_BTN = re.compile(r"^\s*\.btn[-_]", re.MULTILINE)
# Local .badge- definitions  
RE_LOCAL_BADGE = re.compile(r"^\s*\.badge[-_]", re.MULTILINE)
# Token references var(--)
RE_TOKEN_REF = re.compile(r"var\(--[a-z]")


def extract_style_block(content: str) -> str:
    """Extrahiert den Inhalt des <style> Blocks aus einer .vue-Datei."""
    match = re.search(r"<style[^>]*>(.*?)</style>", content, re.DOTALL)
    return match.group(1) if match else ""


# ─── Scan ─────────────────────────────────────────────────────────────────────

def scan_vue_files() -> dict:
    """Scannt alle .vue-Dateien und gibt Metriken zurück."""
    vue_files = sorted(FRONTEND_SRC.rglob("*.vue"))

    total_files = len(vue_files)
    files_with_btn = []
    files_with_badge = []
    hex_count = 0
    rgba_count = 0
    px_padding_count = 0
    px_radius_count = 0
    token_ref_count = 0
    total_style_lines = 0

    ui_components = sorted(
        (FRONTEND_SRC / "components" / "ui").glob("*.vue")
        if (FRONTEND_SRC / "components" / "ui").exists() else []
    )
    domain_components = sorted(
        (FRONTEND_SRC / "components" / "domain").glob("*.vue")
        if (FRONTEND_SRC / "components" / "domain").exists() else []
    )
    views = sorted(
        (FRONTEND_SRC / "views").rglob("*.vue")
        if (FRONTEND_SRC / "views").exists() else []
    )

    file_details = []

    for f in vue_files:
        try:
            content = f.read_text(encoding="utf-8")
        except Exception:
            continue

        style = extract_style_block(content)
        if not style:
            continue

        style_lines = style.count("\n")
        total_style_lines += style_lines

        file_hex = len(RE_HEX_COLOR.findall(style))
        file_rgba = len(RE_RGBA.findall(style))
        file_px = len(RE_HARDCODED_PX.findall(style))
        file_radius = len(RE_HARDCODED_RADIUS.findall(style))
        file_tokens = len(RE_TOKEN_REF.findall(style))
        has_btn = bool(RE_LOCAL_BTN.search(style))
        has_badge = bool(RE_LOCAL_BADGE.search(style))

        hex_count += file_hex
        rgba_count += file_rgba
        px_padding_count += file_px
        px_radius_count += file_radius
        token_ref_count += file_tokens

        rel = f.relative_to(FRONTEND_SRC)
        violations = file_hex + file_rgba + file_px + file_radius

        if has_btn:
            files_with_btn.append(str(rel))
        if has_badge:
            files_with_badge.append(str(rel))

        if violations > 0:
            file_details.append({
                "path": str(rel),
                "hex": file_hex,
                "rgba": file_rgba,
                "px_padding": file_px,
                "px_radius": file_radius,
                "tokens": file_tokens,
                "violations": violations,
            })

    file_details.sort(key=lambda x: -x["violations"])

    return {
        "scan_date": date.today().isoformat(),
        "total_vue_files": total_files,
        "ui_components": [f.name for f in ui_components],
        "domain_components": [f.name for f in domain_components],
        "view_count": len(views),
        "hex_colors": hex_count,
        "rgba_values": rgba_count,
        "hardcoded_px_padding": px_padding_count,
        "hardcoded_px_radius": px_radius_count,
        "token_refs": token_ref_count,
        "total_style_lines": total_style_lines,
        "files_with_btn": files_with_btn,
        "files_with_badge": files_with_badge,
        "file_details": file_details[:15],  # Top 15 Verletzungen
    }


# ─── Report ───────────────────────────────────────────────────────────────────

def format_report(m: dict) -> str:
    """Erstellt einen Markdown-Report aus den Metriken."""
    btn_list = "\n".join(f"  - `{f}`" for f in m["files_with_btn"]) or "  _Keine_"
    badge_list = "\n".join(f"  - `{f}`" for f in m["files_with_badge"]) or "  _Keine_"

    top_violations = ""
    if m["file_details"]:
        rows = "\n".join(
            f"| `{d['path']}` | {d['hex']} | {d['rgba']} | {d['px_padding']} | {d['px_radius']} |"
            for d in m["file_details"]
        )
        top_violations = f"""
### Top-Verletzungen pro Datei

| Datei | Hex-Farben | rgba() | Padding px | Radius px |
| --- | --- | --- | --- | --- |
{rows}
"""

    ui_list = ", ".join(f.replace(".vue", "") for f in m["ui_components"]) or "_Keine_"
    domain_list = ", ".join(f.replace(".vue", "") for f in m["domain_components"]) or "_Keine_"

    return f"""## Aktueller Stand (Scan: {m['scan_date']})

> Automatisch generiert durch `scripts/kartograph_scan.py`

### Metriken

| KPI | Wert | Ziel |
| --- | --- | --- |
| Vue-Dateien total | {m['total_vue_files']} | — |
| UI Components (`components/ui/`) | {len(m['ui_components'])} | ~18 |
| Domain Components (`components/domain/`) | {len(m['domain_components'])} | ~10 |
| Views | {m['view_count']} | — |
| Hardcoded Hex-Farben in Styles | {m['hex_colors']} | **0** |
| Hardcoded rgba()-Werte in Styles | {m['rgba_values']} | **0** |
| Hardcoded `padding`/`margin` in px | {m['hardcoded_px_padding']} | **0** |
| Hardcoded `border-radius` in px | {m['hardcoded_px_radius']} | **0** |
| Token-Referenzen `var(--)` (gesamt) | {m['token_refs']} | ↑ maximieren |
| Files mit eigener `.btn-*` Definition | {len(m['files_with_btn'])} | **0** |
| Files mit eigener `.badge-*` Definition | {len(m['files_with_badge'])} | **0** |

### UI Components ({len(m['ui_components'])})

{ui_list}

### Domain Components ({len(m['domain_components'])})

{domain_list}

### Files mit `.btn-*` Definitionen

{btn_list}

### Files mit `.badge-*` Definitionen

{badge_list}
{top_violations}"""


# ─── Wiki-Update ──────────────────────────────────────────────────────────────

SCAN_SECTION_START = "## Aktueller Stand"
SCAN_SECTION_END_MARKER = "\n## "  # nächste H2-Sektion


def update_wiki_file(report: str) -> None:
    """Ersetzt/fügt den 'Aktueller Stand'-Abschnitt in der Wiki-Datei ein."""
    if not WIKI_FILE.exists():
        print(f"ERROR: Wiki-Datei nicht gefunden: {WIKI_FILE}", file=sys.stderr)
        sys.exit(1)

    content = WIKI_FILE.read_text(encoding="utf-8")

    # Vorhandenen Scan-Abschnitt entfernen
    if SCAN_SECTION_START in content:
        start_idx = content.index(SCAN_SECTION_START)
        # Suche nach nächster H2 nach dem Scan-Abschnitt
        after = content[start_idx + len(SCAN_SECTION_START):]
        next_h2 = after.find("\n## ")
        if next_h2 >= 0:
            # Abschnitt ersetzen, Rest behalten
            end_idx = start_idx + len(SCAN_SECTION_START) + next_h2
            content = content[:start_idx] + report + "\n" + content[end_idx:]
        else:
            # Letzter Abschnitt — alles ab hier ersetzen
            content = content[:start_idx] + report + "\n"
    else:
        # Noch kein Scan-Abschnitt — ans Ende anhängen
        content = content.rstrip() + "\n\n" + report + "\n"

    WIKI_FILE.write_text(content, encoding="utf-8")
    print(f"✓ Wiki-Datei aktualisiert: {WIKI_FILE.relative_to(REPO_ROOT)}")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Kartograph Frontend-Scanner")
    parser.add_argument(
        "--update", action="store_true",
        help="Aktualisiert seed/wiki/frontend-component-architektur.md"
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Exit-Code 1 wenn Verletzungen > 0 (für CI-Gates)"
    )
    args = parser.parse_args()

    if not FRONTEND_SRC.exists():
        print(f"ERROR: Frontend-Quellverzeichnis nicht gefunden: {FRONTEND_SRC}", file=sys.stderr)
        sys.exit(1)

    print(f"Scanne: {FRONTEND_SRC}")
    metrics = scan_vue_files()
    report = format_report(metrics)

    print(report)

    total_violations = (
        metrics["hex_colors"]
        + metrics["rgba_values"]
        + metrics["hardcoded_px_padding"]
        + metrics["hardcoded_px_radius"]
        + len(metrics["files_with_btn"])
        + len(metrics["files_with_badge"])
    )

    print(f"\n{'─' * 60}")
    print(f"Total Violations: {total_violations}")
    print(f"UI Components:    {len(metrics['ui_components'])}")
    print(f"Scan-Datum:       {metrics['scan_date']}")

    if args.update:
        update_wiki_file(report)

    if args.check and total_violations > 0:
        print(f"\nFEHLER: {total_violations} Design-System-Verletzungen gefunden.", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
