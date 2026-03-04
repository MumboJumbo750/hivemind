"""
Analyzer: Hardcoded CSS Values — Colors, Spacing, Fonts, Z-Index

Detects hardcoded CSS values that should use design tokens / CSS custom properties.

Registered automatically via AnalyzerRegistry (BaseAnalyzer subclass).

Configuration (via __init__ config dict or root/.hivemind-health.json):
  {
    "hardcoded-css": {
      "exclude_patterns": ["**/tokens/**", "**/design-system/**"],
      "definition_patterns": ["my-theme", "my-colors"],
      "color_allowlist": ["rebeccapurple"],
      "spacing_allowlist_px": [2, 3, 4]
    }
  }
"""

from __future__ import annotations

import fnmatch
import json
import re
from pathlib import Path

from scripts.analyzers import BaseAnalyzer, Finding

# ─── Regexes ──────────────────────────────────────────────────────────────────

# Colors
_HEX_RE = re.compile(r"(?<![&\w])#([0-9a-fA-F]{3,8})\b")
_RGB_RE = re.compile(r"\brgba?\s*\([\d\s,./%%]+\)")
_HSL_RE = re.compile(r"\bhsla?\s*\([\d\s,./%%]+\)")

_DEFAULT_NAMED_COLORS = (
    "red|green|blue|white|black|gray|grey|yellow|orange|purple|pink|brown|"
    "cyan|magenta|lime|navy|teal|silver|gold|coral|salmon|khaki|violet|indigo"
)
def _make_named_color_re(extra_allowlist: frozenset[str] = frozenset()) -> re.Pattern:
    banned = _DEFAULT_NAMED_COLORS
    if extra_allowlist:
        # Remove allowlisted names from the detection set
        all_names = [n.strip() for n in banned.split("|")]
        all_names = [n for n in all_names if n.lower() not in extra_allowlist]
        if not all_names:
            return re.compile(r"(?!x)x")  # never matches
        banned = "|".join(all_names)
    return re.compile(
        r"(?:^|\s|;)"
        r"(color|background(?:-color)?|border(?:-color)?|outline(?:-color)?|fill|stroke)"
        r"\s*:\s*"
        r"(" + banned + r")\b",
        re.IGNORECASE,
    )

_NAMED_COLOR_PROPS_RE = _make_named_color_re()  # default (no allowlist)

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

# Font size
_FONT_SIZE_RE = re.compile(
    r"(?:^|\s|;)font-size\s*:\s*(\d+(?:\.\d+)?(?:px|rem|em|pt))\b",
    re.IGNORECASE,
)
_FONT_SIZE_EXEMPT = {"1rem", "inherit", "initial", "unset"}

# Z-index
_ZINDEX_RE = re.compile(r"(?:^|\s|;)z-index\s*:\s*(-?\d+)\b", re.IGNORECASE)
_ZINDEX_EXEMPT = {0, 1, -1}

# Exempt patterns (token / var usages)
_VAR_RE = re.compile(r"var\s*\(--")
_EXEMPT_TOKENS = re.compile(
    r"(?:currentColor|transparent|inherit|initial|unset|none)", re.IGNORECASE
)

