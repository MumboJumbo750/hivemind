"""
Analyzer: Dependency Freshness & Security Hints

Detects potentially outdated or insecure dependencies in Python and Node.js
projects without requiring any external services or network access.

Checks:
  1. Python Dependencies (requirements.txt, pyproject.toml):
     - Exactly-pinned (fastapi==0.109.0)  → info: no auto-update range
     - Unpinned (fastapi)                 → warning: non-reproducible builds
     - Deprecated packages                → warning: replacement available

  2. Node Dependencies (package.json):
     - Outdated major versions (configurable current-version map)
     - Duplicate in both dependencies + devDependencies → warning
     - Deprecated packages                → warning: replacement available

  3. Lockfile checks:
     - Missing Node lockfile (package-lock.json / yarn.lock / pnpm-lock.yaml)
       when package.json is present                    → warning
     - Both requirements.txt AND pyproject.toml present in same dir → info

  4. Security hints (zero external deps):
     - Configurable CVE blocklist keyed by package + minimum safe version
     - e.g. {"package": "lodash", "below": "4.17.21", "reason": "..."}

Zero-Dep-Prinzip: Kein Network-Zugriff. Stdlib only (re, json, tomllib, pathlib).

Suppression markers:
  requirements.txt : append  # dep-ok
  package.json     : add "//dep-ok" as a pseudo-dependency (not available)
  — or configure ignore_packages to suppress specific packages globally.

Registered automatically via AnalyzerRegistry (BaseAnalyzer subclass).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

try:
    import tomllib  # Python 3.11+
except ImportError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]

from scripts.analyzers import BaseAnalyzer, Finding

# ─── Skip dirs ────────────────────────────────────────────────────────────────

_SKIP_DIRS: frozenset[str] = frozenset(
    {
        "node_modules", ".git", ".venv", "venv", "__pycache__",
        "dist", "build", ".next", "coverage", "out",
    }
)

# ─── Known deprecated Python packages ────────────────────────────────────────

_PY_DEPRECATED: dict[str, str] = {
    "python-jose": "PyJWT (python-jose is abandoned; use 'pyjwt[cryptography]')",
    "pycrypto": "pycryptodome (pycrypto is unmaintained since 2013)",
    "unsign": "itsdangerous (unsign is unmaintained)",
    "md5": "hashlib (md5 package is redundant, use stdlib hashlib)",
    "sha": "hashlib (sha package is redundant, use stdlib hashlib)",
    "nose": "pytest (nose is unmaintained since 2015)",
    "mock": "unittest.mock (included in stdlib since Python 3.3)",
    "simplejson": "json (simplejson is redundant for most use-cases; stdlib json is fine)",
    "six": "python 3 native code (six is for py2/py3 compat — not needed in py3-only projects)",
    "futures": "concurrent.futures (included in stdlib since Python 3.2)",
    "typing_extensions": None,  # Not deprecated, but note that many things moved to typing
}

# ─── Known deprecated Node packages ──────────────────────────────────────────

_NODE_DEPRECATED: dict[str, str] = {
    "request": "node-fetch, axios, or native fetch (request is archived)",
    "moment": "date-fns or dayjs (moment is in maintenance mode)",
    "lodash": None,  # not deprecated, but security-relevant (see blocklist)
    "underscore": "lodash or native JS methods",
    "bower": "npm or yarn",
    "grunt": "vite, esbuild, or rollup",
    "gulp": "vite, esbuild, or rollup",
    "tslint": "eslint with @typescript-eslint (tslint is archived)",
    "node-uuid": "uuid (node-uuid is deprecated in favor of uuid)",
    "querystring": "URLSearchParams (querystring is a legacy built-in)",
    "mkdirp": "fs.mkdirSync with { recursive: true } (stdlib since Node 10.12)",
    "rimraf": "fs.rmSync with { recursive: true } (stdlib since Node 14.14)",
    "inflight": "Archived, no replacement needed (avoid)",
    "glob": None,  # v7 → v10 break, not deprecated per se
    "domexception": "Use native DOMException (built-in since Node 18)",
    "rollup-plugin-terser": "@rollup/plugin-terser",
    "vue-template-compiler": "@vue/compiler-sfc (for Vue 3)",
    "axios-mock-adapter": None,  # not deprecated
}

# ─── Security blocklist (CVE / known-vulnerable) ──────────────────────────────

DEFAULT_SECURITY_BLOCKLIST: list[dict[str, str]] = [
    {
        "package": "lodash",
        "below": "4.17.21",
        "ecosystem": "node",
        "reason": "CVE-2021-23337 & CVE-2020-8203: Prototype Pollution (fix: upgrade to >=4.17.21)",
    },
    {
        "package": "minimist",
        "below": "1.2.6",
        "ecosystem": "node",
        "reason": "CVE-2021-44906: Prototype Pollution (fix: upgrade to >=1.2.6)",
    },
    {
        "package": "ansi-regex",
        "below": "5.0.1",
        "ecosystem": "node",
        "reason": "CVE-2021-3807: ReDoS vulnerability (fix: upgrade to >=5.0.1)",
    },
    {
        "package": "node-fetch",
        "below": "2.6.7",
        "ecosystem": "node",
        "reason": "CVE-2022-0235: Information exposure (fix: upgrade to >=2.6.7 or >=3.x)",
    },
    {
        "package": "follow-redirects",
        "below": "1.15.4",
        "ecosystem": "node",
        "reason": "CVE-2023-26159: URL Redirection (fix: upgrade to >=1.15.4)",
    },
    {
        "package": "python-jose",
        "below": "9999.0.0",  # all versions — project is abandoned
        "ecosystem": "python",
        "reason": "Abandoned project with unpatched CVEs; replace with 'pyjwt[cryptography]'",
    },
    {
        "package": "pycrypto",
        "below": "9999.0.0",
        "ecosystem": "python",
        "reason": "Unmaintained since 2013; multiple CVEs; replace with 'pycryptodome'",
    },
    {
        "package": "pillow",
        "below": "10.0.1",
        "ecosystem": "python",
        "reason": "CVE-2023-44271 & others: upgrade to >=10.0.1",
    },
    {
        "package": "cryptography",
        "below": "41.0.6",
        "ecosystem": "python",
        "reason": "CVE-2023-49083: NULL ptr dereference (fix: upgrade to >=41.0.6)",
    },
    {
        "package": "requests",
        "below": "2.31.0",
        "ecosystem": "python",
        "reason": "CVE-2023-32681: Proxy-Authorization header leak (fix: upgrade to >=2.31.0)",
    },
    {
        "package": "urllib3",
        "below": "1.26.18",
        "ecosystem": "python",
        "reason": "CVE-2023-45803: Auth header leak on redirect (fix: upgrade >=1.26.18 or >=2.0.7)",
    },
]

# ─── Known current major versions for Node packages ──────────────────────────
# Used to flag packages that are >2 majors behind the known current version.

DEFAULT_NODE_KNOWN_MAJORS: dict[str, int] = {
    "vue": 3,
    "react": 19,
    "react-dom": 19,
    "angular": 19,
    "@angular/core": 19,
    "svelte": 5,
    "next": 15,
    "nuxt": 3,
    "vite": 6,
    "rollup": 4,
    "webpack": 5,
    "eslint": 9,
    "typescript": 5,
    "prettier": 3,
    "jest": 29,
    "vitest": 3,
    "playwright": 1,
    "cypress": 13,
    "express": 5,
    "fastify": 5,
    "axios": 1,
    "lodash": 4,
    "moment": 2,
    "date-fns": 4,
    "dayjs": 1,
    "uuid": 11,
    "zod": 3,
    "pinia": 3,
    "vue-router": 4,
    "@sentry/vue": 9,
    "@sentry/node": 9,
    "tailwindcss": 4,
    "postcss": 8,
    "autoprefixer": 10,
    "sass": 1,
    "bootstrap": 5,
    "three": 0,  # still 0.x (r170 etc)
    "socket.io": 4,
    "socket.io-client": 4,
    "mongoose": 8,
    "sequelize": 6,
    "typeorm": 0,  # still 0.x
    "knex": 3,
    "prisma": 6,
    "@prisma/client": 6,
    "graphql": 16,
    "apollo-server": 4,
    "@apollo/server": 4,
    "rxjs": 7,
    "redux": 5,
    "@reduxjs/toolkit": 2,
    "mobx": 6,
    "immer": 10,
    "yup": 1,
    "joi": 17,
    "ajv": 8,
    "formik": 2,
    "react-hook-form": 7,
    "storybook": 8,
    "@storybook/react": 8,
    "gulp": 5,
    "grunt": 1,
    "nx": 20,
    "turbo": 2,
    "husky": 9,
    "lint-staged": 15,
    "commitlint": 19,
    "semantic-release": 24,
    "lerna": 8,
    "changesets": 2,
    "dotenv": 16,
    "cross-env": 7,
    "ts-node": 10,
    "tsx": 4,
    "esbuild": 0,  # still 0.x
}

# ─── Version parsing ──────────────────────────────────────────────────────────

_VERSION_RE = re.compile(r"^[^0-9]*(\d+)(?:\.(\d+))?(?:\.(\d+))?")
_CARET_RE = re.compile(r"^\^(.+)$")
_TILDE_RE = re.compile(r"^~(.+)$")
_EXACT_RE = re.compile(r"^(\d.*)$")
_WILDCARD_RE = re.compile(r"^[*xX]$|^latest$|^$")


def _parse_version(v: str) -> tuple[int, ...]:
    """Parse a version string into a tuple of ints. Returns (0,) on failure."""
    v = v.strip()
    m = _VERSION_RE.match(v)
    if not m:
        return (0,)
    return tuple(int(x) for x in m.groups() if x is not None)


def _version_lt(a: tuple[int, ...], b: tuple[int, ...]) -> bool:
    """Return True if version a < b."""
    la, lb = len(a), len(b)
    for i in range(max(la, lb)):
        ai = a[i] if i < la else 0
        bi = b[i] if i < lb else 0
        if ai < bi:
            return True
        if ai > bi:
            return False
    return False


# ─── Python requirements parser ───────────────────────────────────────────────

# Matches: name[extras]<op><version>  (simplified)
_PY_REQ_RE = re.compile(
    r"^([A-Za-z0-9_\-\.]+)"          # package name
    r"(?:\[.*?\])?"                    # optional extras
    r"([><=!~^]{1,3}\S+)?"            # optional version spec
    r"(?:\s*;.*)?$"                    # optional environment marker
)

# Matches a single version specifier like ==1.2.3 or >=1.0.0
_VER_SPEC_RE = re.compile(r"([><=!~^]{1,3})\s*(\S+?)(?:[,\s]|$)")

_PY_SUPPRESS_RE = re.compile(r"#\s*dep-ok\b", re.IGNORECASE)


def _is_py_req_line(line: str) -> bool:
    """Return True if the line looks like a requirement (not a comment/option)."""
    stripped = line.strip()
    return bool(stripped) and not stripped.startswith("#") and not stripped.startswith("-")


def _parse_py_req(line: str) -> dict[str, Any] | None:
    """
    Parse a single requirements.txt line.
    Returns dict with keys:
      name, specs (list of (op, version)), raw_line
    or None if the line is not a dependency.
    """
    stripped = line.strip()
    if not stripped or stripped.startswith("#") or stripped.startswith("-"):
        return None
    # Strip inline comment
    spec_part = re.sub(r"\s*#.*$", "", stripped).strip()
    if not spec_part:
        return None
    # Parse name + version specifiers
    name_m = re.match(r"^([A-Za-z0-9_\-\.]+)(?:\[.*?\])?(.*)?$", spec_part)
    if not name_m:
        return None
    raw_name = name_m.group(1)
    # Normalize package name: lowercase, replace - with _
    name = raw_name.lower().replace("-", "_").replace(".", "_")
    remainder = name_m.group(2) or ""
    specs = _VER_SPEC_RE.findall(remainder)
    return {"name": name, "raw_name": raw_name, "specs": specs, "raw_line": stripped}


def _py_pin_type(specs: list[tuple[str, str]]) -> str:
    """
    Classify pin type:
      'unpinned'    — no version spec at all
      'exact'       — == only
      'ranged'      — using >=, <=, ~=, !=, or combination
    """
    if not specs:
        return "unpinned"
    ops = [op for op, _ in specs]
    if ops == ["=="]:
        return "exact"
    return "ranged"


# ─── Node package.json parser ─────────────────────────────────────────────────

_SEMVER_RANGE_RE = re.compile(
    r"^(?P<prefix>[~^>=<]*)(?P<version>\d[\d\.a-zA-Z\-]*)$"
)


def _parse_node_version(raw: str) -> tuple[str, tuple[int, ...]]:
    """
    Parse a Node version specifier like "^3.5.13".
    Returns (prefix, version_tuple).
    prefix: "^", "~", ">=", etc., or "" for exact / special.
    """
    raw = raw.strip()
    if _WILDCARD_RE.match(raw):
        return ("*", (0,))
    m = _SEMVER_RANGE_RE.match(raw)
    if not m:
        return ("", (0,))
    return (m.group("prefix"), _parse_version(m.group("version")))


# ─── Main Analyzer ────────────────────────────────────────────────────────────


class DependencyFreshnessAnalyzer(BaseAnalyzer):
    """
    Checks for stale, unpinned, or insecure dependencies in Python and
    Node.js projects.
    """

    name = "dependency-freshness"
    description = "Detects unpinned, deprecated, or vulnerable dependencies"

    def __init__(
        self,
        *,
        security_blocklist: list[dict[str, str]] | None = None,
        node_known_majors: dict[str, int] | None = None,
        py_deprecated: dict[str, str | None] | None = None,
        node_deprecated: dict[str, str | None] | None = None,
        ignore_packages: set[str] | None = None,
        outdated_majors_threshold: int = 2,
        check_py_pinning: bool = True,
        check_node_pinning: bool = True,
        check_lockfiles: bool = True,
        check_duplicates: bool = True,
        check_security: bool = True,
        check_deprecated: bool = True,
        check_outdated_majors: bool = True,
    ) -> None:
        self._blocklist = security_blocklist if security_blocklist is not None else DEFAULT_SECURITY_BLOCKLIST
        self._node_known_majors = node_known_majors if node_known_majors is not None else DEFAULT_NODE_KNOWN_MAJORS
        self._py_deprecated = py_deprecated if py_deprecated is not None else _PY_DEPRECATED
        self._node_deprecated = node_deprecated if node_deprecated is not None else _NODE_DEPRECATED
        self._ignore = {n.lower().replace("-", "_").replace(".", "_") for n in (ignore_packages or set())}
        self._threshold = outdated_majors_threshold
        self._check_py_pinning = check_py_pinning
        self._check_node_pinning = check_node_pinning
        self._check_lockfiles = check_lockfiles
        self._check_duplicates = check_duplicates
        self._check_security = check_security
        self._check_deprecated = check_deprecated
        self._check_outdated_majors = check_outdated_majors

    # ─── Public entry point ────────────────────────────────────────────────

    def analyze(self, root: Path) -> list[Finding]:
        findings: list[Finding] = []
        root = root.resolve()

        for dirpath, dirnames, filenames in self._walk(root):
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]

            rel_dir = Path(dirpath).relative_to(root)

            # Python: requirements*.txt
            for fname in filenames:
                if re.match(r"requirements.*\.txt$", fname, re.IGNORECASE):
                    fpath = Path(dirpath) / fname
                    findings.extend(self._analyze_requirements_txt(root, fpath))

            # Python: pyproject.toml
            if "pyproject.toml" in filenames:
                fpath = Path(dirpath) / "pyproject.toml"
                findings.extend(self._analyze_pyproject_toml(root, fpath))

            # Lockfile consistency: both requirements.txt and pyproject.toml?
            if self._check_lockfiles:
                has_req = any(re.match(r"requirements.*\.txt$", f, re.IGNORECASE) for f in filenames)
                has_pyproject = "pyproject.toml" in filenames
                if has_req and has_pyproject:
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="info",
                        file=str(rel_dir / "pyproject.toml") if str(rel_dir) != "." else "pyproject.toml",
                        line=None,
                        message=(
                            "Both requirements*.txt and pyproject.toml found in the same directory. "
                            "Consider consolidating dependency definitions to avoid drift."
                        ),
                        category="dep-dual-source",
                    ))

            # Node: package.json
            if "package.json" in filenames:
                fpath = Path(dirpath) / "package.json"
                findings.extend(self._analyze_package_json(root, fpath))

                # Lockfile check
                if self._check_lockfiles:
                    lockfiles = {"package-lock.json", "yarn.lock", "pnpm-lock.yaml"}
                    has_lock = any(lf in filenames for lf in lockfiles)
                    if not has_lock:
                        findings.append(Finding(
                            analyzer=self.name,
                            severity="warning",
                            file=self._rel(root, fpath),
                            line=None,
                            message=(
                                "No lockfile found (package-lock.json / yarn.lock / pnpm-lock.yaml). "
                                "Without a lockfile builds are non-reproducible."
                            ),
                            category="missing-lockfile",
                        ))

        return findings

    # ─── Walk helper ──────────────────────────────────────────────────────

    def _walk(self, root: Path):
        import os
        for dirpath, dirnames, filenames in os.walk(root):
            # prune skip dirs in-place so os.walk won't recurse into them
            dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
            yield dirpath, dirnames, filenames

    # ─── requirements.txt ─────────────────────────────────────────────────

    def _analyze_requirements_txt(self, root: Path, fpath: Path) -> list[Finding]:
        findings: list[Finding] = []
        rel = self._rel(root, fpath)
        try:
            lines = fpath.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            return findings

        for lineno, raw_line in enumerate(lines, start=1):
            # Suppression
            if _PY_SUPPRESS_RE.search(raw_line):
                continue

            parsed = _parse_py_req(raw_line)
            if parsed is None:
                continue

            norm_name = parsed["name"]
            if norm_name in self._ignore:
                continue

            pin_type = _py_pin_type(parsed["specs"])

            if self._check_py_pinning:
                if pin_type == "unpinned":
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="warning",
                        file=rel,
                        line=lineno,
                        message=(
                            f"'{parsed['raw_name']}' has no version specifier — "
                            "builds are non-reproducible (pin with ==x.y.z or >=x,<y)"
                        ),
                        category="dep-unpinned",
                    ))
                elif pin_type == "exact":
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="info",
                        file=rel,
                        line=lineno,
                        message=(
                            f"'{parsed['raw_name']}' is exactly pinned (==). "
                            "No automatic patch updates — review periodically."
                        ),
                        category="dep-exact-pin",
                    ))

            # Deprecated check
            if self._check_deprecated:
                dep_key = norm_name.replace("_", "-")
                # Try both normalized forms
                replacement = None
                found_dep = False
                for key, rep in self._py_deprecated.items():
                    nkey = key.lower().replace("-", "_").replace(".", "_")
                    if nkey == norm_name:
                        replacement = rep
                        found_dep = True
                        break
                if found_dep:
                    msg = f"'{parsed['raw_name']}' is deprecated."
                    if replacement:
                        msg += f" Consider replacing with: {replacement}"
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="warning",
                        file=rel,
                        line=lineno,
                        message=msg,
                        category="dep-deprecated",
                    ))

            # Security check
            if self._check_security:
                findings.extend(
                    self._check_blocklist(rel, lineno, norm_name, parsed["raw_name"], parsed["specs"], "python")
                )

        return findings

    # ─── pyproject.toml ───────────────────────────────────────────────────

    def _analyze_pyproject_toml(self, root: Path, fpath: Path) -> list[Finding]:
        findings: list[Finding] = []
        rel = self._rel(root, fpath)
        try:
            raw = fpath.read_bytes()
        except OSError:
            return findings

        deps: list[str] = []

        if tomllib is not None:
            try:
                data = tomllib.loads(raw.decode("utf-8", errors="replace"))
                # PEP 621: [project] dependencies
                pep621 = data.get("project", {}).get("dependencies", [])
                deps.extend(pep621)
                # Poetry: [tool.poetry.dependencies]
                poetry = data.get("tool", {}).get("poetry", {}).get("dependencies", {})
                for pkg, spec in poetry.items():
                    if pkg.lower() == "python":
                        continue
                    if isinstance(spec, str):
                        deps.append(f"{pkg}{spec}")
                    elif isinstance(spec, dict):
                        ver = spec.get("version", "")
                        deps.append(f"{pkg}{ver}")
            except Exception:
                # Fall back to regex
                deps = self._extract_toml_deps_regex(raw.decode("utf-8", errors="replace"))
        else:
            deps = self._extract_toml_deps_regex(raw.decode("utf-8", errors="replace"))

        for dep_str in deps:
            parsed = _parse_py_req(dep_str.strip())
            if parsed is None:
                continue
            norm_name = parsed["name"]
            if norm_name in self._ignore:
                continue

            pin_type = _py_pin_type(parsed["specs"])

            if self._check_py_pinning and pin_type == "unpinned":
                findings.append(Finding(
                    analyzer=self.name,
                    severity="warning",
                    file=rel,
                    line=None,
                    message=(
                        f"'{parsed['raw_name']}' in pyproject.toml has no version specifier — "
                        "builds are non-reproducible."
                    ),
                    category="dep-unpinned",
                ))

            if self._check_deprecated:
                for key, replacement in self._py_deprecated.items():
                    nkey = key.lower().replace("-", "_").replace(".", "_")
                    if nkey == norm_name:
                        msg = f"'{parsed['raw_name']}' is deprecated."
                        if replacement:
                            msg += f" Consider replacing with: {replacement}"
                        findings.append(Finding(
                            analyzer=self.name,
                            severity="warning",
                            file=rel,
                            line=None,
                            message=msg,
                            category="dep-deprecated",
                        ))
                        break

            if self._check_security:
                findings.extend(
                    self._check_blocklist(rel, None, norm_name, parsed["raw_name"], parsed["specs"], "python")
                )

        return findings

    def _extract_toml_deps_regex(self, content: str) -> list[str]:
        """Fallback: extract dependency strings from toml using regex."""
        deps: list[str] = []
        # Match quoted strings inside 'dependencies = [...]'
        in_deps = False
        for line in content.splitlines():
            stripped = line.strip()
            if re.match(r"dependencies\s*=\s*\[", stripped):
                in_deps = True
            elif in_deps:
                if stripped.startswith("]"):
                    in_deps = False
                else:
                    m = re.search(r'"([^"]+)"', stripped)
                    if m:
                        deps.append(m.group(1))
        return deps

    # ─── package.json ─────────────────────────────────────────────────────

    def _analyze_package_json(self, root: Path, fpath: Path) -> list[Finding]:
        findings: list[Finding] = []
        rel = self._rel(root, fpath)

        try:
            data = json.loads(fpath.read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            return findings

        deps: dict[str, str] = data.get("dependencies", {})
        dev_deps: dict[str, str] = data.get("devDependencies", {})

        # Duplicates check
        if self._check_duplicates:
            duplicates = set(deps.keys()) & set(dev_deps.keys())
            for pkg in sorted(duplicates):
                findings.append(Finding(
                    analyzer=self.name,
                    severity="warning",
                    file=rel,
                    line=None,
                    message=(
                        f"'{pkg}' appears in both dependencies and devDependencies. "
                        "Remove it from one of the sections."
                    ),
                    category="dep-duplicate",
                ))

        all_node_deps: dict[str, str] = {**deps, **dev_deps}

        for pkg_name, raw_version in all_node_deps.items():
            norm_name = pkg_name.lower().replace("-", "_").replace(".", "_")
            if norm_name in self._ignore or pkg_name.lower().replace("-", "_").replace(".", "_") in self._ignore:
                continue

            prefix, version_tuple = _parse_node_version(str(raw_version))

            # Pinning check: unpinned (* / latest / empty)
            if self._check_node_pinning and prefix == "*":
                findings.append(Finding(
                    analyzer=self.name,
                    severity="warning",
                    file=rel,
                    line=None,
                    message=(
                        f"'{pkg_name}': version '{raw_version}' is unpinned — "
                        "builds are non-reproducible."
                    ),
                    category="dep-unpinned",
                ))

            # Outdated major version check
            if self._check_outdated_majors and version_tuple and version_tuple != (0,):
                known_major = self._node_known_majors.get(pkg_name)
                if known_major is not None:
                    pkg_major = version_tuple[0]
                    if (known_major - pkg_major) > self._threshold:
                        findings.append(Finding(
                            analyzer=self.name,
                            severity="warning",
                            file=rel,
                            line=None,
                            message=(
                                f"'{pkg_name}' uses major v{pkg_major} (spec: '{raw_version}'), "
                                f"but current major is v{known_major} — "
                                f"more than {self._threshold} majors behind."
                            ),
                            category="dep-outdated-major",
                        ))

            dep_key = pkg_name.lower()

            # Deprecated check
            if self._check_deprecated:
                # check exact name match
                for dep_pkg, replacement in self._node_deprecated.items():
                    if dep_pkg.lower() == dep_key:
                        msg = f"'{pkg_name}' is deprecated or in maintenance mode."
                        if replacement:
                            msg += f" Consider: {replacement}"
                        findings.append(Finding(
                            analyzer=self.name,
                            severity="warning",
                            file=rel,
                            line=None,
                            message=msg,
                            category="dep-deprecated",
                        ))
                        break

            # Security check
            if self._check_security:
                findings.extend(
                    self._check_blocklist(rel, None, dep_key, pkg_name, [], "node", raw_version=raw_version)
                )

        return findings

    # ─── Security blocklist helper ────────────────────────────────────────

    def _check_blocklist(
        self,
        rel: str,
        lineno: int | None,
        norm_name: str,
        raw_name: str,
        specs: list[tuple[str, str]],
        ecosystem: str,
        *,
        raw_version: str | None = None,
    ) -> list[Finding]:
        findings: list[Finding] = []
        pkg_lower = raw_name.lower()

        for entry in self._blocklist:
            if entry.get("ecosystem", ecosystem) != ecosystem:
                continue
            if entry["package"].lower() != pkg_lower:
                # Normalize and retry
                entry_norm = entry["package"].lower().replace("-", "_")
                if entry_norm != norm_name:
                    continue

            safe_version = _parse_version(entry["below"])

            # Determine installed/declared version
            installed: tuple[int, ...] | None = None
            if specs:
                # Pick the == spec if present, otherwise the >= spec
                for op, ver in specs:
                    if op == "==":
                        installed = _parse_version(ver)
                        break
                if installed is None:
                    for op, ver in specs:
                        if op in (">=", ">"):
                            installed = _parse_version(ver)
                            break
            elif raw_version:
                _, installed = _parse_node_version(raw_version)
                if installed == (0,):
                    installed = None

            if installed is not None:
                # Only flag if installed version < safe_version
                if _version_lt(installed, safe_version):
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="error",
                        file=rel,
                        line=lineno,
                        message=(
                            f"⚠ SECURITY: '{raw_name}' "
                            f"(declared: {'.'.join(str(x) for x in installed)}) "
                            f"is below safe version {entry['below']}. "
                            f"{entry['reason']}"
                        ),
                        category="dep-security",
                    ))
            else:
                # Version unknown — warn that it's on the blocklist
                # (only if entry["below"] is not a catch-all 9999.x)
                if _parse_version(entry["below"])[0] >= 9000:
                    findings.append(Finding(
                        analyzer=self.name,
                        severity="error",
                        file=rel,
                        line=lineno,
                        message=(
                            f"⚠ SECURITY: '{raw_name}' is on the security blocklist. "
                            f"{entry['reason']}"
                        ),
                        category="dep-security",
                    ))

        return findings
