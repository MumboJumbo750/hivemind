"""
Analyzer: Hardcoded CSS Values — Colors, Spacing, Fonts, Z-Index

Detects hardcoded CSS values that should use design tokens / CSS custom properties.

Registered automatically via AnalyzerRegistry (BaseAnalyzer subclass).
"""

from __future__ import annotations

import re
from pathlib import Path

from scripts.analyzers import BaseAnalyzer, Finding

# ─── Regexes ──────────────────────────────────────────────────────────────────

# Colors
_HEX_RE = re.compile(r"(?<![&\w])#([0-9a-fA-F]{3,8})\b")
_RGB_RE = re.compile(r"\brgba?\s*\([\d\s,./%%]+\)")
_HSL_RE = re.compile(r"\bhsla?\s*\([\d\s,./%%]+\)")
_NAMED_COLOR_PROPS_RE = re.compile(
    r"(?:^|\s|;)"
    r"(color|background(?:-color)?|border(?:-color)?|outline(?:-color)?|fill|stroke)"
    r"\s*:\s*"
    r"(red|green|blue|white|black|gray|grey|yellow|orange|purple|pink|brown|"
    r"cyan|magenta|lime|navy|teal|silver|gold|coral|salmon|khaki|violet|indigo)\b",
    re.IGNORECASE,
)

# Spacing — px values on layout properties (ignore 0px, 1px borders)
_SPACING_RE = re.compile(
    r"(?:^|\s|;)"
    r"(padding|margin|gap|row-gap|column-gap|top|right|bottom|left|"
    r"width|height|max-width|max-height|min-width|min-height|"
    r"border-radius|inset)"
    r"\s*:\s*"
    r"((?:\d+px\s*)+)",  # one or more px values
    re.IGNORECASE,
)
_SPACING_EXEMPT_RE = re.compile(r"\b(?:0px|1px|100%|0)\b")

# Font size
_FONT_SIZE_RE = re.compile(
    r"(?:^|\s|;)font-size\s*:\s*(\d+(?:\.\d+)?(?:px|rem|em|pt))\b",
    re.IGNORECASE,
)
_FONT_SIZE_EXEMPT = {"1rem", "inherit", "initial", "unset"}

# Z-index
_ZINDEX_RE = re.compile(r"(?:^|\s|;)z-index\s*:\s*(\d+)\b", re.IGNORECASE)
_ZINDEX_EXEMPT = {0, 1, -1}

# Exempt patterns (token / var usages)
_VAR_RE = re.compile(r"var\s*\(--")
_EXEMPT_TOKENS = re.compile(
    r"(?:currentColor|transparent|inherit|initial|unset|none)", re.IGNORECASE
)

# Files that are allowed to define raw values (theme/token definition files)
_DEFINITION_FILENAME_RE = re.compile(
    r"(tokens|semantic|theme|variables|colors|palette|design-system|base)",
    re.IGNORECASE,
)

# Supported file extensions
_CSS_EXTS = {".css", ".scss", ".sass", ".less"}
_COMPONENT_EXTS = {".vue", ".jsx", ".tsx"}
_ALL_EXTS = _CSS_EXTS | _COMPONENT_EXTS

# Directories to skip
_SKIP_DIRS = {
    "node_modules", ".git", ".venv", "venv", "__pycache__",
    "dist", "build", ".next", "coverage", "out",
}


