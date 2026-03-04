"""
Analyzer: File Size & Cyclomatic Complexity Hints

Detects:
  - Files exceeding configurable line-count thresholds (warn / error)
  - Python functions with high cyclomatic complexity (>20 branches)

Configuration (constructor args or per-file-type overrides):
  thresholds : dict mapping file-type glob suffix → (warn_lines, error_lines)
               Default: {"test": (500, 800), "*": (300, 500)}
               Keys: "test" matches test files (*/tests/* or *.test.* or *_test.*)
  complexity_threshold : int — branch count that triggers a complexity hint (default: 20)

Registered automatically via AnalyzerRegistry (BaseAnalyzer subclass).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from scripts.analyzers import BaseAnalyzer, Finding

# ─── Defaults ────────────────────────────────────────────────────────────────

_DEFAULT_WARN = 300
_DEFAULT_ERROR = 500
_DEFAULT_TEST_WARN = 500
_DEFAULT_TEST_ERROR = 800
_DEFAULT_COMPLEXITY = 20

_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules", ".git", ".venv", "venv", "__pycache__",
        "dist", "build", ".next", "coverage", "out",
        "src/api/client",   # generated API client
        "alembic/versions", # generated migrations
    }
)

_TARGET_EXTS: frozenset[str] = frozenset({".py", ".ts", ".vue", ".css", ".scss"})

_IS_TEST_RE = re.compile(
    r"(?:^|[/\\])tests?[/\\]|"
    r"\.(test|spec)\.[jt]sx?$|"
    r"_test\.py$",
    re.IGNORECASE,
)

# ─── Cyclomatic Complexity ────────────────────────────────────────────────────


def _count_branches(node: ast.AST) -> int:
    """Count decision points in a function AST node (simplified cyclomatic)."""
    count = 0
    for child in ast.walk(node):
        if isinstance(child, (
            ast.If, ast.While, ast.For, ast.ExceptHandler,
            ast.With, ast.Assert, ast.comprehension,
        )):
            count += 1
        elif isinstance(child, ast.BoolOp):
            # each `and`/`or` adds one path
            count += len(child.values) - 1
        elif isinstance(child, ast.IfExp):
            count += 1
    return count


def _check_complexity(path: Path, root: Path, threshold: int) -> list[Finding]:
    """Return complexity findings for all functions/methods in a Python file."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    findings: list[Finding] = []
    rel = path.relative_to(root).as_posix()

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            branches = _count_branches(node)
            if branches > threshold:
                findings.append(
                    Finding(
                        analyzer="file-size",
                        severity="info",
                        file=rel,
                        line=node.lineno,
                        message=(
                            f"Function '{node.name}' has ~{branches} branches "
                            f"(threshold: {threshold}) — consider splitting"
                        ),
                        category="complexity",
                    )
                )

    return findings


# ─── Analyzer ─────────────────────────────────────────────────────────────────


class FileSizeAnalyzer(BaseAnalyzer):
    """Checks file sizes and Python cyclomatic complexity."""

    name = "file-size"
    description = (
        "Reports files exceeding line-count thresholds and Python functions "
        "with high cyclomatic complexity."
    )

    def __init__(
        self,
        warn_lines: int = _DEFAULT_WARN,
        error_lines: int = _DEFAULT_ERROR,
        test_warn_lines: int = _DEFAULT_TEST_WARN,
        test_error_lines: int = _DEFAULT_TEST_ERROR,
        complexity_threshold: int = _DEFAULT_COMPLEXITY,
    ) -> None:
        self.warn_lines = warn_lines
        self.error_lines = error_lines
        self.test_warn_lines = test_warn_lines
        self.test_error_lines = test_error_lines
        self.complexity_threshold = complexity_threshold

    def _is_skipped(self, path: Path, root: Path) -> bool:
        rel = str(path.relative_to(root))
        for skip in _SKIP_DIRS:
            if skip in rel.replace("\\", "/"):
                return True
        return False

    def _thresholds(self, path: Path) -> tuple[int, int]:
        """Return (warn, error) line thresholds for the given path."""
        rel = path.as_posix()
        if _IS_TEST_RE.search(rel):
            return self.test_warn_lines, self.test_error_lines
        return self.warn_lines, self.error_lines

    def analyze(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        root = root.resolve()

        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix not in _TARGET_EXTS:
                continue
            if self._is_skipped(path, root):
                continue

            rel = self._rel(root, path)
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue

            line_count = len(text.splitlines())
            warn_limit, error_limit = self._thresholds(path)

            if line_count > error_limit:
                findings.append(
                    Finding(
                        analyzer=self.name,
                        severity="error",
                        file=rel,
                        line=None,
                        message=(
                            f"File has {line_count} lines — exceeds error limit of {error_limit}"
                        ),
                        category="file-too-large",
                    )
                )
            elif line_count > warn_limit:
                findings.append(
                    Finding(
                        analyzer=self.name,
                        severity="warning",
                        file=rel,
                        line=None,
                        message=(
                            f"File has {line_count} lines — exceeds warning limit of {warn_limit}"
                        ),
                        category="file-too-large",
                    )
                )

            # Cyclomatic complexity only for Python files
            if path.suffix == ".py":
                findings.extend(_check_complexity(path, root, self.complexity_threshold))

        return findings
