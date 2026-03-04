"""
Analyzer: Layer Violations (Architecture Boundary Checks)

Detects forbidden cross-layer imports based on a configurable rule set.

Built-in rules (migrated from arch-check.py):
  - BE: Router modules must not import from app.models.*
  - FE: UI primitive components must not import from stores or API modules
  - FE: Vue composables must not import Vue components
  - BE: Service modules must not import from app.routers.* (circular)

Custom rules via constructor:
  extra_rules : list[LayerRule] (dataclass with layer/file_pattern/forbidden_imports/message)

Rule format::

    LayerRule(
        name="router-no-models",
        file_pattern="backend/app/routers/*.py",   # glob relative to root
        forbidden_imports=["app.models."],          # substring match in import lines
        message="Router must not import Model directly — use Service or Schema",
        severity="error",
    )

Registered automatically via AnalyzerRegistry (BaseAnalyzer subclass).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

from scripts.analyzers import BaseAnalyzer, Finding

# ─── Rule definition ──────────────────────────────────────────────────────────


@dataclass
class LayerRule:
    name: str
    file_pattern: str           # glob pattern relative to root (e.g. "backend/app/routers/*.py")
    forbidden_imports: list[str]  # substring patterns — any match in an import line triggers
    message: str
    severity: str = "error"     # "error" | "warning" | "info"
    skip_filenames: list[str] = field(default_factory=list)  # e.g. ["__init__.py", "deps.py"]


# ─── Built-in rules ───────────────────────────────────────────────────────────

_BUILTIN_RULES: list[LayerRule] = [
    # BE: Routers must not import ORM models directly
    LayerRule(
        name="be-router-no-models",
        file_pattern="backend/app/routers/*.py",
        forbidden_imports=["from app.models.", "import app.models."],
        message="Router imports Model directly — use Service or Schema instead",
        severity="error",
        skip_filenames=["__init__.py", "deps.py"],
    ),
    # BE: Services must not import from routers (circular dependency)
    LayerRule(
        name="be-service-no-router",
        file_pattern="backend/app/services/*.py",
        forbidden_imports=["from app.routers.", "import app.routers."],
        message="Service imports Router — circular dependency",
        severity="error",
        skip_filenames=["__init__.py"],
    ),
    # FE: UI primitive components must not import stores or API
    LayerRule(
        name="fe-ui-no-store",
        file_pattern="frontend/src/components/ui/*.vue",
        forbidden_imports=["from '@/stores/", 'from "@/stores/', "from '../stores/", 'from "../../stores/'],
        message="UI primitive imports Store — violates presentational component boundary",
        severity="error",
    ),
    LayerRule(
        name="fe-ui-no-api",
        file_pattern="frontend/src/components/ui/*.vue",
        forbidden_imports=["from '@/api", 'from "@/api', "/api/", "useProjectStore", "useSettingsStore"],
        message="UI primitive imports API or domain Store — violates presentational component boundary",
        severity="error",
    ),
    # FE: Vue composables must not import Vue SFC components
    LayerRule(
        name="fe-composable-no-component",
        file_pattern="frontend/src/composables/*.ts",
        forbidden_imports=["from '@/components/", 'from "@/components/', "from '../components/"],
        message="Composable imports Vue component — composables should be component-agnostic",
        severity="warning",
    ),
]

# ─── Import line detection ────────────────────────────────────────────────────

_PY_IMPORT_RE = re.compile(r"^\s*(from\s+\S+\s+import|import\s+\S+)")
_TS_IMPORT_RE = re.compile(r"""^\s*import\s+(?:(?:\{[^}]*\}|\*\s+as\s+\w+|\w+)\s+from\s+)?['"]""")


def _is_import_line(line: str, suffix: str) -> bool:
    if suffix == ".py":
        return bool(_PY_IMPORT_RE.match(line))
    return bool(_TS_IMPORT_RE.match(line))


# ─── Analyzer ─────────────────────────────────────────────────────────────────


class LayerViolationsAnalyzer(BaseAnalyzer):
    """Checks architecture layer boundaries via configurable import rules."""

    name = "layer-violations"
    description = (
        "Detects forbidden cross-layer imports (Router→Model, Service→Router, "
        "UI primitive→Store/API, Composable→Component)."
    )

    def __init__(self, extra_rules: Sequence[LayerRule] | None = None) -> None:
        self._rules: list[LayerRule] = list(_BUILTIN_RULES)
        if extra_rules:
            self._rules.extend(extra_rules)

    def analyze(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        root = root.resolve()

        for rule in self._rules:
            # Expand glob pattern relative to root
            matched_files = list(root.glob(rule.file_pattern))

            for path in matched_files:
                if not path.is_file():
                    continue
                if path.name in rule.skip_filenames:
                    continue

                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                except OSError:
                    continue

                rel = self._rel(root, path)
                suffix = path.suffix

                for lineno, line in enumerate(text.splitlines(), 1):
                    # Only inspect import lines for performance
                    stripped = line.strip()
                    if not stripped:
                        continue
                    # For Python files, check only import statements
                    # For TS/Vue, check import statements
                    # We still scan all lines with forbidden pattern to catch re-exports etc.
                    for forbidden in rule.forbidden_imports:
                        if forbidden in line:
                            findings.append(
                                Finding(
                                    analyzer=self.name,
                                    severity=rule.severity,
                                    file=rel,
                                    line=lineno,
                                    message=f"[{rule.name}] {rule.message}",
                                    category="layer-violation",
                                )
                            )
                            break  # one finding per line per rule

        return findings
