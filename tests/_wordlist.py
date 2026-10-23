"""The banned-pattern list the stealth gates share: tests/wordlists/public.txt plus, where present, private.txt."""
from __future__ import annotations

import os
import re

WORDLISTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "wordlists")


def banned() -> re.Pattern:
    patterns = []
    for name in ("public.txt", "private.txt"):
        path = os.path.join(WORDLISTS, name)
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                patterns += [line.strip() for line in fh if line.strip() and not line.startswith("#")]
    assert patterns, "no word list found"
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE)
