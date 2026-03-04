"""
Unit tests for DependencyFreshnessAnalyzer.

Run (canonical):
    make health-test

Or directly:
    podman compose exec -w /workspace -e PYTHONPATH=/workspace:/app backend \
        /app/.venv/bin/pytest scripts/analyzers/tests/test_dependency_freshness.py -v
"""

from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from scripts.analyzers.dependency_freshness import (
    DependencyFreshnessAnalyzer,
    _parse_version,
    _version_lt,
    _parse_py_req,
    _py_pin_type,
    _parse_node_version,
)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _write(tmp: Path, rel: str, content: str) -> Path:
    p = tmp / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(textwrap.dedent(content), encoding="utf-8")
    return p


def _analyzer(**kwargs) -> DependencyFreshnessAnalyzer:
    return DependencyFreshnessAnalyzer(**kwargs)


def _cats(findings) -> list[str]:
    return [f.category for f in findings]


def _msgs(findings) -> list[str]:
    return [f.message for f in findings]


# ─── Version parsing utils ────────────────────────────────────────────────────

def test_parse_version_basic():
    assert _parse_version("1.2.3") == (1, 2, 3)


def test_parse_version_with_prefix():
    assert _parse_version("v1.2.3") == (1, 2, 3)
    assert _parse_version("V1.2.3") == (1, 2, 3)


def test_parse_version_partial():
    assert _parse_version("3") == (3,)
    assert _parse_version("3.5") == (3, 5)


def test_parse_version_invalid():
    assert _parse_version("latest") == (0,)
    assert _parse_version("*") == (0,)
    assert _parse_version("") == (0,)


def test_version_lt_basic():
    assert _version_lt((1, 0, 0), (2, 0, 0))
    assert not _version_lt((2, 0, 0), (1, 0, 0))
    assert not _version_lt((1, 0, 0), (1, 0, 0))


def test_version_lt_different_lengths():
    assert _version_lt((1, 0), (1, 0, 1))
    assert not _version_lt((1, 0, 1), (1, 0))


# ─── _parse_py_req ────────────────────────────────────────────────────────────

def test_parse_py_req_exact():
    r = _parse_py_req("fastapi==0.115.6")
    assert r is not None
    assert r["raw_name"] == "fastapi"
    assert r["specs"] == [("==", "0.115.6")]


def test_parse_py_req_unpinned():
    r = _parse_py_req("fastapi")
    assert r is not None
    assert r["specs"] == []


def test_parse_py_req_range():
    r = _parse_py_req("requests>=2.28.0,<3.0.0")
    assert r is not None
    assert any(op == ">=" for op, _ in r["specs"])


def test_parse_py_req_with_extras():
    r = _parse_py_req("uvicorn[standard]==0.34.0")
    assert r is not None
    assert r["raw_name"] == "uvicorn"


def test_parse_py_req_comment_line():
    assert _parse_py_req("# this is a comment") is None
    assert _parse_py_req("") is None
    assert _parse_py_req("-r other.txt") is None


def test_parse_py_req_with_marker():
    r = _parse_py_req("pywin32==306; sys_platform == 'win32'")
    assert r is not None
    assert r["raw_name"] == "pywin32"


# ─── _py_pin_type ─────────────────────────────────────────────────────────────

def test_py_pin_type_exact():
    assert _py_pin_type([("==", "1.0.0")]) == "exact"


def test_py_pin_type_unpinned():
    assert _py_pin_type([]) == "unpinned"


def test_py_pin_type_ranged():
    assert _py_pin_type([(">=", "1.0.0"), ("<", "2.0.0")]) == "ranged"


# ─── _parse_node_version ──────────────────────────────────────────────────────

def test_parse_node_version_caret():
    prefix, ver = _parse_node_version("^3.5.13")
    assert prefix == "^"
    assert ver == (3, 5, 13)


def test_parse_node_version_tilde():
    prefix, ver = _parse_node_version("~1.2.3")
    assert prefix == "~"
    assert ver == (1, 2, 3)


def test_parse_node_version_wildcard():
    prefix, ver = _parse_node_version("*")
    assert prefix == "*"


def test_parse_node_version_exact():
    prefix, ver = _parse_node_version("3.5.13")
    assert ver == (3, 5, 13)


# ─── Python: requirements.txt ─────────────────────────────────────────────────

def test_py_unpinned_flagged(tmp_path):
    _write(tmp_path, "requirements.txt", """\
        fastapi
        requests>=2.28.0
    """)
    a = _analyzer(check_node_pinning=False, check_lockfiles=False)
    findings = a.analyze(tmp_path)
    unpinned = [f for f in findings if f.category == "dep-unpinned"]
    assert any("fastapi" in f.message for f in unpinned)


