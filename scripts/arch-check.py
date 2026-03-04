#!/usr/bin/env python3
"""
Hivemind Architecture & Quality Guard (Wrapper)
================================================
This script now delegates to the Hivemind Repo Health Scanner framework.

Analyzers run:
  - file-size          (FileSizeAnalyzer)      — previously checks 1 (file sizes)
  - layer-violations   (LayerViolationsAnalyzer) — previously checks 2 + 4 (FE/BE layers)
  - hardcoded-css      (HardcodedCssAnalyzer)  — previously check 3 (hardcoded colors)

Exit codes:
  0 = no errors
  1 = at least one error-severity finding

For detailed JSON/Markdown output use the health scanner directly:
  make health          # text summary
  make health-json     # JSON → health_report.json
  make health-md       # Markdown → health_report.md
"""
import sys
from pathlib import Path

# Windows-kompatible Ausgabe
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]

# Ensure project root is on sys.path so `scripts.analyzers` is importable
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.analyzers import run_all  # noqa: E402


def main() -> int:
    report = run_all(
        ROOT,
        analyzers=["file-size", "layer-violations", "hardcoded-css"],
    )

    warnings_list = [f for f in report.findings if f.severity == "warning"]
    errors_list = [f for f in report.findings if f.severity == "error"]

    if warnings_list:
        print("\n⚠  WARNINGS")
        for w in warnings_list:
            loc = f"{w.file}:{w.line}" if w.line else w.file
            print(f"   [{w.category}] {loc}: {w.message}")

    if errors_list:
        print("\n✗  ERRORS")
        for e in errors_list:
            loc = f"{e.file}:{e.line}" if e.line else e.file
            print(f"   [{e.category}] {loc}: {e.message}")
        print(f"\n{len(errors_list)} error(s), {len(warnings_list)} warning(s) — EXIT 1\n")
        return 1

    print(f"\n✓  arch-check passed — 0 errors, {len(warnings_list)} warning(s)\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
