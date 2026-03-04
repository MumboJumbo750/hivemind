"""
Analyzer: Duplicate Detection — Templates, CSS-Blocks, Code-Blocks, Import Patterns

Detects:
  - Exact and near-duplicate <template> blocks in Vue SFC files (Phase 1 + 2)
  - Exact and near-duplicate <style> blocks in Vue SFC files (Phase 1 + 2)
  - Near-duplicate code blocks (functions/methods ≥ min_block_lines) across
    Python, JS/TS, and Vue <script> sections (Phase 2)
  - Import groups repeated in > import_repeat_threshold files
    → Extract to Barrel/Index candidates (Phase 1)

Algorithm:
  Phase 1 : Content-Hashing  — fast, exact duplicates (always runs)
  Phase 2 : Token-Similarity via difflib.SequenceMatcher  — slower, near-dup
             Configurable via deep_scan=True (default)

Configuration (constructor args):
  similarity_threshold     : float, default 0.80 (80%)
  min_block_lines          : int,   default 5
  deep_scan                : bool,  default True (Phase 1 + Phase 2)
  import_repeat_threshold  : int,   default 3 (group must appear in >N files)
  ignore_dirs              : frozenset[str]

Registered automatically via AnalyzerRegistry (BaseAnalyzer subclass).
"""

from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations
from pathlib import Path
from typing import Iterator

from scripts.analyzers import BaseAnalyzer, Finding

# ── Defaults ──────────────────────────────────────────────────────────────────

DEFAULT_SIMILARITY: float = 0.80
DEFAULT_MIN_LINES: int = 5
DEFAULT_IMPORT_REPEAT: int = 3
DEFAULT_IGNORE_DIRS: frozenset[str] = frozenset(
    {
        "node_modules",
        ".git",
        ".venv",
        "venv",
        "__pycache__",
        ".mypy_cache",
        ".pytest_cache",
        "dist",
        "build",
        ".next",
        "coverage",
        "out",
    }
)

# ── Vue SFC block extractors ──────────────────────────────────────────────────

_VUE_BLOCK_RE = re.compile(
    r"<(template|style|script)(\s[^>]*)?>(.+?)</\1>",
    re.DOTALL | re.IGNORECASE,
)

# ── Import line extractors ─────────────────────────────────────────────────────

_PY_IMPORT_RE = re.compile(r"^\s*(?:from\s+\S+\s+import|import)\s+.+", re.MULTILINE)
_JS_IMPORT_RE = re.compile(r"""^\s*import\s+.+?\s+from\s+['"].+['"]""", re.MULTILINE)

# ── Helpers ───────────────────────────────────────────────────────────────────


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _normalize(text: str) -> str:
    """Collapse whitespace for stable hashing/comparison."""
    return re.sub(r"\s+", " ", text.strip())


def _tokenize(text: str) -> list[str]:
    """Split into alphanumeric tokens."""
    return re.findall(r"\w+", text)


def _similarity(a: str, b: str) -> float:
    """SequenceMatcher ratio on token sequences."""
    ta = _tokenize(a)
    tb = _tokenize(b)
    if not ta or not tb:
        return 0.0
    return SequenceMatcher(None, ta, tb).ratio()


def _iter_files(
    root: Path,
    extensions: frozenset[str],
    ignore_dirs: frozenset[str],
) -> Iterator[Path]:
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in ignore_dirs for part in path.parts):
            continue
        if path.suffix in extensions:
            yield path


# ── Content-block extraction ──────────────────────────────────────────────────


def _extract_vue_blocks(
    content: str,
) -> dict[str, str]:
    """Return {'template': ..., 'style': ..., 'script': ...} or empty values."""
    result: dict[str, str] = {"template": "", "style": "", "script": ""}
    for m in _VUE_BLOCK_RE.finditer(content):
        tag = m.group(1).lower()
        if tag in result:
            result[tag] = m.group(3)
    return result