def test_py_unpinned_ranged_not_flagged(tmp_path):
    """requests>=2.28.0 is a range — not flagged as unpinned."""
    _write(tmp_path, "requirements.txt", "requests>=2.28.0,<3.0.0\n")
    a = _analyzer(check_node_pinning=False, check_lockfiles=False)
    findings = a.analyze(tmp_path)
    unpinned = [f for f in findings if f.category == "dep-unpinned"]
    assert not any("requests" in f.message for f in unpinned)


def test_py_exact_pin_is_info(tmp_path):
    _write(tmp_path, "requirements.txt", "fastapi==0.115.6\n")
    a = _analyzer(check_node_pinning=False, check_lockfiles=False, check_security=False)
    findings = a.analyze(tmp_path)
    info = [f for f in findings if f.category == "dep-exact-pin"]
    assert any("fastapi" in f.message for f in info)
    assert all(f.severity == "info" for f in info)


def test_py_deprecated_package_flagged(tmp_path):
    _write(tmp_path, "requirements.txt", "python-jose[cryptography]==3.3.0\n")
    a = _analyzer(check_node_pinning=False, check_lockfiles=False, check_security=False)
    findings = a.analyze(tmp_path)
    deprecated = [f for f in findings if f.category == "dep-deprecated"]
    assert any("python-jose" in f.message for f in deprecated)
    assert all(f.severity == "warning" for f in deprecated)


def test_py_comment_suppression(tmp_path):
    _write(tmp_path, "requirements.txt", "fastapi  # dep-ok\n")
    a = _analyzer(check_node_pinning=False, check_lockfiles=False)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "dep-unpinned" and "fastapi" in f.message for f in findings)


def test_py_security_blocklist_exact_version(tmp_path):
    """Pinned version below safe threshold → error."""
    _write(tmp_path, "requirements.txt", "pillow==9.0.0\n")
    a = _analyzer(
        check_node_pinning=False, check_lockfiles=False, check_deprecated=False,
        security_blocklist=[
            {"package": "pillow", "below": "10.0.1", "ecosystem": "python", "reason": "Test CVE"},
        ],
    )
    findings = a.analyze(tmp_path)
    sec = [f for f in findings if f.category == "dep-security"]
    assert len(sec) == 1
    assert sec[0].severity == "error"
    assert "pillow" in sec[0].message.lower()


def test_py_security_blocklist_safe_version_not_flagged(tmp_path):
    """Pinned version >= safe version → no finding."""
    _write(tmp_path, "requirements.txt", "pillow==10.2.0\n")
    a = _analyzer(
        check_node_pinning=False, check_lockfiles=False, check_deprecated=False,
        security_blocklist=[
            {"package": "pillow", "below": "10.0.1", "ecosystem": "python", "reason": "Test CVE"},
        ],
    )
    findings = a.analyze(tmp_path)
    assert not any(f.category == "dep-security" for f in findings)


def test_py_ignore_package(tmp_path):
    """ignore_packages suppresses all findings for that package."""
    _write(tmp_path, "requirements.txt", "fastapi\n")
    a = _analyzer(
        check_node_pinning=False, check_lockfiles=False,
        ignore_packages={"fastapi"},
    )
    findings = a.analyze(tmp_path)
    assert not any("fastapi" in f.message for f in findings)


def test_skip_dirs_not_analyzed(tmp_path):
    """node_modules and .venv should not be analyzed."""
    _write(tmp_path, "node_modules/some-lib/requirements.txt", "fastapi\n")
    _write(tmp_path, ".venv/lib/requirements.txt", "fastapi\n")
    a = _analyzer(check_lockfiles=False)
    findings = a.analyze(tmp_path)
    # No findings from skip dirs
    assert all("node_modules" not in f.file and ".venv" not in f.file for f in findings)


# ─── Python: pyproject.toml ───────────────────────────────────────────────────

def test_pyproject_pep621_unpinned(tmp_path):
    _write(tmp_path, "pyproject.toml", """\
        [project]
        name = "test"
        dependencies = [
            "requests",
            "fastapi>=0.100.0",
        ]
    """)
    a = _analyzer(check_node_pinning=False, check_lockfiles=False, check_security=False,
                  check_deprecated=False)
    findings = a.analyze(tmp_path)
    unpinned = [f for f in findings if f.category == "dep-unpinned"]
    assert any("requests" in f.message for f in unpinned)
    assert not any("fastapi" in f.message for f in unpinned)


def test_pyproject_deprecated_pkg(tmp_path):
    _write(tmp_path, "pyproject.toml", """\
        [project]
        name = "test"
        dependencies = [
            "python-jose[cryptography]>=3.3.0",
        ]
    """)
    a = _analyzer(check_node_pinning=False, check_lockfiles=False, check_security=False)
    findings = a.analyze(tmp_path)
    assert any(f.category == "dep-deprecated" and "python-jose" in f.message for f in findings)


