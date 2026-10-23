"""Every ```python block in the two how-to guides must run as written, under this interpreter, in an empty directory.
A block whose first line is `# needs: quantlib` is skipped where no AADC QuantLib build is installed."""
from __future__ import annotations

import importlib.util
import os
import re
import subprocess
import sys

import pytest

GUIDES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "aadc_mcp", "guides")
HAVE_QL = any(importlib.util.find_spec(m) is not None for m in ("aadc_quantlib_tracing", "aadc_quantlib"))
HAVE_TRACING = importlib.util.find_spec("aadc_quantlib_tracing") is not None
BLOCK = re.compile(r"```python\n(.*?)```", re.S)


def _blocks(name):
    with open(os.path.join(GUIDES, name), encoding="utf-8") as fh:
        text = fh.read()
    found = [(i + 1, b) for i, b in enumerate(BLOCK.findall(text))]
    assert found, f"{name} has no python blocks"
    return found


def _run(code, tmp_path, timeout=240):
    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "AADC_TRACE_OUT": str(tmp_path / "out.tape")})
    env.pop("AADC_TRACE", None)
    script = tmp_path / "snippet.py"
    script.write_text(code, encoding="utf-8")
    return subprocess.run([sys.executable, str(script)], cwd=tmp_path, env=env, capture_output=True, text=True,
                          timeout=timeout)


@pytest.mark.parametrize("guide", ["aadc-howto.md", "tracer-howto.md"])
def test_every_snippet_runs(guide, tmp_path):
    for n, code in _blocks(guide):
        first = code.strip().splitlines()[0]
        if first.startswith("# needs: quantlib-tracing") and not HAVE_TRACING:
            continue
        if first.startswith("# needs: quantlib") and not HAVE_QL:
            continue
        d = tmp_path / f"block{n}"
        d.mkdir()
        r = _run(code, d)
        assert r.returncode == 0, f"{guide} block {n} failed:\n{code}\n--- stderr ---\n{r.stderr[-2000:]}"


def test_guides_carry_no_internal_names():
    from _wordlist import banned
    bad = banned()
    for name in ("aadc-howto.md", "tracer-howto.md"):
        with open(os.path.join(GUIDES, name), encoding="utf-8") as fh:
            hit = bad.search(fh.read())
        assert not hit, f"{name}: {hit.group(0)}"