class HardcodedCssAnalyzer(BaseAnalyzer):
    """Detects hardcoded CSS colors, spacing, font-sizes, and z-index values."""

    name = "hardcoded-css"
    description = "Finds hardcoded CSS values that should use design tokens."

    def analyze(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []

        for path in _iter_files(root):
            if _is_definition_file(path):
                continue
            try:
                self._analyze_file(root, path, findings)
            except Exception:
                pass  # never crash the run

        return findings

    def _analyze_file(self, root: Path, path: Path, findings: list[Finding]) -> None:
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = self._rel(root, path)

        if path.suffix == ".vue":
            # Only analyze <style> blocks in Vue SFCs
            style_blocks = re.findall(r"<style[^>]*>(.*?)</style>", text, re.DOTALL)
            css_text = "\n".join(style_blocks)
            if not css_text.strip():
                return
            self._check_css(rel, css_text, findings, offset=0)
        elif path.suffix in _CSS_EXTS:
            self._check_css(rel, text, findings, offset=0)
        elif path.suffix in {".jsx", ".tsx"}:
            # Check inline styles: style={{ color: 'red', padding: '12px' }}
            self._check_jsx_inline_styles(rel, text, findings)

    def _check_css(
        self, rel: str, text: str, findings: list[Finding], offset: int
    ) -> None:
        lines = text.splitlines()
        for i, raw_line in enumerate(lines, 1 + offset):
            line = raw_line.strip()
            if not line or line.startswith("//") or line.startswith("/*"):
                continue
            # Skip lines already using CSS variables
            if _VAR_RE.search(line):
                continue

            lineno = i
            self._check_colors(rel, line, lineno, findings)
            self._check_spacing(rel, line, lineno, findings)
            self._check_font_size(rel, line, lineno, findings)
            self._check_zindex(rel, line, lineno, findings)

    def _check_jsx_inline_styles(
        self, rel: str, text: str, findings: list[Finding]
    ) -> None:
        """Check style={{ ... }} objects in JSX/TSX."""
        inline_re = re.compile(r"style\s*=\s*\{\{(.+?)\}\}", re.DOTALL)
        for m in inline_re.finditer(text):
            lineno = text[: m.start()].count("\n") + 1
            block = m.group(1)
            self._check_colors(rel, block, lineno, findings)
            self._check_spacing(rel, block, lineno, findings)
            self._check_font_size(rel, block, lineno, findings)
            self._check_zindex(rel, block, lineno, findings)

    # ── individual checks ────────────────────────────────────────────────────

    def _check_colors(
        self, rel: str, line: str, lineno: int, findings: list[Finding]
    ) -> None:
        if _EXEMPT_TOKENS.search(line):
            return

        for m in _HEX_RE.finditer(line):
            findings.append(Finding(
                analyzer=self.name,
                severity="warning",
                file=rel,
                line=lineno,
                message=f"Hardcoded hex color `#{m.group(1)}` — use a CSS custom property (var(--))",
                category="hardcoded-color",
                auto_fixable=False,
            ))

        for pattern, label in [(_RGB_RE, "rgb/rgba"), (_HSL_RE, "hsl/hsla")]:
            for m in pattern.finditer(line):
                findings.append(Finding(
                    analyzer=self.name,
                    severity="warning",
                    file=rel,
                    line=lineno,
                    message=f"Hardcoded {label} color `{m.group(0).strip()}` — use a CSS custom property",
                    category="hardcoded-color",
                    auto_fixable=False,
                ))

        m = _NAMED_COLOR_PROPS_RE.search(line)
        if m:
            findings.append(Finding(
                analyzer=self.name,
                severity="info",
                file=rel,
                line=lineno,
                message=f"Named CSS color `{m.group(2)}` on property `{m.group(1)}` — consider a token",
                category="hardcoded-color",
                auto_fixable=False,
            ))

    def _check_spacing(
        self, rel: str, line: str, lineno: int, findings: list[Finding]
    ) -> None:
        m = _SPACING_RE.search(line)
        if not m:
            return
        values = m.group(2).strip()
        # Exempt if ALL tokens are 0px or 1px
        tokens = re.findall(r"\d+px", values)
        non_exempt = [t for t in tokens if t not in ("0px", "1px")]
        if not non_exempt:
            return
        findings.append(Finding(
            analyzer=self.name,
            severity="info",
            file=rel,
            line=lineno,
            message=f"Hardcoded spacing `{m.group(1)}: {values}` — consider a spacing token",
            category="hardcoded-spacing",
            auto_fixable=False,
        ))

    def _check_font_size(
        self, rel: str, line: str, lineno: int, findings: list[Finding]
    ) -> None:
        m = _FONT_SIZE_RE.search(line)
        if not m:
            return
        value = m.group(1).lower()
        if value in _FONT_SIZE_EXEMPT:
            return
        findings.append(Finding(
            analyzer=self.name,
            severity="info",
            file=rel,
            line=lineno,
            message=f"Hardcoded font-size `{value}` — consider a typography token",
            category="hardcoded-font-size",
            auto_fixable=False,
        ))

    def _check_zindex(
        self, rel: str, line: str, lineno: int, findings: list[Finding]
    ) -> None:
        m = _ZINDEX_RE.search(line)
        if not m:
            return
        val = int(m.group(1))
        if val in _ZINDEX_EXEMPT:
            return
        findings.append(Finding(
            analyzer=self.name,
            severity="info",
            file=rel,
            line=lineno,
            message=f"Hardcoded z-index `{val}` — consider a z-index scale token",
            category="hardcoded-z-index",
            auto_fixable=False,
        ))


# ─── File Iterator ────────────────────────────────────────────────────────────

def _iter_files(root: Path):
    """Yield all relevant style/component files, skipping junk dirs."""
    for entry in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in entry.parts):
            continue
        if entry.is_file() and entry.suffix in _ALL_EXTS:
            yield entry


def _is_definition_file(path: Path) -> bool:
    """Return True if this file is a token/theme definition (allowed to have raw values)."""
    return bool(_DEFINITION_FILENAME_RE.search(path.stem))