# ─── Lockfile checks ──────────────────────────────────────────────────────────

def test_missing_lockfile_flagged(tmp_path):
    _write(tmp_path, "package.json", json.dumps({"dependencies": {}}))
    a = _analyzer(check_py_pinning=False, check_node_pinning=False,
                  check_security=False, check_deprecated=False,
                  check_outdated_majors=False, check_duplicates=False)
    findings = a.analyze(tmp_path)
    assert any(f.category == "missing-lockfile" for f in findings)
    assert any(f.severity == "warning" for f in findings if f.category == "missing-lockfile")


def test_lockfile_present_not_flagged(tmp_path):
    _write(tmp_path, "package.json", json.dumps({"dependencies": {}}))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(check_py_pinning=False, check_node_pinning=False,
                  check_security=False, check_deprecated=False,
                  check_outdated_majors=False, check_duplicates=False)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "missing-lockfile" for f in findings)


def test_yarn_lock_accepted(tmp_path):
    _write(tmp_path, "package.json", json.dumps({"dependencies": {}}))
    _write(tmp_path, "yarn.lock", "# yarn lockfile v1\n")
    a = _analyzer(check_py_pinning=False, check_node_pinning=False,
                  check_security=False, check_deprecated=False,
                  check_outdated_majors=False, check_duplicates=False)
    findings = a.analyze(tmp_path)
    assert not any(f.category == "missing-lockfile" for f in findings)


def test_dual_source_info(tmp_path):
    """Both requirements.txt and pyproject.toml in same dir → info finding."""
    _write(tmp_path, "requirements.txt", "fastapi==0.115.6\n")
    _write(tmp_path, "pyproject.toml", '[project]\nname="test"\n')
    a = _analyzer(check_node_pinning=False, check_security=False, check_deprecated=False,
                  check_outdated_majors=False)
    findings = a.analyze(tmp_path)
    assert any(f.category == "dep-dual-source" for f in findings)


# ─── Node: package.json ───────────────────────────────────────────────────────

def test_node_duplicate_dependency(tmp_path):
    _write(tmp_path, "package.json", json.dumps({
        "dependencies": {"lodash": "^4.17.21"},
        "devDependencies": {"lodash": "^4.17.21"},
    }))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(check_py_pinning=False, check_security=False, check_deprecated=False,
                  check_outdated_majors=False)
    findings = a.analyze(tmp_path)
    assert any(f.category == "dep-duplicate" and "lodash" in f.message for f in findings)
    assert all(f.severity == "warning" for f in findings if f.category == "dep-duplicate")


def test_node_outdated_major(tmp_path):
    """eslint ^5 when current is 9 → >2 majors behind → warning."""
    _write(tmp_path, "package.json", json.dumps({
        "devDependencies": {"eslint": "^5.0.0"},
    }))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(
        check_py_pinning=False, check_security=False, check_deprecated=False,
        check_duplicates=False,
        node_known_majors={"eslint": 9},
        outdated_majors_threshold=2,
    )
    findings = a.analyze(tmp_path)
    assert any(f.category == "dep-outdated-major" and "eslint" in f.message for f in findings)


def test_node_current_major_not_flagged(tmp_path):
    """eslint ^9 when current is 9 → not flagged."""
    _write(tmp_path, "package.json", json.dumps({
        "devDependencies": {"eslint": "^9.0.0"},
    }))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(
        check_py_pinning=False, check_security=False, check_deprecated=False,
        check_duplicates=False,
        node_known_majors={"eslint": 9},
    )
    findings = a.analyze(tmp_path)
    assert not any(f.category == "dep-outdated-major" and "eslint" in f.message for f in findings)


def test_node_deprecated_package(tmp_path):
    _write(tmp_path, "package.json", json.dumps({
        "dependencies": {"request": "^2.88.2"},
    }))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(check_py_pinning=False, check_security=False,
                  check_outdated_majors=False, check_duplicates=False)
    findings = a.analyze(tmp_path)
    assert any(f.category == "dep-deprecated" and "request" in f.message for f in findings)


def test_node_security_blocklist_version_below(tmp_path):
    """lodash ^4.17.20 → below 4.17.21 → security error."""
    _write(tmp_path, "package.json", json.dumps({
        "dependencies": {"lodash": "^4.17.20"},
    }))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(
        check_py_pinning=False, check_deprecated=False, check_outdated_majors=False,
        check_duplicates=False,
        security_blocklist=[{
            "package": "lodash", "below": "4.17.21",
            "ecosystem": "node", "reason": "Prototype Pollution",
        }],
    )
    findings = a.analyze(tmp_path)
    sec = [f for f in findings if f.category == "dep-security"]
    assert len(sec) == 1
    assert sec[0].severity == "error"
    assert "lodash" in sec[0].message.lower()


