#!/usr/bin/env python3
"""hivemind init — Konfiguration für externe Repos.

Generiert:
  - docker-compose.override.yml  (Workspace-Mount in den backend-Container)
  - .vscode/mcp.json             (Copilot Agent Mode — MCP-Server-Eintrag)
  - .hivemind/config.yml         (Workspace-Einstellungen)

Verwendung (vom hivemind-Projekt-Root aus):
  python scripts/hivemind_init.py --workspace /path/to/your/repo
  python scripts/hivemind_init.py --workspace /path/to/your/repo --port 8000 --dry-run

Die generierten Dateien werden im Verzeichnis des hivemind-Repos abgelegt
(docker-compose.override.yml) bzw. im Ziel-Workspace (.vscode/, .hivemind/).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from textwrap import dedent

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "backend"))

from app.services.onboarding_templates import (
    DEFAULT_ONBOARDING_DENY_PATTERNS,
    DEFAULT_ONBOARDING_PORT,
    DEFAULT_WORKSPACE_ROOT_CONTAINER,
    cursor_mcp_json,
    docker_compose_override,
    hivemind_config_yml,
    vscode_mcp_json,
)


# ── Writer ────────────────────────────────────────────────────────────────

def _write(path: Path, content: str, dry_run: bool) -> None:
    """Schreibt Datei — oder gibt Vorschau aus bei dry_run."""
    if dry_run:
        print(f"\n{'='*60}")
        print(f"[DRY-RUN] Würde schreiben: {path}")
        print('='*60)
        print(content)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        print(f"  ⚠️  Überschreibe: {path}")
    else:
        print(f"  ✅  Erstelle:    {path}")
    path.write_text(content, encoding="utf-8")


# ── Main ──────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Hivemind init — Workspace-Konfiguration für externe Repos",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=dedent("""\
            Beispiele:
              python scripts/hivemind_init.py --workspace /path/to/myproject
              python scripts/hivemind_init.py --workspace /path/to/myproject --port 8001 --dry-run
              python scripts/hivemind_init.py --workspace /path/to/myproject --vscode-only
        """),
    )
    ap.add_argument(
        "--workspace", "-w",
        required=True,
        help="Absoluter Pfad zum externen Repository (Host-Pfad).",
    )
    ap.add_argument(
        "--container-path",
        default=DEFAULT_WORKSPACE_ROOT_CONTAINER,
        help=f"Container-interner Pfad (HIVEMIND_WORKSPACE_ROOT). Default: {DEFAULT_WORKSPACE_ROOT_CONTAINER}",
    )
    ap.add_argument(
        "--port", "-p",
        type=int,
        default=DEFAULT_ONBOARDING_PORT,
        help=f"Port des Hivemind-MCP-Servers. Default: {DEFAULT_ONBOARDING_PORT}",
    )
    ap.add_argument(
        "--deny-patterns",
        default=DEFAULT_ONBOARDING_DENY_PATTERNS,
        help="Kommagetrennte Deny-Patterns. Default: .git/objects,.env,...",
    )
    ap.add_argument(
        "--output-dir",
        default=None,
        help="Hivemind-Root-Verzeichnis für docker-compose.override.yml. "
             "Default: aktuelles Verzeichnis.",
    )
    ap.add_argument(
        "--vscode-only",
        action="store_true",
        help="Nur .vscode/mcp.json im Workspace generieren (kein docker-compose.override.yml).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Keine Dateien schreiben — nur Vorschau ausgeben.",
    )
    args = ap.parse_args()

    workspace_host = str(Path(args.workspace).resolve())
    container_path = args.container_path
    port = args.port
    deny_patterns = args.deny_patterns
    hivemind_root = Path(args.output_dir).resolve() if args.output_dir else Path.cwd()
    workspace_path = Path(workspace_host)
    dry_run: bool = args.dry_run

    print(f"\n🐝  Hivemind Init")
    print(f"   Workspace:       {workspace_host}")
    print(f"   Container-Pfad:  {container_path}")
    print(f"   MCP-Port:        {port}")
    print(f"   Hivemind-Root:   {hivemind_root}")
    print()

    if not workspace_path.is_dir() and not dry_run:
        print(f"❌  Fehler: Workspace nicht gefunden: {workspace_host}", file=sys.stderr)
        sys.exit(1)

    # 1. docker-compose.override.yml (im hivemind-Root)
    if not args.vscode_only:
        override_path = hivemind_root / "docker-compose.override.yml"
        _write(
            override_path,
            docker_compose_override(workspace_host, container_path, read_only=True),
            dry_run,
        )

    # 2. .vscode/mcp.json (im Ziel-Workspace)
    _write(
        workspace_path / ".vscode" / "mcp.json",
        vscode_mcp_json(port),
        dry_run,
    )

    # 3. .cursor/mcp.json (im Ziel-Workspace)
    _write(
        workspace_path / ".cursor" / "mcp.json",
        cursor_mcp_json(port),
        dry_run,
    )

    # 4. .hivemind/config.yml (im Ziel-Workspace)
    _write(
        workspace_path / ".hivemind" / "config.yml",
        hivemind_config_yml(workspace_host, container_path, port, deny_patterns),
        dry_run,
    )

    if not dry_run:
        print()
        print("✅  Setup abgeschlossen!")
        print()
        print("Nächste Schritte:")
        print(f"  1. Hivemind stack neu starten:  make down && make up")
        print(f"  2. Backend prüfen:              curl http://localhost:{port}/health")
        print(f"  3. VS Code öffnen → Copilot Agent Mode aktivieren")
        print(f"  4. Discovery-Endpoint prüfen:   curl http://localhost:{port}/api/mcp/discovery")
        print()
        print("Dokumentation: docs/setup-external-repo.md")


if __name__ == "__main__":
    main()
