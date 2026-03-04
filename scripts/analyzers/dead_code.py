"""
Analyzer: Dead Code Hints (Heuristic)

Detects potential dead code using heuristics — all findings at severity "info".

Checks:
  1. TypeScript/JavaScript: non-exported top-level functions/classes/constants
     (declared without `export` keyword — may be dead if not used locally)
  2. Python: module-level functions not called within the same module and
     not referenced in `__all__`
  3. Unreferenced files: source files that are never imported/required from
     any other source file in the project

Caveats:
  - This is a HEURISTIC analyzer. False positives are expected:
    - Entry points (main.py, index.ts, app.ts) export nothing but are valid
    - Files used via dynamic import(), importlib, or side-effects
    - Functions called from templates or config files
  - All findings are severity "info" — review before acting

Suppression markers:
  Python  : # noqa: dead-code
  TS/JS   : // dead-code-ok

Registered automatically via AnalyzerRegistry (BaseAnalyzer subclass).
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

from scripts.analyzers import BaseAnalyzer, Finding

# ─── Skip patterns ────────────────────────────────────────────────────────────

_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules", ".git", ".venv", "venv", "__pycache__",
        "dist", "build", ".next", "coverage", "out",
        "alembic/versions",   # generated migration files
        "src/api/client",     # generated API client
    }
)

_SKIP_FILENAMES: frozenset[str] = frozenset(
    {
        "__init__.py",      # public surface — not dead by definition
        "conftest.py",      # pytest fixtures
        "main.py",          # entry points
        "app.py",
        "index.ts",         # TS entry points
        "index.js",
        "vite.config.ts",
        "vite.config.js",
    }
)

_ENTRY_POINT_RE = re.compile(
    r"(?:main|index|app|__init__|conftest|setup|settings|config)\.[pj][sy](?:x?)$",
    re.IGNORECASE,
)

# Suppression markers
_PY_NOQA_RE = re.compile(r"#\s*noqa\s*:.*\bdead-code\b", re.IGNORECASE)
_TS_DEAD_OK_RE = re.compile(r"//.*\bdead-code-ok\b", re.IGNORECASE)

_SOURCE_EXTS_PY: frozenset[str] = frozenset({".py"})
_SOURCE_EXTS_TS: frozenset[str] = frozenset({".ts", ".js", ".vue", ".tsx", ".jsx"})
_SOURCE_EXTS_ALL: frozenset[str] = _SOURCE_EXTS_PY | _SOURCE_EXTS_TS

# ─── TypeScript non-exported declarations ─────────────────────────────────────

# Matches top-level function/class/const that lacks `export`
_TS_DECLARATION_RE = re.compile(
    r"^(?!export\b)"                   # does NOT start with export
    r"(?:async\s+)?function\s+(\w+)"   # function name
    r"|^(?!export\b)class\s+(\w+)"     # class name
    r"|^(?!export\b)(?:const|let|var)\s+(\w+)\s*(?::\s*\S+\s*)?=",
    re.MULTILINE,
)

_TS_EXPORT_RE = re.compile(r"\bexport\b")


def _check_ts_unexported(path: Path, root: Path) -> list[Finding]:
    """Find top-level declarations in TS/JS/Vue without export keyword."""
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return []

    # For .vue files, extract <script> block
    if path.suffix == ".vue":
        m = re.search(r"<script[^>]*>(.*?)</script>", text, re.DOTALL)
        if not m:
            return []
        script_text = m.group(1)
        script_offset = text[: m.start(1)].count("\n")
    else:
        script_text = text
        script_offset = 0

    # If the file has a default export or uses defineComponent etc. as its main export,
    # likely not dead — but we still check individual named members.
    findings: list[Finding] = []
    rel = path.relative_to(root).as_posix()

    lines = script_text.splitlines()
    for lineno, line in enumerate(lines, 1):
        # Skip suppression lines
        if _TS_DEAD_OK_RE.search(line):
            continue
        # Only top-level (no leading whitespace) declarations without `export`
        if line and not line[0].isspace() and not _TS_EXPORT_RE.search(line):
            m2 = re.match(
                r"^(?:async\s+)?function\s+(\w+)|^class\s+(\w+)|^(?:const|let|var)\s+(\w+)",
                line,
            )
            if m2:
                name = next(g for g in m2.groups() if g)
                # Skip if the name appears elsewhere in the file (local usage)
                usage_pattern = re.compile(rf"\b{re.escape(name)}\b")
                usages = len(usage_pattern.findall(script_text))
                if usages <= 1:
                    findings.append(
                        Finding(
                            analyzer="dead-code",
                            severity="info",
                            file=rel,
                            line=lineno + script_offset,
                            message=(
                                f"'{name}' is not exported and appears to have no local usages "
                                f"— may be dead code (heuristic)"
                            ),
                            category="unexported-symbol",
                        )
                    )

    return findings


# ─── Python unused functions ───────────────────────────────────────────────────


def _get_py_all_names(tree: ast.Module) -> set[str]:
    """Extract names from __all__ if present."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(node.value, (ast.List, ast.Tuple)):
                        for elt in node.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                names.add(elt.value)
    return names


