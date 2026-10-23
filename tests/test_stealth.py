"""Nothing in the shipped package, its README or its metadata may name private hosts, paths, people or tooling.
The patterns live in tests/wordlists (public.txt everywhere; private.txt only in the private repository)."""
import os
import re

from _wordlist import banned

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHIPPED = [os.path.join(ROOT, "aadc_mcp"), os.path.join(ROOT, "README.md"), os.path.join(ROOT, "pyproject.toml"),
           os.path.join(ROOT, "LICENSE"), os.path.join(ROOT, "CHANGELOG.md"), os.path.join(ROOT, "server.json")]
BANNED = banned()
# client names are allowed only where the developer is told how to register the server: the get-started guide, the
# README, and the console script's --help text
ALLOW_CLIENT_NAMES = {"get-started.md", "README.md", "server.py"}
CLIENTS = re.compile(r"Claude|Codex|ChatGPT", re.IGNORECASE)


def _files():
    for base in SHIPPED:
        if os.path.isfile(base):
            yield base
            continue
        if not os.path.isdir(base):
            continue
        for d, _, fs in os.walk(base):
            if "__pycache__" in d:
                continue
            for f in fs:
                yield os.path.join(d, f)


def test_no_internal_names():
    hits = []
    for path in _files():
        with open(path, encoding="utf-8", errors="replace") as fh:
            for n, line in enumerate(fh, 1):
                m = BANNED.search(line)
                if m and not (os.path.basename(path) in ALLOW_CLIENT_NAMES and CLIENTS.fullmatch(m.group(0))):
                    hits.append(f"{os.path.relpath(path, ROOT)}:{n}: {m.group(0)!r}: {line.strip()[:90]}")
    assert not hits, "\n".join(hits)


def test_self_test_fixture_fires():
    assert BANNED.search("registry at 192.168.1.250:3030")
    assert BANNED.search("see /home/someone/file")
    assert BANNED.search("C:/Users/someone or /Users/someone")
    assert not BANNED.search("pip install aadc-mcp")
