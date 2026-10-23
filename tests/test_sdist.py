"""The built distributions are public. Whatever is in dist/ may contain only the package, its guides and examples,
the README, pyproject and the metadata setuptools writes. Skips when nothing has been built."""
from __future__ import annotations

import glob
import os
import re
import tarfile
import zipfile

import pytest

from _wordlist import banned

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ALLOWED_SDIST = re.compile(
    r"^aadc_mcp-[^/]+/(PKG-INFO|README\.md|pyproject\.toml|setup\.cfg|MANIFEST\.in|LICENSE|CHANGELOG\.md"
    r"|aadc_mcp/[^/]+\.py|aadc_mcp/guides/[^/]+\.md|aadc_mcp/examples/[^/]+\.py"
    r"|aadc_mcp\.egg-info/[^/]+)$"
)
ALLOWED_WHEEL = re.compile(
    r"^(aadc_mcp/[^/]+\.py|aadc_mcp/guides/[^/]+\.md|aadc_mcp/examples/[^/]+\.py"
    r"|aadc_mcp-[^/]+\.dist-info/(METADATA|WHEEL|RECORD|entry_points\.txt|top_level\.txt|licenses/[^/]+))$"
)
INTERNAL = banned()
CLIENTS = re.compile(r"Claude|Codex|ChatGPT", re.IGNORECASE)   # the README, embedded in the metadata, may name clients


def _internal_hit(text):
    return next((m.group(0) for m in INTERNAL.finditer(text) if not CLIENTS.fullmatch(m.group(0))), None)


def _dists(pattern):
    found = sorted(glob.glob(os.path.join(ROOT, "dist", pattern)))
    if not found:
        pytest.skip(f"no {pattern} in dist/ (run python -m build first)")
    return found


def test_sdist_members_are_only_the_public_files():
    for path in _dists("*.tar.gz"):
        with tarfile.open(path) as tar:
            names = [m.name for m in tar.getmembers() if m.isfile()]
            bad = [n for n in names if not ALLOWED_SDIST.match(n)]
            assert not bad, f"{os.path.basename(path)} carries files that are not public: {bad}"
            pkg_info = tar.extractfile([m for m in tar.getmembers() if m.name.endswith("/PKG-INFO")][0]).read().decode()
            assert not _internal_hit(pkg_info), f"PKG-INFO carries an internal host, path or name: {_internal_hit(pkg_info)!r}"


def test_wheel_members_are_only_the_public_files():
    for path in _dists("*.whl"):
        with zipfile.ZipFile(path) as whl:
            names = [n for n in whl.namelist() if not n.endswith("/")]
            bad = [n for n in names if not ALLOWED_WHEEL.match(n)]
            assert not bad, f"{os.path.basename(path)} carries files that are not public: {bad}"
            meta = whl.read([n for n in names if n.endswith("METADATA")][0]).decode()
            assert not _internal_hit(meta), f"METADATA carries an internal host, path or name: {_internal_hit(meta)!r}"
            assert "mcp-name: com.matlogica/aadc-mcp" in meta, "the registry ownership marker must ship in the README"


def test_sdist_gate_fires_on_a_test_file():
    """Prove the allow-list rejects what it was written to reject."""
    assert not ALLOWED_SDIST.match("aadc_mcp-0.1.0/tests/test_stealth.py")
    assert not ALLOWED_SDIST.match("aadc_mcp-0.1.0/PLAN-2026-10-21.md")
    assert ALLOWED_SDIST.match("aadc_mcp-0.1.0/aadc_mcp/guides/versions.md")
    assert not ALLOWED_WHEEL.match("aadc_mcp/tapes/x.tape")
