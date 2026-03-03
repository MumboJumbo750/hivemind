#!/usr/bin/env python3
"""
Hivemind Repo Health Scanner — CLI Entry Point

Usage:
    python scripts/health_check.py
    python scripts/health_check.py --root . --format markdown
    python scripts/health_check.py --analyzers hardcoded-css,magic-numbers --severity warning
    python scripts/health_check.py --format json --output report.json

Exit codes:
    0  — clean or only warnings/infos
    1  — at least one error found
    2  — usage / config error
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Allow running as `python scripts/health_check.py` from repo root
_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.analyzers import detect_stack, run_all  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="health_check",
        description="Hivemind Repo Health Scanner — analyses code quality issues.",
    )
    parser.add_argument(
        "--root",
        default=".",
        help="Repository root directory to scan (default: current directory).",
    )
    parser.add_argument(
        "--analyzers",
        default=None,
        help="Comma-separated list of analyzer names to run (default: all).",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json", "markdown", "sarif"],
        default="text",
        help="Output format (default: text).",
    )
    parser.add_argument(
        "--severity",
        choices=["error", "warning", "info"],
        default=None,
        help="Minimum severity to report (default: all).",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Write output to this file instead of stdout.",
    )
    parser.add_argument(
        "--stack",
        action="store_true",
        help="Only print detected stack and exit.",
    )

    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.is_dir():
        print(f"ERROR: --root '{args.root}' is not a directory.", file=sys.stderr)
        return 2

    # --stack shortcut
    if args.stack:
        stack = detect_stack(root)
        print("Detected stack:", ", ".join(sorted(stack)) or "(none)")
        return 0

    analyzer_names: list[str] | None = None
    if args.analyzers:
        analyzer_names = [a.strip() for a in args.analyzers.split(",") if a.strip()]

    report = run_all(root, analyzers=analyzer_names, min_severity=args.severity)

    # Format output
    if args.format == "json":
        output = report.to_json()
    elif args.format == "markdown":
        output = report.to_markdown()
    elif args.format == "sarif":
        output = report.to_sarif()
    else:
        # text: compact human-readable
        output = _format_text(report)

    if args.output:
        Path(args.output).write_text(output, encoding="utf-8")
        print(f"Report written to {args.output}")
    else:
        print(output)

    # Exit code: 1 if any errors found
    return 1 if report.summary.errors > 0 else 0


def _format_text(report) -> str:
    from scripts.analyzers import SEVERITY_ORDER

    lines = [
        f"Hivemind Health Scanner",
        f"Root    : {report.root_path}",
        f"Stack   : {', '.join(sorted(report.stack)) or 'unknown'}",
        f"Time    : {report.timestamp}",
        f"",
        f"Summary : {report.summary.errors} errors, "
        f"{report.summary.warnings} warnings, "
        f"{report.summary.infos} infos "
        f"({report.summary.auto_fixable} auto-fixable)",
        f"",
    ]

    if not report.findings:
        lines.append("✓ No issues found.")
        return "\n".join(lines)

    sorted_findings = sorted(
        report.findings,
        key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.file, f.line or 0),
    )
    for f in sorted_findings:
        icon = {"error": "✗", "warning": "⚠", "info": "·"}.get(f.severity, "?")
        loc = f.file + (f":{f.line}" if f.line else "")
        fix = " [auto-fixable]" if f.auto_fixable else ""
        lines.append(f"  {icon} [{f.severity:7s}] {loc}  {f.message}  ({f.category}){fix}")

    return "\n".join(lines)


if __name__ == "__main__":
    sys.exit(main())
