"""The console script answers a person: --help, --version, --check, and a help message instead of silence when the bare
command is typed on a terminal. An MCP client never hands the server a terminal, so that case is unambiguous."""
from __future__ import annotations

import os
import pty
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _run(args, **kw):
    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "PYTHONPATH": ROOT})
    return subprocess.run([sys.executable, "-m", "aadc_mcp.server", *args], capture_output=True, text=True,
                          timeout=180, env=env, **kw)


def test_help_names_the_registration_command():
    r = _run(["--help"])
    assert r.returncode == 0, r.stderr
    assert "claude mcp add aadc --" in r.stdout and "mcpServers" in r.stdout and "--check" in r.stdout


def test_version_names_both_packages():
    from aadc_mcp import __version__
    r = _run(["--version"])
    assert r.returncode == 0, r.stderr
    assert f"aadc-mcp {__version__}" in r.stdout
    assert "aadc " in r.stdout


def test_check_prints_the_measured_summary():
    r = _run(["--check"])
    assert r.returncode == 0, r.stdout + r.stderr
    assert "AADC runs in" in r.stdout and "finding(s)" in r.stdout


def test_unknown_option_is_refused():
    r = _run(["--bogus"])
    assert r.returncode == 2 and "unknown option" in r.stderr


def test_bare_command_on_a_terminal_prints_help_and_exits():
    master, slave = pty.openpty()
    try:
        r = _run([], stdin=slave)
    finally:
        os.close(master)
        os.close(slave)
    assert r.returncode == 2, (r.returncode, r.stderr[-300:])
    assert "claude mcp add aadc --" in r.stderr
