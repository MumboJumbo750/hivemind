"""
Analyzer: Magic Numbers & Hardcoded Strings

Detects:
  - Magic numbers in comparisons, function arguments, and lowercase variable assignments
  - Hardcoded URLs and API paths in business logic
  - Hardcoded status strings used in comparisons instead of enums/constants

Suppression markers:
  Python  : # noqa: magic
  JS/TS   : // magic-ok

Configuration (constructor args):
  allowed_numbers : numbers that are always exempt (default: {0, 1, -1, 2, 100})
  ignore_patterns : list of regex strings — matching lines are skipped entirely
  ignore_dirs     : set of directory names to skip (default: tests, migrations, …)

Registered automatically via AnalyzerRegistry (BaseAnalyzer subclass).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Sequence

from scripts.analyzers import BaseAnalyzer, Finding

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_ALLOWED_NUMBERS: frozenset[float] = frozenset({0.0, 1.0, -1.0, 2.0, 100.0})
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        "tests",
        "test",
        "migrations",
        "__pycache__",
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "dist",
        "build",
        ".next",
        "coverage",
        "out",
    }
)

# ── Suppression ────────────────────────────────────────────────────────────────

_PY_NOQA_RE = re.compile(r"#\s*noqa\s*:.*\bmagic\b", re.IGNORECASE)
_JS_MAGIC_OK_RE = re.compile(r"//.*\bmagic-ok\b", re.IGNORECASE)

# ── Supported extensions ───────────────────────────────────────────────────────

_PY_EXTS = frozenset({".py"})
_JS_EXTS = frozenset({".ts", ".js", ".vue"})
_ALL_EXTS = _PY_EXTS | _JS_EXTS

# ── Structural exclusions ──────────────────────────────────────────────────────

_IS_PY_TEST = re.compile(r"(?:^|[/\\])tests?[/\\]", re.IGNORECASE)
_IS_PY_MIGRATION = re.compile(r"(?:^|[/\\])migrations?[/\\]", re.IGNORECASE)
_IS_JS_TEST = re.compile(r"\.(test|spec)\.[jt]sx?$", re.IGNORECASE)

# ── Structural helpers ─────────────────────────────────────────────────────────

_PY_IMPORT_RE = re.compile(r"^\s*(?:import|from)\s")
_JS_IMPORT_RE = re.compile(r'^\s*(?:import\b|(?:const|var|let)\s+\w+\s*=\s*require\s*\()')
_PY_COMMENT_RE = re.compile(r"^\s*#")
_JS_COMMENT_RE = re.compile(r"^\s*//")
_BLANK_RE = re.compile(r"^\s*$")

# ALL_CAPS variable assignment — intentional named constants, never flag
_ALL_CAPS_ASSIGN_RE = re.compile(r"\b[A-Z][A-Z0-9_]{2,}\s*(?::|=)(?!=)")

# Skip log / print / error message lines (strings there are messages, not config)
_LOG_SKIP_RE = re.compile(
    r"(?:\.log|\.warn|\.error|\.info|\.debug"
    r"|print\s*\("
    r"|logger\.\w+\s*\("
    r"|logging\.\w+\s*\("
    r"|console\.\w+\s*\("
    r"|raise\s+\w+"
    r"|throw\s+new\s+\w+"
    r"|Exception\s*\("
    r"|Error\s*\()",
    re.IGNORECASE,
)

# ── Magic Number Regexes ───────────────────────────────────────────────────────

# Number following a comparison operator: > 42, >= 3.14, == 99, !== 5, != -7
_CMP_NUMBER_RE = re.compile(
    r"(?:[><!]=?=?|===)\s*(-?\s*\d+(?:\.\d+)?)\b"
    r"(?!\s*[\"'\w])"  # not followed by string or identifier (avoids false array triggers)
)

# Number as function argument: fn(x, 3000), fn(5), retry(3)
# Captures trailing numeric arg before ) or another arg
_FUNC_ARG_NUMBER_RE = re.compile(
    r"\b(\w+)\s*\("  # function name
    r"(?:[^()]*?[,(]\s*)?"  # optional preceding args (no nested parens)
    r"(-?\d+(?:\.\d+)?)\s*"  # the numeric arg (group 2)
    r"(?:,\s*[^()]*?)?\)"  # optional trailing args
)

# Trailing numeric argument: catches setTimeout(() => fn(), 3000) style
# where nested parens prevent the above regex from matching
_TRAILING_ARG_RE = re.compile(r",\s*(-?\d+(?:\.\d+)?)\s*\)")

# Short variable names that are common loop counters — never flag their assignments
_LOOP_VAR_RE = re.compile(r"^[a-z_]{1,2}$")

# Lowercase variable assignment: timeout = 3000, threshold = 0.85
# Excludes ALL_CAPS and very short names (loop vars)
_LOWERCASE_ASSIGN_RE = re.compile(
    r"\b([a-z_][a-z0-9_]*)\s*=(?!=)\s*(-?\d+(?:\.\d+)?)\s*(?:[;,#\r\n]|$)"
)

# ── Hardcoded String Regexes ───────────────────────────────────────────────────

# URL literals (http:// or https://)
_URL_RE = re.compile(r"""['"](?P<url>https?://[^'"]{5,})['"]""")

# API path literals such as '/api/users' or '/api/v1/epics/{id}'
_API_PATH_RE = re.compile(r"""['"](?P<path>/api(?:/[a-zA-Z0-9_\-{}?#%&=.]+)+)['"]""")