def _extract_py_functions(content: str, min_lines: int) -> list[str]:
    """
    Extract Python function/method bodies (def-to-next-same-or-outer-indent).
    Returns only blocks with >= min_lines lines.
    """
    blocks: list[str] = []
    lines = content.splitlines()
    n = len(lines)
    i = 0
    while i < n:
        m_def = re.match(r"^(\s*)def\s+\w+", lines[i])
        if not m_def:
            i += 1
            continue
        indent = len(m_def.group(1))
        block: list[str] = [lines[i]]
        j = i + 1
        while j < n:
            raw = lines[j]
            stripped = raw.strip()
            if stripped == "":
                block.append(raw)
                j += 1
                continue
            line_indent = len(raw) - len(raw.lstrip())
            if line_indent > indent:
                block.append(raw)
                j += 1
            else:
                break
        # Trim trailing blank lines
        while block and not block[-1].strip():
            block.pop()
        if len(block) >= min_lines:
            blocks.append("\n".join(block))
        i = j
    return blocks


def _extract_js_functions(content: str, min_lines: int) -> list[str]:
    """
    Extract JS/TS function bodies using brace-depth tracking.
    Matches: function declarations, arrow functions, method shorthands.
    Returns only blocks with >= min_lines lines.
    """
    blocks: list[str] = []
    lines = content.splitlines()
    n = len(lines)

    # Patterns that signal the start of a function
    _func_start = re.compile(
        r"(?:"
        r"(?:export\s+)?(?:async\s+)?function\s+\w+"         # function foo
        r"|(?:async\s+)?\w+\s*[:=]\s*(?:async\s+)?"          # method = / property:
        r"(?:\([^)]*\)|[a-zA-Z_]\w*)\s*=>"                   # arrow
        r"|(?:async\s+)?\w+\s*\([^)]*\)\s*(?::\s*\w[\w<> [\],|?&.]*\s*)?\{"  # method(){ or method(): Type {
        r")"
    )

    i = 0
    while i < n:
        if not _func_start.search(lines[i]):
            i += 1
            continue

        # Find the opening brace in this or the next few lines
        start_line = i
        search_text = "\n".join(lines[i : i + 3])
        brace_pos = search_text.find("{")
        if brace_pos == -1:
            i += 1
            continue

        # Determine which line the opening brace is on
        pre_brace = search_text[:brace_pos]
        brace_line_offset = pre_brace.count("\n")
        brace_line = i + brace_line_offset

        # Walk forward tracking brace depth
        depth = 0
        j = brace_line
        block: list[str] = lines[i : brace_line + 1]
        depth += lines[brace_line].count("{") - lines[brace_line].count("}")

        j = brace_line + 1
        while j < n and depth > 0:
            line = lines[j]
            depth += line.count("{") - line.count("}")
            block.append(line)
            j += 1
            if depth <= 0:
                break

        # Trim trailing blank lines
        while block and not block[-1].strip():
            block.pop()

        if len(block) >= min_lines:
            blocks.append("\n".join(block))
        i = j if j > i else i + 1

    return blocks


def _extract_imports(content: str, suffix: str) -> frozenset[str]:
    """Extract a frozenset of import lines from a file."""
    if suffix == ".py":
        matches = _PY_IMPORT_RE.findall(content)
    else:
        matches = _JS_IMPORT_RE.findall(content)
    return frozenset(m.strip() for m in matches if m.strip())


# ── Main Analyzer ─────────────────────────────────────────────────────────────