# Files that are allowed to define raw values (theme/token definition files)
_DEFAULT_DEFINITION_STEMS = re.compile(
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

# ─── JSX / React inline-style helpers ─────────────────────────────────────────

# JSX camelCase → CSS property groups
_JSX_COLOR_PROPS = frozenset({
    "color", "backgroundColor", "background", "borderColor",
    "borderTopColor", "borderRightColor", "borderBottomColor", "borderLeftColor",
    "outlineColor", "fill", "stroke", "caretColor",
})
_JSX_SPACING_PROPS = frozenset({
    "padding", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft",
    "paddingInline", "paddingBlock",
    "margin", "marginTop", "marginRight", "marginBottom", "marginLeft",
    "marginInline", "marginBlock",
    "gap", "rowGap", "columnGap",
    "top", "right", "bottom", "left",
    "width", "height", "maxWidth", "maxHeight", "minWidth", "minHeight",
    "borderRadius",
    "borderTopLeftRadius", "borderTopRightRadius",
    "borderBottomLeftRadius", "borderBottomRightRadius",
    "inset",
})
_JSX_FONT_PROPS = frozenset({"fontSize", "lineHeight"})
_JSX_ZINDEX_PROPS = frozenset({"zIndex"})

# Matches  propName: 'value'  or  propName: "value"
_JSX_PROP_STR_RE = re.compile(r'(\w+)\s*:\s*[\'"]([^\'"]+)[\'"]')
# Matches  propName: 123   or   propName: -123   (bare number)
_JSX_PROP_NUM_RE = re.compile(r'(\w+)\s*:\s*(-?\d+(?:\.\d+)?)(?:\s*[,}\s]|$)')

# styled-components: styled.tag`...`  or  styled(Comp)`...`  or  css`...`
_STYLED_COMPONENTS_RE = re.compile(
    r"(?:styled\.[a-zA-Z]+|styled\([^)]+\)|css)\s*`([^`]*)`",
    re.DOTALL,
)


class HardcodedCssAnalyzer(BaseAnalyzer):
    """Detects hardcoded CSS colors, spacing, font-sizes, and z-index values."""

    name = "hardcoded-css"
    description = "Finds hardcoded CSS values that should use design tokens."

    def __init__(self, config: dict | None = None) -> None:
        self._init_config = config  # preserve for re-use; root-level config loaded in analyze()

    def analyze(self, root: Path) -> list[Finding]:
        cfg = self._resolve_config(root)
        exclude_patterns: list[str] = cfg.get("exclude_patterns", [])
        color_allowlist: frozenset[str] = frozenset(
            s.lower() for s in cfg.get("color_allowlist", [])
        )
        extra_def_patterns: list[str] = cfg.get("definition_patterns", [])
        spacing_allowlist_px: frozenset[int] = frozenset(
            int(v) for v in cfg.get("spacing_allowlist_px", [])
        )

        named_color_re = (
            _make_named_color_re(color_allowlist) if color_allowlist
            else _NAMED_COLOR_PROPS_RE
        )

        findings: list[Finding] = []
        for path in _iter_files(root):
            if _is_definition_file(path, extra_def_patterns):
                continue
            if _is_excluded(path, root, exclude_patterns):
                continue
            try:
                self._analyze_file(root, path, findings, named_color_re, spacing_allowlist_px)
            except Exception:
                pass  # never crash the run

        return findings

    # ── config helpers ────────────────────────────────────────────────────────

    def _resolve_config(self, root: Path) -> dict:
        if self._init_config is not None:
            return self._init_config
        # Try to load from root/.hivemind-health.json
        cfg_file = root / ".hivemind-health.json"
        if cfg_file.exists():
            try:
                data = json.loads(cfg_file.read_text(encoding="utf-8"))
                return data.get("hardcoded-css", {})
            except Exception:
                pass
        return {}

    # ── file dispatch ─────────────────────────────────────────────────────────

    def _analyze_file(
        self,
        root: Path,
        path: Path,
        findings: list[Finding],
        named_color_re: re.Pattern,
        spacing_allowlist_px: frozenset[int],
    ) -> None:
        text = path.read_text(encoding="utf-8", errors="ignore")
        rel = self._rel(root, path)

        if path.suffix == ".vue":
            # Only analyze <style> blocks in Vue SFCs; track actual file line offsets
            for m in re.finditer(r"<style[^>]*>(.*?)</style>", text, re.DOTALL):
                css_text = m.group(1)
                if not css_text.strip():
                    continue
                # Number of newlines before the CSS content start = 0-based line index
                offset = text[: m.start(1)].count("\n")
                self._check_css(rel, css_text, findings, offset=offset,
                                named_color_re=named_color_re,
                                spacing_allowlist_px=spacing_allowlist_px)
        elif path.suffix in _CSS_EXTS:
            self._check_css(rel, text, findings, offset=0,
                            named_color_re=named_color_re,
                            spacing_allowlist_px=spacing_allowlist_px)
        elif path.suffix in {".jsx", ".tsx"}:
            self._check_jsx(rel, text, findings,
                            named_color_re=named_color_re,
                            spacing_allowlist_px=spacing_allowlist_px)

    def _check_css(
        self,
        rel: str,
        text: str,
        findings: list[Finding],
        offset: int,
        named_color_re: re.Pattern = _NAMED_COLOR_PROPS_RE,
        spacing_allowlist_px: frozenset[int] = frozenset(),
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
            self._check_colors(rel, line, lineno, findings, named_color_re)
            self._check_spacing(rel, line, lineno, findings, spacing_allowlist_px)
            self._check_font_size(rel, line, lineno, findings)
            self._check_zindex(rel, line, lineno, findings)

    def _check_jsx(
        self,
        rel: str,
        text: str,
        findings: list[Finding],
        named_color_re: re.Pattern = _NAMED_COLOR_PROPS_RE,
        spacing_allowlist_px: frozenset[int] = frozenset(),
    ) -> None:
        """Check JSX/TSX files: inline styles, styled-components."""
        # 1. style={{ ... }} inline objects
        inline_re = re.compile(r"style\s*=\s*\{\{(.+?)\}\}", re.DOTALL)
        for m in inline_re.finditer(text):
            lineno = text[: m.start()].count("\n") + 1
            block = m.group(1)
            self._check_jsx_style_object(
                rel, block, lineno, findings, named_color_re, spacing_allowlist_px
            )

        # 2. styled-components template literals
        for m in _STYLED_COMPONENTS_RE.finditer(text):
            lineno = text[: m.start()].count("\n") + 1
            css_body = m.group(1)
            self._check_css(
                rel, css_body, findings, offset=lineno - 1,
                named_color_re=named_color_re,
                spacing_allowlist_px=spacing_allowlist_px,
            )

    def _check_jsx_style_object(
        self,
        rel: str,
        block: str,
        base_lineno: int,
        findings: list[Finding],
        named_color_re: re.Pattern,
        spacing_allowlist_px: frozenset[int],
    ) -> None:
        """Parse a JS style-object block and check each property:value pair."""
        # ── String values:  propName: 'value'  or  propName: "value" ──
        for m in _JSX_PROP_STR_RE.finditer(block):
            prop = m.group(1)
            raw_value = m.group(2)
            line_offset = block[: m.start()].count("\n")
            lineno = base_lineno + line_offset

            # Skip if value is a CSS variable
            if _VAR_RE.search(raw_value):
                continue

            if prop in _JSX_COLOR_PROPS:
                # Reuse CSS color checks by constructing pseudo-CSS line
                css_prop = _camel_to_kebab(prop)
                self._check_colors(
                    rel, f"{css_prop}: {raw_value}", lineno, findings, named_color_re
                )

            elif prop in _JSX_SPACING_PROPS:
                # Extract px values from quoted string
                px_vals = re.findall(r"(\d+)px", raw_value)
                non_exempt = [
                    int(v) for v in px_vals
                    if int(v) not in (0, 1) and int(v) not in spacing_allowlist_px
                ]
                if non_exempt:
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="info",
                        file=rel,
                        line=lineno,
                        message=(
                            f"Hardcoded spacing `{prop}: '{raw_value}'` "
                            f"— consider a spacing token"
                        ),
                        category="hardcoded-spacing",
                        auto_fixable=False,
                    ))

            elif prop in _JSX_FONT_PROPS:
                val = raw_value.lower()
                if val not in _FONT_SIZE_EXEMPT and re.search(
                    r"\d+(?:\.\d+)?(?:px|rem|em|pt)", val
                ):
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="info",
                        file=rel,
                        line=lineno,
                        message=(
                            f"Hardcoded font-size `{raw_value}` "
                            f"— consider a typography token"
                        ),
                        category="hardcoded-font-size",
                        auto_fixable=False,
                    ))

            elif prop in _JSX_ZINDEX_PROPS:
                try:
                    val = int(raw_value)
                    if val not in _ZINDEX_EXEMPT:
                        findings.append(Finding(
                            analyzer=self.name,
                            severity="info",
                            file=rel,
                            line=lineno,
                            message=(
                                f"Hardcoded z-index `{val}` "
                                f"— consider a z-index scale token"
                            ),
                            category="hardcoded-z-index",
                            auto_fixable=False,
                        ))
                except ValueError:
                    pass

        # ── Numeric values:  propName: 123  ──
        for m in _JSX_PROP_NUM_RE.finditer(block):
            prop = m.group(1)
            try:
                num = float(m.group(2))
            except ValueError:
                continue
            line_offset = block[: m.start()].count("\n")
            lineno = base_lineno + line_offset

            if prop in _JSX_SPACING_PROPS:
                int_val = int(num)
                if num == int_val and int_val not in (0, 1) and int_val not in spacing_allowlist_px:
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="info",
                        file=rel,
                        line=lineno,
                        message=(
                            f"Hardcoded spacing `{prop}: {int_val}` (implicit px) "
                            f"— consider a spacing token"
                        ),
                        category="hardcoded-spacing",
                        auto_fixable=False,
                    ))

            elif prop in _JSX_ZINDEX_PROPS:
                int_val = int(num)
                if int_val not in _ZINDEX_EXEMPT:
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="info",
                        file=rel,
                        line=lineno,
                        message=(
                            f"Hardcoded z-index `{int_val}` "
                            f"— consider a z-index scale token"
                        ),
                        category="hardcoded-z-index",
                        auto_fixable=False,
                    ))

    # ── individual CSS checks ─────────────────────────────────────────────────

    def _check_colors(
        self,
        rel: str,
        line: str,
        lineno: int,
        findings: list[Finding],
        named_color_re: re.Pattern = _NAMED_COLOR_PROPS_RE,
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

        m = named_color_re.search(line)
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
        self,
        rel: str,
        line: str,
        lineno: int,
        findings: list[Finding],
        spacing_allowlist_px: frozenset[int] = frozenset(),
    ) -> None:
        m = _SPACING_RE.search(line)
        if not m:
            return
        values = m.group(2).strip()
        # Exempt if ALL tokens are 0px, 1px, or in allowlist
        tokens = re.findall(r"(\d+)px", values)
        non_exempt = [
            t for t in tokens
            if int(t) not in (0, 1) and int(t) not in spacing_allowlist_px
        ]
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


