#!/usr/bin/env python3
"""Exportiert das FastAPI OpenAPI-Schema statisch als openapi.json in den Repo-Root."""
import json
import sys
from pathlib import Path

# Repo-Root relativ zu diesem Script ermitteln
REPO_ROOT = Path(__file__).parent.parent.parent

# Backend-Paket importierbar machen
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.main import app

schema = app.openapi()
output_path = REPO_ROOT / "openapi.json"
output_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False))
print(f"OpenAPI schema written to {output_path}")
