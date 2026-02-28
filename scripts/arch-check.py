#!/usr/bin/env python3
"""
Hivemind Architecture & Quality Guard
======================================
Prüft:
  1. Dateigrößen        — Warn bei >300 Zeilen, Error bei >500
  2. Layer-Grenzen FE   — UI-Primitives importieren keine Stores/API
  3. Design-Tokens FE   — Keine hardcodierten Hex-Farben in Vue-Styles
  4. Layer-Grenzen BE   — Router importieren keine ORM-Models direkt

Exit-Code: 0 = alles OK, 1 = Errors gefunden
"""
import re
import sys
from pathlib import Path

# Windows-kompatible Ausgabe
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

ROOT = Path(__file__).parent.parent

WARN_LINES = 300
ERROR_LINES = 500

# Dateien/Ordner die nicht geprüft werden
IGNORE_PATTERNS = [
    "node_modules", "dist", ".venv", "__pycache__",
    "src/api/client",          # generierter API-Client
    "alembic/versions",        # generierte Migrations
    "src/design/tokens.css",   # viele Zeilen durch Primitiv-Skala – OK
]

errors: list[str] = []
warnings: list[str] = []


def is_ignored(path: Path) -> bool:
    parts = path.parts
    return any(ig in parts or any(ig in str(path) for _ in [1]) for ig in IGNORE_PATTERNS)


def collect_files(base: Path, extensions: tuple[str, ...]) -> list[Path]:
    return [
        p for p in base.rglob("*")
        if p.suffix in extensions and not is_ignored(p)
    ]


# ── 1. Dateigrößen ────────────────────────────────────────────────────────────

def check_file_sizes() -> None:
    exts = (".ts", ".vue", ".py", ".css")
    files = collect_files(ROOT / "frontend" / "src", (".ts", ".vue", ".css"))
    files += collect_files(ROOT / "backend" / "app", (".py",))

    for path in files:
        lines = len(path.read_text(encoding="utf-8", errors="ignore").splitlines())
        rel = path.relative_to(ROOT)
        if lines > ERROR_LINES:
            errors.append(f"[size] {rel}: {lines} Zeilen (Limit: {ERROR_LINES})")
        elif lines > WARN_LINES:
            warnings.append(f"[size] {rel}: {lines} Zeilen (Empfehlung: <{WARN_LINES})")


# ── 2. FE Layer: UI-Primitives ohne Store/API ─────────────────────────────────

UI_PRIMITIVES_DIR = ROOT / "frontend" / "src" / "components" / "ui"
FORBIDDEN_IN_UI = [
    (re.compile(r"from ['\"].*\/stores\/"), "Store-Import in UI-Primitive"),
    (re.compile(r"from ['\"].*\/api['\"/]"),  "API-Import in UI-Primitive"),
    (re.compile(r"useProjectStore|useSettingsStore"), "Domain-Store in UI-Primitive"),
]

def check_fe_layer_boundaries() -> None:
    for path in UI_PRIMITIVES_DIR.rglob("*.vue"):
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        for pattern, msg in FORBIDDEN_IN_UI:
            if pattern.search(text):
                errors.append(f"[arch:fe] {rel}: {msg}")


# ── 3. FE Design-Tokens: keine hardcodierten Hex-Farben in Scoped Styles ──────

# Hex-Farben im CSS innerhalb von <style>-Blöcken
HEX_COLOR_RE = re.compile(r":\s*#[0-9a-fA-F]{3,8}\b")
# Ausnahmen: Datei ist eine Theme-Datei oder Semantic-Datei (die DEFINIEREN Werte)
STYLE_DEFINITION_FILES = {
    ROOT / "frontend" / "src" / "design" / "tokens.css",
    ROOT / "frontend" / "src" / "design" / "semantic.css",
    *(ROOT / "frontend" / "src" / "design" / "themes").glob("*.css"),
}

def check_fe_hardcoded_colors() -> None:
    # Nur components/ prüfen — Views dürfen intentionale Hex-Werte haben (z.B. Theme-Preview)
    vue_files = collect_files(ROOT / "frontend" / "src" / "components", (".vue",))
    css_files = collect_files(ROOT / "frontend" / "src" / "components", (".css",))

    for path in vue_files + css_files:
        if path in STYLE_DEFINITION_FILES:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        # Nur in <style>-Blöcken suchen (bei .vue-Dateien)
        if path.suffix == ".vue":
            style_match = re.search(r"<style[^>]*>(.*?)</style>", text, re.DOTALL)
            if not style_match:
                continue
            text = style_match.group(1)

        for i, line in enumerate(text.splitlines(), 1):
            if HEX_COLOR_RE.search(line) and "var(--" not in line:
                rel = path.relative_to(ROOT)
                errors.append(
                    f"[arch:fe] {rel}:{i}: Hardcodierte Hex-Farbe — bitte CSS-Variable verwenden"
                )
                break  # nur erste Fundstelle pro Datei melden


# ── 4. BE Layer: Router importieren keine Models direkt ───────────────────────

ROUTERS_DIR = ROOT / "backend" / "app" / "routers"
DIRECT_MODEL_IMPORT_RE = re.compile(r"from app\.models\.")

def check_be_layer_boundaries() -> None:
    for path in ROUTERS_DIR.glob("*.py"):
        if path.name in ("__init__.py", "deps.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = path.relative_to(ROOT)
        for i, line in enumerate(text.splitlines(), 1):
            if DIRECT_MODEL_IMPORT_RE.search(line):
                errors.append(
                    f"[arch:be] {rel}:{i}: Router importiert Model direkt — "
                    f"bitte über Service oder Schema gehen"
                )


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    check_file_sizes()
    check_fe_layer_boundaries()
    check_fe_hardcoded_colors()
    check_be_layer_boundaries()

    if warnings:
        print("\n⚠  WARNINGS")
        for w in warnings:
            print(f"   {w}")

    if errors:
        print("\n✗  ERRORS")
        for e in errors:
            print(f"   {e}")
        print(f"\n{len(errors)} error(s), {len(warnings)} warning(s) — EXIT 1\n")
        return 1

    print(f"\n✓  arch-check passed — 0 errors, {len(warnings)} warning(s)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