# ─── Utilities ────────────────────────────────────────────────────────────────

def _camel_to_kebab(name: str) -> str:
    """Convert camelCase to kebab-case. E.g. 'backgroundColor' → 'background-color'."""
    return re.sub(r"([A-Z])", lambda m: "-" + m.group(1).lower(), name)


# ─── File Iterator ────────────────────────────────────────────────────────────

def _iter_files(root: Path):
    """Yield all relevant style/component files, skipping junk dirs."""
    for entry in root.rglob("*"):
        if any(part in _SKIP_DIRS for part in entry.parts):
            continue
        if entry.is_file() and entry.suffix in _ALL_EXTS:
            yield entry


def _is_definition_file(path: Path, extra_patterns: list[str] = []) -> bool:
    """Return True if this file is a token/theme definition (allowed to have raw values)."""
    if _DEFAULT_DEFINITION_STEMS.search(path.stem):
        return True
    for pat in extra_patterns:
        if fnmatch.fnmatch(path.stem.lower(), pat.lower()):
            return True
    return False


def _is_excluded(path: Path, root: Path, patterns: list[str]) -> bool:
    """Return True if *path* matches any of the given glob exclude patterns."""
    if not patterns:
        return False
    try:
        rel = path.relative_to(root).as_posix()
    except ValueError:
        rel = path.as_posix()
    for pat in patterns:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(path.name, pat):
            return True
    return False
