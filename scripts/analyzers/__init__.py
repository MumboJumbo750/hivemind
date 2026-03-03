"""
Hivemind Repo Health Scanner — Framework Core

Zero external dependencies (stdlib only: abc, dataclasses, pathlib, re, json, datetime).

Usage:
    from scripts.analyzers import run_all, detect_stack

    report = run_all(Path("."))
    print(report.to_json())
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import ClassVar

# ─── Data Types ──────────────────────────────────────────────────────────────

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Finding:
    """A single issue found by an analyzer."""

    analyzer: str
    severity: str          # "error" | "warning" | "info"
    file: str              # relative path from root
    line: int | None       # 1-based, None if not applicable
    message: str
    category: str          # e.g. "hardcoded-css", "magic-number", "duplicate"
    auto_fixable: bool = False

    def as_dict(self) -> dict:
        return {
            "analyzer": self.analyzer,
            "severity": self.severity,
            "file": self.file,
            "line": self.line,
            "message": self.message,
            "category": self.category,
            "auto_fixable": self.auto_fixable,
        }


@dataclass
class Summary:
    total: int = 0
    errors: int = 0
    warnings: int = 0
    infos: int = 0
    auto_fixable: int = 0

    def as_dict(self) -> dict:
        return {
            "total": self.total,
            "errors": self.errors,
            "warnings": self.warnings,
            "infos": self.infos,
            "auto_fixable": self.auto_fixable,
        }


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    summary: Summary = field(default_factory=Summary)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    root_path: str = "."
    stack: set[str] = field(default_factory=set)

    def _recompute_summary(self) -> None:
        s = Summary()
        s.total = len(self.findings)
        for f in self.findings:
            if f.severity == "error":
                s.errors += 1
            elif f.severity == "warning":
                s.warnings += 1
            else:
                s.infos += 1
            if f.auto_fixable:
                s.auto_fixable += 1
        self.summary = s

    def to_json(self) -> str:
        import json
        self._recompute_summary()
        return json.dumps(
            {
                "timestamp": self.timestamp,
                "root_path": self.root_path,
                "stack": sorted(self.stack),
                "summary": self.summary.as_dict(),
                "findings": [f.as_dict() for f in self.findings],
            },
            indent=2,
            ensure_ascii=False,
        )

    def to_markdown(self) -> str:
        self._recompute_summary()
        lines = [
            f"# Repo Health Report",
            f"",
            f"**Generated:** {self.timestamp}  ",
            f"**Root:** `{self.root_path}`  ",
            f"**Stack:** {', '.join(sorted(self.stack)) or 'unknown'}",
            f"",
            f"## Summary",
            f"",
            f"| Severity | Count |",
            f"|----------|-------|",
            f"| 🔴 Error   | {self.summary.errors} |",
            f"| 🟡 Warning | {self.summary.warnings} |",
            f"| 🔵 Info    | {self.summary.infos} |",
            f"| **Total**  | **{self.summary.total}** |",
            f"| Auto-fixable | {self.summary.auto_fixable} |",
            f"",
        ]

        if not self.findings:
            lines.append("✅ No issues found.")
            return "\n".join(lines)

        lines.append("## Findings")
        lines.append("")

        by_severity = sorted(self.findings, key=lambda f: (SEVERITY_ORDER.get(f.severity, 99), f.file, f.line or 0))
        current_sev = None
        for finding in by_severity:
            if finding.severity != current_sev:
                current_sev = finding.severity
                icon = {"error": "🔴", "warning": "🟡", "info": "🔵"}.get(current_sev, "⚪")
                lines.append(f"### {icon} {current_sev.capitalize()}")
                lines.append("")
            loc = f"`{finding.file}`" + (f":{finding.line}" if finding.line else "")
            fix = " *(auto-fixable)*" if finding.auto_fixable else ""
            lines.append(f"- **{finding.category}** — {loc}: {finding.message}{fix}")

        return "\n".join(lines)

    def to_sarif(self) -> str:
        """SARIF 2.1.0 output for CI integration."""
        import json
        self._recompute_summary()

        rules: dict[str, dict] = {}
        results = []

        for f in self.findings:
            rule_id = f"{f.analyzer}/{f.category}"
            if rule_id not in rules:
                rules[rule_id] = {
                    "id": rule_id,
                    "name": f.category,
                    "shortDescription": {"text": f.category},
                }
            level = {"error": "error", "warning": "warning", "info": "note"}.get(f.severity, "none")
            result: dict = {
                "ruleId": rule_id,
                "level": level,
                "message": {"text": f.message},
                "locations": [
                    {
                        "physicalLocation": {
                            "artifactLocation": {"uri": f.file},
                            **({"region": {"startLine": f.line}} if f.line else {}),
                        }
                    }
                ],
            }
            results.append(result)

        sarif = {
            "$schema": "https://raw.githubusercontent.com/oasis-tcs/sarif-spec/master/Schemata/sarif-schema-2.1.0.json",
            "version": "2.1.0",
            "runs": [
                {
                    "tool": {
                        "driver": {
                            "name": "hivemind-health-scanner",
                            "version": "1.0.0",
                            "rules": list(rules.values()),
                        }
                    },
                    "results": results,
                }
            ],
        }
        return json.dumps(sarif, indent=2, ensure_ascii=False)


# ─── Base Analyzer ────────────────────────────────────────────────────────────


class BaseAnalyzer(ABC):
    """Abstract base class for all analyzers. Subclass and implement analyze()."""

    name: ClassVar[str] = ""
    description: ClassVar[str] = ""

    @abstractmethod
    def analyze(self, root: Path) -> list[Finding]:
        """Run analysis on the repo rooted at *root*. Return list of findings."""
        ...

    def _rel(self, root: Path, path: Path) -> str:
        """Return a POSIX-style relative path string."""
        try:
            return path.relative_to(root).as_posix()
        except ValueError:
            return path.as_posix()


# ─── Stack Detection ──────────────────────────────────────────────────────────

_SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__",
    ".mypy_cache", ".pytest_cache", "dist", "build", ".next",
}

_STACK_MARKERS: list[tuple[str, str]] = [
    # (glob_pattern, stack_name)
    ("package.json", "nodejs"),
    ("tsconfig.json", "typescript"),
    ("vite.config.*", "vite"),
    ("vue.config.*", "vue"),
    ("src/main.ts", "vue"),
    ("src/App.vue", "vue"),
    ("next.config.*", "nextjs"),
    ("react", "react"),           # checked via package.json content
    ("pyproject.toml", "python"),
    ("requirements*.txt", "python"),
    ("setup.py", "python"),
    ("Pipfile", "python"),
    ("go.mod", "go"),
    ("Cargo.toml", "rust"),
    ("pom.xml", "java"),
    ("build.gradle", "java"),
]


def _find_file(root: Path, pattern: str) -> bool:
    """Return True if *pattern* matches any file under *root*, skipping junk dirs."""
    for path in root.iterdir():
        if path.is_dir():
            if path.name in _SKIP_DIRS:
                continue
            # one level deep sub-search (avoids full rglob)
            for sub in path.iterdir():
                if sub.is_file() and sub.match(pattern):
                    return True
        elif path.is_file() and path.match(pattern):
            return True
    return False


def detect_stack(root: Path) -> set[str]:
    """Detect the technology stack present under *root*."""
    stack: set[str] = set()

    for pattern, name in _STACK_MARKERS:
        if name == "react":
            continue  # handled below via package.json
        if _find_file(root, pattern):
            stack.add(name)

    # Detect React / Vue more precisely from package.json (root + 1 subdir)
    pkg_candidates = [root / "package.json"] + [
        d / "package.json"
        for d in root.iterdir()
        if d.is_dir() and d.name not in _SKIP_DIRS
    ]
    for pkg in pkg_candidates:
        if not pkg.exists():
            continue
        try:
            import json
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {
                **data.get("dependencies", {}),
                **data.get("devDependencies", {}),
            }
            if "react" in deps or "react-dom" in deps:
                stack.add("react")
            if "vue" in deps:
                stack.add("vue")
            if "typescript" in deps or "ts-node" in deps:
                stack.add("typescript")
            if "vite" in deps:
                stack.add("vite")
            if "next" in deps:
                stack.add("nextjs")
        except Exception:
            pass

    # Vue SFC files
    if _find_file(root, "*.vue"):
        stack.add("vue")

    # TypeScript files
    if _find_file(root, "*.ts"):
        stack.add("typescript")

    return stack


# ─── Analyzer Registry ────────────────────────────────────────────────────────


class AnalyzerRegistry:
    """Auto-discovers all BaseAnalyzer subclasses in this package."""

    _analyzers: list[type[BaseAnalyzer]] | None = None

    @classmethod
    def discover(cls) -> list[type[BaseAnalyzer]]:
        """Return all registered BaseAnalyzer subclasses (auto-import from package)."""
        if cls._analyzers is not None:
            return cls._analyzers

        package_path = Path(__file__).parent
        package_name = __name__  # e.g. "scripts.analyzers" or "__main__"

        # Import all sibling modules so their classes get registered
        for _, module_name, _ in pkgutil.iter_modules([str(package_path)]):
            full_name = f"{package_name}.{module_name}" if "." in package_name else module_name
            try:
                importlib.import_module(f"scripts.analyzers.{module_name}")
            except ImportError:
                try:
                    importlib.import_module(module_name)
                except ImportError:
                    pass

        cls._analyzers = [
            sub for sub in _all_subclasses(BaseAnalyzer)
            if sub.name  # skip abstract intermediates without a name
        ]
        return cls._analyzers

    @classmethod
    def reset(cls) -> None:
        """Clear cache (for testing)."""
        cls._analyzers = None


def _all_subclasses(cls: type) -> list[type]:
    result = []
    for sub in cls.__subclasses__():
        result.append(sub)
        result.extend(_all_subclasses(sub))
    return result


# ─── run_all ──────────────────────────────────────────────────────────────────


def run_all(
    root: Path,
    analyzers: list[str] | None = None,
    min_severity: str | None = None,
) -> Report:
    """
    Run all (or selected) analyzers against *root*.

    :param root:         Repo root directory.
    :param analyzers:    Optional list of analyzer names to run (default: all).
    :param min_severity: Filter findings to this severity and above
                         ("error" | "warning" | "info").
    :returns:            Populated Report.
    """
    root = root.resolve()
    stack = detect_stack(root)
    registered = AnalyzerRegistry.discover()

    if analyzers:
        registered = [a for a in registered if a.name in analyzers]

    all_findings: list[Finding] = []
    for analyzer_cls in registered:
        try:
            instance = analyzer_cls()
            findings = instance.analyze(root)
            all_findings.extend(findings)
        except Exception as exc:
            # Never crash the whole run due to one broken analyzer
            all_findings.append(
                Finding(
                    analyzer="framework",
                    severity="warning",
                    file="<analyzer>",
                    line=None,
                    message=f"Analyzer '{analyzer_cls.name}' raised an exception: {exc}",
                    category="analyzer-error",
                )
            )

    if min_severity and min_severity in SEVERITY_ORDER:
        threshold = SEVERITY_ORDER[min_severity]
        all_findings = [f for f in all_findings if SEVERITY_ORDER.get(f.severity, 99) <= threshold]

    report = Report(
        findings=all_findings,
        root_path=str(root),
        stack=stack,
    )
    report._recompute_summary()
    return report