class DuplicateDetectionAnalyzer(BaseAnalyzer):
    """
    Detect duplicate templates, CSS blocks, code blocks, and import patterns.
    """

    name = "duplicate-detection"
    description = "Detects duplicate and near-duplicate Vue templates, CSS blocks, code functions, and import groups."

    def __init__(
        self,
        similarity_threshold: float = DEFAULT_SIMILARITY,
        min_block_lines: int = DEFAULT_MIN_LINES,
        deep_scan: bool = True,
        import_repeat_threshold: int = DEFAULT_IMPORT_REPEAT,
        ignore_dirs: frozenset[str] = DEFAULT_IGNORE_DIRS,
    ) -> None:
        self.similarity_threshold = similarity_threshold
        self.min_block_lines = min_block_lines
        self.deep_scan = deep_scan
        self.import_repeat_threshold = import_repeat_threshold
        self.ignore_dirs = ignore_dirs

    # ── Public entry point ────────────────────────────────────────────────────

    def analyze(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        findings.extend(self._check_vue_blocks(root))
        findings.extend(self._check_code_blocks(root))
        findings.extend(self._check_import_patterns(root))
        return findings

    # ── Vue Template + CSS duplicates ─────────────────────────────────────────

    def _check_vue_blocks(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        _vue_exts = frozenset({".vue"})

        # Collect template and style blocks per file
        # {file_rel: {"template": content, "style": content}}
        templates: dict[str, tuple[Path, str]] = {}  # rel_path -> (abs_path, normalized_content)
        styles: dict[str, tuple[Path, str]] = {}

        for path in _iter_files(root, _vue_exts, self.ignore_dirs):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            blocks = _extract_vue_blocks(content)
            rel = self._rel(root, path)

            tmpl = blocks["template"]
            if tmpl.strip():
                templates[rel] = (path, _normalize(tmpl))

            style = blocks["style"]
            if style.strip():
                styles[rel] = (path, _normalize(style))

        # Phase 1: exact hash duplicates
        findings.extend(self._hash_duplicates(root, templates, "template-duplicate", "template"))
        findings.extend(self._hash_duplicates(root, styles, "css-duplicate", "style"))

        # Phase 2: near-duplicates (SequenceMatcher)
        if self.deep_scan:
            findings.extend(
                self._near_duplicates(root, templates, "template-near-duplicate", "template")
            )
            findings.extend(
                self._near_duplicates(root, styles, "css-near-duplicate", "style")
            )

        return findings

    def _hash_duplicates(
        self,
        root: Path,
        blocks: dict[str, tuple[Path, str]],
        category: str,
        block_type: str,
    ) -> list[Finding]:
        """Phase 1: group by hash, emit finding for each pair of exact duplicates."""
        findings: list[Finding] = []
        hash_to_files: dict[str, list[str]] = defaultdict(list)

        for rel, (_, norm) in blocks.items():
            h = _sha256(norm)
            hash_to_files[h].append(rel)

        for h, files in hash_to_files.items():
            if len(files) < 2:
                continue
            # Emit one finding per pair to make it pairwise
            for a, b in combinations(sorted(files), 2):
                findings.append(
                    Finding(
                        analyzer=self.name,
                        severity="warning",
                        file=a,
                        line=None,
                        message=(
                            f"Exact {block_type} duplicate: `{a}` and `{b}` "
                            f"have identical content (similarity: 1.00). "
                            f"Consider extracting a shared component."
                        ),
                        category=category,
                        auto_fixable=False,
                    )
                )
        return findings

    def _near_duplicates(
        self,
        root: Path,
        blocks: dict[str, tuple[Path, str]],
        category: str,
        block_type: str,
    ) -> list[Finding]:
        """Phase 2: pairwise similarity check, skip exact duplicates (covered by phase 1)."""
        findings: list[Finding] = []
        items = sorted(blocks.items())  # deterministic order

        # Pre-compute hashes so we skip exact pairs (already reported)
        hashes = {rel: _sha256(norm) for rel, (_, norm) in items}

        for (rel_a, (_, norm_a)), (rel_b, (_, norm_b)) in combinations(items, 2):
            # Skip exact duplicates (handled in phase 1)
            if hashes[rel_a] == hashes[rel_b]:
                continue

            score = _similarity(norm_a, norm_b)
            if score >= self.similarity_threshold:
                pct = int(score * 100)
                findings.append(
                    Finding(
                        analyzer=self.name,
                        severity="info",
                        file=rel_a,
                        line=None,
                        message=(
                            f"Near-duplicate {block_type} ({pct}% similar): "
                            f"`{rel_a}` ↔ `{rel_b}`. "
                            f"Consider extracting shared content."
                        ),
                        category=category,
                        auto_fixable=False,
                    )
                )
        return findings

    # ── Code-Block (function/method) duplicates ───────────────────────────────

    def _check_code_blocks(self, root: Path) -> list[Finding]:
        """Phase 2: near-duplicate function/method blocks (≥ min_block_lines)."""
        if not self.deep_scan:
            return []

        findings: list[Finding] = []
        _code_exts = frozenset({".py", ".ts", ".js", ".vue"})

        # Collect (rel_path, block_text) pairs
        all_blocks: list[tuple[str, str]] = []

        for path in _iter_files(root, _code_exts, self.ignore_dirs):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            rel = self._rel(root, path)

            if path.suffix == ".py":
                extracted = _extract_py_functions(content, self.min_block_lines)
            elif path.suffix in {".ts", ".js"}:
                extracted = _extract_js_functions(content, self.min_block_lines)
            elif path.suffix == ".vue":
                script = _extract_vue_blocks(content)["script"]
                if script.strip():
                    extracted = _extract_js_functions(script, self.min_block_lines)
                else:
                    extracted = []
            else:
                extracted = []

            for block in extracted:
                all_blocks.append((rel, block))

        # Pairwise comparison across different files
        # Group by file first to avoid file-internal duplicates flooding output
        by_file: dict[str, list[str]] = defaultdict(list)
        for rel, block in all_blocks:
            by_file[rel].append(block)

        files = sorted(by_file.keys())

        # Pre-compute hashes for exact-match fast-path
        exact: dict[str, list[tuple[str, str]]] = defaultdict(list)  # hash -> [(file, block)]
        for rel, blocks_list in by_file.items():
            for b in blocks_list:
                h = _sha256(_normalize(b))
                exact[h].append((rel, b))

        # Emit exact code duplicates (across different files)
        reported_exact: set[tuple[str, str, str]] = set()
        for h, entries in exact.items():
            cross = [(r, b) for r, b in entries if r]
            unique_files = list({r for r, _ in cross})
            if len(unique_files) < 2:
                continue
            for (rel_a, block_a), (rel_b, block_b) in combinations(cross, 2):
                if rel_a == rel_b:
                    continue
                key = (min(rel_a, rel_b), max(rel_a, rel_b), h)
                if key in reported_exact:
                    continue
                reported_exact.add(key)
                nlines = block_a.count("\n") + 1
                findings.append(
                    Finding(
                        analyzer=self.name,
                        severity="warning",
                        file=rel_a,
                        line=None,
                        message=(
                            f"Exact code-block duplicate ({nlines} lines, similarity: 1.00): "
                            f"`{rel_a}` and `{rel_b}`. Consider extracting a shared function."
                        ),
                        category="code-duplicate",
                        auto_fixable=False,
                    )
                )

        # Near-duplicate cross-file comparison (skip exact pairs)
        exact_hashes: set[str] = {h for h, entries in exact.items() if len({r for r, _ in entries}) >= 2}
        reported_near: set[tuple[str, str, int]] = set()

        for file_a, file_b in combinations(files, 2):
            blocks_a = by_file[file_a]
            blocks_b = by_file[file_b]
            for block_a in blocks_a:
                h_a = _sha256(_normalize(block_a))
                if h_a in exact_hashes:
                    continue  # already reported as exact
                for block_b in blocks_b:
                    h_b = _sha256(_normalize(block_b))
                    if h_a == h_b:
                        continue  # exact duplicate already reported
                    score = _similarity(block_a, block_b)
                    if score >= self.similarity_threshold:
                        pct = int(score * 100)
                        key = (min(file_a, file_b), max(file_a, file_b), pct)
                        if key in reported_near:
                            continue
                        reported_near.add(key)
                        nlines = max(block_a.count("\n") + 1, block_b.count("\n") + 1)
                        findings.append(
                            Finding(
                                analyzer=self.name,
                                severity="info",
                                file=file_a,
                                line=None,
                                message=(
                                    f"Near-duplicate code block ({nlines} lines, {pct}% similar): "
                                    f"`{file_a}` ↔ `{file_b}`. "
                                    f"Consider extracting a shared utility."
                                ),
                                category="code-near-duplicate",
                                auto_fixable=False,
                            )
                        )

        return findings

    # ── Import-Pattern duplicates ─────────────────────────────────────────────

    def _check_import_patterns(self, root: Path) -> list[Finding]:
        """
        Phase 1: Find import groups (≥ 2 lines) that appear in > import_repeat_threshold files.
        Each unique frozenset of imports is a "group". If the same group appears in too many files,
        flag it as a barrel/index extraction candidate.
        """
        findings: list[Finding] = []
        _import_exts = frozenset({".py", ".ts", ".js", ".vue"})

        # file -> frozenset of import lines
        file_imports: dict[str, frozenset[str]] = {}

        for path in _iter_files(root, _import_exts, self.ignore_dirs):
            try:
                content = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            rel = self._rel(root, path)
            if path.suffix == ".vue":
                # Extract from <script> block
                script = _extract_vue_blocks(content)["script"]
                imports = _extract_imports(script, ".ts")
            else:
                imports = _extract_imports(content, path.suffix)

            if len(imports) >= 2:  # Only groups with at least 2 imports are interesting
                file_imports[rel] = imports

        # Find common sub-groups: for each pair of files, compute intersection of imports
        # Flag if a common subset of ≥2 imports appears in > threshold files
        # We use full frozenset matches first (simple approach)
        group_files: dict[frozenset[str], list[str]] = defaultdict(list)
        for rel, imports in file_imports.items():
            group_files[imports].append(rel)

        for group, files_list in group_files.items():
            if len(files_list) > self.import_repeat_threshold:
                sample = sorted(list(group))[:3]
                sample_str = "; ".join(sample)
                if len(group) > 3:
                    sample_str += f"; ... (+{len(group) - 3} more)"
                for f in sorted(files_list):
                    findings.append(
                        Finding(
                            analyzer=self.name,
                            severity="info",
                            file=f,
                            line=None,
                            message=(
                                f"Import group ({len(group)} imports) repeated in "
                                f"{len(files_list)} files: [{sample_str}]. "
                                f"Consider creating a barrel/index file."
                            ),
                            category="import-pattern-duplicate",
                            auto_fixable=False,
                        )
                    )

        # Also check for partial overlap: common imports across many files
        # Use pairwise intersection for groups that are not identical
        file_list = sorted(file_imports.keys())
        for file_a, file_b in combinations(file_list, 2):
            imp_a = file_imports[file_a]
            imp_b = file_imports[file_b]
            common = imp_a & imp_b
            if len(common) >= 3:  # at least 3 shared imports
                # Check if this common group appears in many files
                count = sum(1 for imp in file_imports.values() if common.issubset(imp))
                if count > self.import_repeat_threshold:
                    # Only emit for the pair (not per-file, to avoid noise)
                    sample = sorted(list(common))[:3]
                    sample_str = "; ".join(sample)
                    if len(common) > 3:
                        sample_str += f"; ... (+{len(common) - 3} more)"
                    # Check we haven't already flagged the exact group
                    if common not in group_files or len(group_files[common]) <= self.import_repeat_threshold:
                        findings.append(
                            Finding(
                                analyzer=self.name,
                                severity="info",
                                file=file_a,
                                line=None,
                                message=(
                                    f"Shared import subset ({len(common)} imports, used in {count} files): "
                                    f"[{sample_str}]. Consider a barrel/index export."
                                ),
                                category="import-pattern-duplicate",
                                auto_fixable=False,
                            )
                        )

        return findings