def test_node_security_blocklist_version_safe(tmp_path):
    """lodash ^4.17.21 → exactly safe → no finding."""
    _write(tmp_path, "package.json", json.dumps({
        "dependencies": {"lodash": "^4.17.21"},
    }))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(
        check_py_pinning=False, check_deprecated=False, check_outdated_majors=False,
        check_duplicates=False,
        security_blocklist=[{
            "package": "lodash", "below": "4.17.21",
            "ecosystem": "node", "reason": "Prototype Pollution",
        }],
    )
    findings = a.analyze(tmp_path)
    assert not any(f.category == "dep-security" for f in findings)


def test_node_unpinned_wildcard(tmp_path):
    _write(tmp_path, "package.json", json.dumps({
        "dependencies": {"axios": "*"},
    }))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(
        check_py_pinning=False, check_security=False, check_deprecated=False,
        check_outdated_majors=False, check_duplicates=False,
    )
    findings = a.analyze(tmp_path)
    assert any(f.category == "dep-unpinned" and "axios" in f.message for f in findings)


def test_node_caret_not_flagged_as_unpinned(tmp_path):
    """^3.5.13 is a caret range, not wildcard → not flagged as unpinned."""
    _write(tmp_path, "package.json", json.dumps({
        "dependencies": {"vue": "^3.5.13"},
    }))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(
        check_py_pinning=False, check_security=False, check_deprecated=False,
        check_outdated_majors=False, check_duplicates=False,
    )
    findings = a.analyze(tmp_path)
    assert not any(f.category == "dep-unpinned" and "vue" in f.message for f in findings)


def test_invalid_package_json_skipped(tmp_path):
    """Malformed package.json should not crash the analyzer."""
    _write(tmp_path, "package.json", "this is not JSON {{}")
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer()
    findings = a.analyze(tmp_path)
    # No crash, no findings about the file
    assert all(f.category != "dep-duplicate" for f in findings)


def test_node_ecosystem_check_doesnt_mix_python(tmp_path):
    """Python blocklist entries should not trigger for Node packages."""
    _write(tmp_path, "package.json", json.dumps({
        "dependencies": {"pillow": "^9.0.0"},
    }))
    _write(tmp_path, "package-lock.json", "{}")
    a = _analyzer(
        check_py_pinning=False, check_deprecated=False, check_outdated_majors=False,
        check_duplicates=False,
        security_blocklist=[{
            "package": "pillow", "below": "10.0.1",
            "ecosystem": "python", "reason": "Test",
        }],
    )
    findings = a.analyze(tmp_path)
    assert not any(f.category == "dep-security" and "pillow" in f.message for f in findings)


# ─── Integration: real project files ──────────────────────────────────────────

def test_real_requirements_txt_no_crash(tmp_path):
    """The actual backend/requirements.txt must not crash the analyzer."""
    import os
    # Find the real requirements.txt relative to this test file
    here = Path(__file__).parent
    # Try workspace root paths
    candidates = [
        here.parent.parent.parent / "backend" / "requirements.txt",
        Path("/workspace/backend/requirements.txt"),
    ]
    req_file = next((p for p in candidates if p.exists()), None)
    if req_file is None:
        pytest.skip("backend/requirements.txt not found")

    # Copy to tmp to avoid scanning unrelated files
    (tmp_path / "requirements.txt").write_bytes(req_file.read_bytes())
    a = _analyzer(check_lockfiles=False, check_node_pinning=False)
    findings = a.analyze(tmp_path)
    # All findings should have valid structure
    for f in findings:
        assert f.analyzer == "dependency-freshness"
        assert f.severity in ("error", "warning", "info")
        assert f.category


def test_real_package_json_no_crash(tmp_path):
    """The actual frontend/package.json must not crash the analyzer."""
    candidates = [
        Path(__file__).parent.parent.parent.parent / "frontend" / "package.json",
        Path("/workspace/frontend/package.json"),
    ]
    pkg_file = next((p for p in candidates if p.exists()), None)
    if pkg_file is None:
        pytest.skip("frontend/package.json not found")

    (tmp_path / "package.json").write_bytes(pkg_file.read_bytes())
    (tmp_path / "package-lock.json").write_text("{}")
    a = _analyzer(check_py_pinning=False)
    findings = a.analyze(tmp_path)
    for f in findings:
        assert f.analyzer == "dependency-freshness"
        assert f.severity in ("error", "warning", "info")