def _check_py_unused_functions(path: Path, root: Path) -> list[Finding]:
    """Find module-level functions that are never called in the same module."""
    try:
        source = path.read_text(encoding="utf-8", errors="ignore")
        tree = ast.parse(source, filename=str(path))
    except SyntaxError:
        return []

    all_names = _get_py_all_names(tree)
    rel = path.relative_to(root).as_posix()
    lines = source.splitlines()

    # Collect top-level function defs
    top_level_funcs: list[tuple[str, int]] = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            # Skip private/dunder
            if not node.name.startswith("_"):
                if node.name not in all_names:
                    top_level_funcs.append((node.name, node.lineno))

    findings: list[Finding] = []
    for func_name, lineno in top_level_funcs:
        # Check suppression comment on the def line
        def_line = lines[lineno - 1] if lineno <= len(lines) else ""
        if _PY_NOQA_RE.search(def_line):
            continue

        # Count calls: look for func_name( in the source.
        # The def line itself matches func_name( once, so we need >1 to confirm a real call.
        call_count = len(re.findall(rf"\b{re.escape(func_name)}\s*\(", source))
        if call_count <= 1:  # only the def line matched — no real call found
            findings.append(
                Finding(
                    analyzer="dead-code",
                    severity="info",
                    file=rel,
                    line=lineno,
                    message=(
                        f"Function '{func_name}' is not called within this module "
                        f"and not in __all__ — may be dead code (heuristic)"
                    ),
                    category="unused-function",
                )
            )

    return findings


# ─── Unreferenced files ────────────────────────────────────────────────────────

_PY_IMPORT_FROM_RE = re.compile(r"from\s+([\w.]+)\s+import|import\s+([\w.,\s]+)")
_TS_IMPORT_PATH_RE = re.compile(r"""(?:from|import)\s*['"]([^'"]+)['"]""")


def _collect_source_files(root: Path) -> list[Path]:
    """Collect all source files, skipping junk dirs."""
    result = []
    for p in root.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix not in _SOURCE_EXTS_ALL:
            continue
        parts = p.parts
        if any(skip in parts for skip in _SKIP_DIRS):
            continue
        if any(skip in str(p.relative_to(root)).replace("\\", "/") for skip in _SKIP_DIRS):
            continue
        result.append(p)
    return result


def _collect_referenced_stems(files: list[Path], root: Path) -> set[str]:
    """
    Collect all import-referenced file stems (without extension) from all source files.
    Returns a set of lowercase stems/names for quick lookup.
    """
    referenced: set[str] = set()

    for path in files:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue

        if path.suffix == ".py":
            for m in _PY_IMPORT_FROM_RE.finditer(text):
                module = m.group(1) or m.group(2)
                if module:
                    # last segment of dotted module name
                    for part in module.replace(",", " ").split():
                        referenced.add(part.strip().split(".")[-1].lower())
        else:
            for m in _TS_IMPORT_PATH_RE.finditer(text):
                imp_path = m.group(1)
                # Take the last path component without extension
                stem = Path(imp_path).stem.lower()
                referenced.add(stem)
                # Also add without leading dot/underscore normalisation
                referenced.add(stem.lstrip("_"))

    return referenced


def _check_unreferenced_files(all_files: list[Path], root: Path) -> list[Finding]:
    """Find source files that appear to not be imported from anywhere."""
    referenced = _collect_referenced_stems(all_files, root)
    findings: list[Finding] = []

    for path in all_files:
        if path.name in _SKIP_FILENAMES:
            continue
        if _ENTRY_POINT_RE.search(path.name):
            continue

        stem_lower = path.stem.lower()
        if stem_lower not in referenced:
            rel = path.relative_to(root).as_posix()
            findings.append(
                Finding(
                    analyzer="dead-code",
                    severity="info",
                    file=rel,
                    line=None,
                    message=(
                        f"File '{path.name}' does not appear to be imported "
                        f"from any other source file — may be unreferenced (heuristic)"
                    ),
                    category="unreferenced-file",
                )
            )

    return findings


# ─── Analyzer ─────────────────────────────────────────────────────────────────


class DeadCodeAnalyzer(BaseAnalyzer):
    """Heuristic dead code detector for TypeScript and Python codebases."""

    name = "dead-code"
    description = (
        "Heuristic: detects unexported TS symbols, uncalled Python functions, "
        "and source files not referenced by any import. All findings are 'info'."
    )

    def __init__(
        self,
        check_ts_unexported: bool = True,
        check_py_unused_functions: bool = True,
        check_unreferenced_files: bool = True,
    ) -> None:
        self._check_ts = check_ts_unexported
        self._check_py = check_py_unused_functions
        self._check_files = check_unreferenced_files

    def _is_skipped(self, path: Path, root: Path) -> bool:
        rel = str(path.relative_to(root)).replace("\\", "/")
        if path.name in _SKIP_FILENAMES:
            return True
        if _ENTRY_POINT_RE.search(path.name):
            return True
        for skip in _SKIP_DIRS:
            if skip in rel:
                return True
        return False

    def analyze(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        root = root.resolve()

        all_files = _collect_source_files(root)

        for path in all_files:
            if self._is_skipped(path, root):
                continue

            if self._check_ts and path.suffix in _SOURCE_EXTS_TS:
                findings.extend(_check_ts_unexported(path, root))

            if self._check_py and path.suffix == ".py":
                findings.extend(_check_py_unused_functions(path, root))

        if self._check_files:
            non_skipped = [p for p in all_files if not self._is_skipped(p, root)]
            findings.extend(_check_unreferenced_files(non_skipped, root))

        return findings