# Status string in equality comparison: x === 'pending', "failed" == y
_STATUS_CMP_RE = re.compile(
    r"""(?:===?|!==?)\s*['"](?P<a>[a-z][a-z0-9_]{2,})['"]"""
    r"""|['"](?P<b>[a-z][a-z0-9_]{2,})['"]\s*(?:===?|!==?)"""
)

_STATUS_WORDS: frozenset[str] = frozenset(
    {
        "pending",
        "active",
        "inactive",
        "cancelled",
        "canceled",
        "completed",
        "failed",
        "success",
        "draft",
        "published",
        "archived",
        "approved",
        "rejected",
        "open",
        "closed",
        "resolved",
        "blocked",
        "ready",
        "running",
        "stopped",
        "enabled",
        "disabled",
        "incoming",
        "scoped",
        "in_progress",
        "in_review",
        "done",
        "qa_failed",
        "escalated",
    }
)

# Router / route definition files — exempt from API path detection
_ROUTER_FILE_RE = re.compile(
    r"(?:router|routes?|endpoints?|urls?|api\.py|openapi)(?:\.\w+)?$",
    re.IGNORECASE,
)


# ── Analyzer ──────────────────────────────────────────────────────────────────


class MagicValuesAnalyzer(BaseAnalyzer):
    """Finds magic numbers and hardcoded strings (URLs, API paths, status literals)."""

    name = "magic-values"
    description = (
        "Detects magic numbers in conditions/args and hardcoded"
        " URLs/API-paths/status strings."
    )

    def __init__(
        self,
        allowed_numbers: Sequence[int | float] | None = None,
        ignore_patterns: Sequence[str] | None = None,
        ignore_dirs: Sequence[str] | None = None,
    ) -> None:
        self._allowed: frozenset[float] = (
            frozenset(float(n) for n in allowed_numbers)
            if allowed_numbers is not None
            else DEFAULT_ALLOWED_NUMBERS
        )
        self._ignore_res: list[re.Pattern] = (
            [re.compile(p) for p in ignore_patterns] if ignore_patterns else []
        )
        self._ignore_dirs: frozenset[str] = (
            frozenset(ignore_dirs) if ignore_dirs is not None else DEFAULT_IGNORE_DIRS
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def analyze(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        for path in self._iter_files(root):
            try:
                rel = self._rel(root, path)
                if path.suffix in _PY_EXTS:
                    self._analyze_python(path, rel, findings)
                else:
                    self._analyze_js(path, rel, findings)
            except Exception:
                pass  # never crash the run
        return findings

    # ── Python ────────────────────────────────────────────────────────────────

    def _analyze_python(self, path: Path, rel: str, findings: list[Finding]) -> None:
        if _IS_PY_TEST.search(rel) or _IS_PY_MIGRATION.search(rel):
            return

        text = path.read_text(encoding="utf-8", errors="ignore")
        lines = text.splitlines()
        in_multiline_string = False
        ml_char: str = ""

        for lineno, raw_line in enumerate(lines, 1):
            stripped = raw_line.strip()

            # Track triple-quoted strings (rough heuristic)
            if not in_multiline_string:
                for q in ('"""', "'''"):
                    if stripped.count(q) == 1:  # opens but does not close on same line
                        in_multiline_string = True
                        ml_char = q
                        break
                if in_multiline_string:
                    continue
            else:
                if ml_char in stripped:
                    in_multiline_string = False
                continue

            if _BLANK_RE.match(raw_line):
                continue
            if _PY_COMMENT_RE.match(raw_line):
                continue
            if _PY_NOQA_RE.search(raw_line):
                continue
            if _PY_IMPORT_RE.match(raw_line):
                continue
            if self._is_user_ignored(raw_line):
                continue

            self._check_magic_numbers(rel, raw_line, lineno, findings, is_python=True)
            self._check_hardcoded_strings(rel, raw_line, lineno, findings)

    # ── TypeScript / JavaScript / Vue ─────────────────────────────────────────

    def _analyze_js(self, path: Path, rel: str, findings: list[Finding]) -> None:
        if _IS_JS_TEST.search(rel):
            return

        text = path.read_text(encoding="utf-8", errors="ignore")

        if path.suffix == ".vue":
            # Only inspect <script> blocks, not <template> or <style>
            blocks = re.findall(
                r"<script(?:\s[^>]*)?>(.+?)</script>", text, re.DOTALL | re.IGNORECASE
            )
            for block in blocks:
                offset = text.count("\n", 0, text.find(block))
                self._process_js_lines(block, rel, offset, findings)
        else:
            self._process_js_lines(text, rel, 0, findings)

    def _process_js_lines(
        self, text: str, rel: str, line_offset: int, findings: list[Finding]
    ) -> None:
        in_block_comment = False
        for i, raw_line in enumerate(text.splitlines(), 1):
            lineno = i + line_offset
            stripped = raw_line.strip()

            if in_block_comment:
                if "*/" in stripped:
                    in_block_comment = False
                continue
            if stripped.startswith("/*"):
                if "*/" not in stripped:
                    in_block_comment = True
                continue

            if _BLANK_RE.match(raw_line):
                continue
            if _JS_COMMENT_RE.match(raw_line):
                continue
            if _JS_MAGIC_OK_RE.search(raw_line):
                continue
            if _JS_IMPORT_RE.match(raw_line):
                continue
            if self._is_user_ignored(raw_line):
                continue

            self._check_magic_numbers(rel, raw_line, lineno, findings, is_python=False)
            self._check_hardcoded_strings(rel, raw_line, lineno, findings)

    # ── Magic Number Checks ────────────────────────────────────────────────────

    def _check_magic_numbers(
        self,
        rel: str,
        line: str,
        lineno: int,
        findings: list[Finding],
        is_python: bool,
    ) -> None:
        # ALL_CAPS assignments are intentional constants → skip
        if _ALL_CAPS_ASSIGN_RE.search(line):
            return

        seen_positions: set[int] = set()

        # ── Comparison operators ──────────────────────────────────────────────
        for m in _CMP_NUMBER_RE.finditer(line):
            val_str = m.group(1).replace(" ", "")
            try:
                val = float(val_str)
            except ValueError:
                continue
            if val in self._allowed:
                continue
            seen_positions.add(m.start())
            findings.append(
                Finding(
                    analyzer=self.name,
                    severity="warning",
                    file=rel,
                    line=lineno,
                    message=(
                        f"Magic number `{val_str}` in comparison"
                        " — extract to a named constant (e.g. MAX_RETRIES = ...)"
                    ),
                    category="magic-number",
                )
            )

        # ── Function arguments ─────────────────────────────────────────────────
        for m in _FUNC_ARG_NUMBER_RE.finditer(line):
            func_name = m.group(1)
            val_str = m.group(2)
            # Skip if already caught by comparison check (same position)
            if m.start() in seen_positions:
                continue
            try:
                val = float(val_str)
            except ValueError:
                continue
            if val in self._allowed:
                continue
            # Likely timeout/sleep/retry patterns deserve a warning
            sev = (
                "warning"
                if any(kw in func_name.lower() for kw in ("sleep", "timeout", "retry", "delay", "wait", "interval"))
                else "info"
            )
            findings.append(
                Finding(
                    analyzer=self.name,
                    severity=sev,
                    file=rel,
                    line=lineno,
                    message=(
                        f"Magic number `{val_str}` passed to `{func_name}()`"
                        " — consider a named constant"
                    ),
                    category="magic-number-arg",
                )
            )

        # Catch trailing numeric args after nested parens: fn(() => foo(), 3000)
        for m in _TRAILING_ARG_RE.finditer(line):
            val_str = m.group(1)
            pos = m.start()
            if pos in seen_positions:
                continue
            try:
                val = float(val_str)
            except ValueError:
                continue
            if val in self._allowed:
                continue
            seen_positions.add(pos)
            findings.append(
                Finding(
                    analyzer=self.name,
                    severity="info",
                    file=rel,
                    line=lineno,
                    message=(
                        f"Magic number `{val_str}` as function argument"
                        " — consider a named constant"
                    ),
                    category="magic-number-arg",
                )
            )

        # ── Lowercase variable assignments ─────────────────────────────────────
        for m in _LOWERCASE_ASSIGN_RE.finditer(line):
            var_name, val_str = m.group(1), m.group(2)
            if _LOOP_VAR_RE.match(var_name):
                continue
            try:
                val = float(val_str)
            except ValueError:
                continue
            if val in self._allowed:
                continue
            findings.append(
                Finding(
                    analyzer=self.name,
                    severity="info",
                    file=rel,
                    line=lineno,
                    message=(
                        f"Numeric literal `{val_str}` assigned to `{var_name}`"
                        " — consider a named constant"
                    ),
                    category="magic-number",
                )
            )

    # ── Hardcoded String Checks ────────────────────────────────────────────────

    def _check_hardcoded_strings(
        self, rel: str, line: str, lineno: int, findings: list[Finding]
    ) -> None:
        # Skip log/print/error lines (their strings are messages, not config)
        if _LOG_SKIP_RE.search(line):
            return

        # URL literals
        for m in _URL_RE.finditer(line):
            url = m.group("url")
            truncated = url[:80] + ("…" if len(url) > 80 else "")
            findings.append(
                Finding(
                    analyzer=self.name,
                    severity="warning",
                    file=rel,
                    line=lineno,
                    message=(
                        f"Hardcoded URL `{truncated}`"
                        " — move to config/environment variable"
                    ),
                    category="hardcoded-url",
                )
            )

        # API path literals (skip router/route definition files)
        if not _ROUTER_FILE_RE.search(Path(rel).name):
            for m in _API_PATH_RE.finditer(line):
                api_path = m.group("path")
                findings.append(
                    Finding(
                        analyzer=self.name,
                        severity="info",
                        file=rel,
                        line=lineno,
                        message=(
                            f"Hardcoded API path `{api_path}`"
                            " — consider a central route constant"
                        ),
                        category="hardcoded-api-path",
                    )
                )

        # Status string comparisons
        for m in _STATUS_CMP_RE.finditer(line):
            word = (m.group("a") or m.group("b") or "").lower()
            if word in _STATUS_WORDS:
                findings.append(
                    Finding(
                        analyzer=self.name,
                        severity="info",
                        file=rel,
                        line=lineno,
                        message=(
                            f'Hardcoded status string `"{word}"` in comparison'
                            " — consider an enum or named constant"
                        ),
                        category="hardcoded-status",
                    )
                )

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _is_user_ignored(self, line: str) -> bool:
        return any(p.search(line) for p in self._ignore_res)

    def _iter_files(self, root: Path):
        for entry in root.rglob("*"):
            if any(part in self._ignore_dirs for part in entry.parts):
                continue
            if entry.is_file() and entry.suffix in _ALL_EXTS:
                yield entry
