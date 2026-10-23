"""Tapes: trace a script, keep the record, answer questions about it.

A tape is what the AADC engine records while a script runs. With the environment switch ``AADC_TRACE=1`` an
unmodified Python script that uses an AADC-built library (``aadc-quantlib-tracing``, or ``aadc`` types directly)
writes one on exit. ``Functions.trace_inspect()`` (aadc >= 2.25.2) then answers one plain-text question at a time:
``stats``, ``leaves``, ``branches`` (every decision with its signed margin), ``find``, ``origin``, ``uses``,
``cone``, ``at <file>:<line>`` (the source with the recorded values, hash-checked against the compiled file) and
``replay`` (re-evaluate at new inputs without re-running the model; withheld when a recorded decision flips).

Everything returned here is the engine's own text plus a few parsed fields. Nothing is estimated.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import threading
import time
import uuid

VERBS = ("stats", "source", "sites", "at", "find", "origin", "uses", "leaves", "branches", "replay", "cone")
AUTOTRACE = "[aadc-autotrace]"
TAPE_FILE = "aadc-trace.tape"
EXPLICIT_MARK = "mode=explicit"          # an example that records itself and writes the tape to AADC_TRACE_OUT

_FLIPPED = re.compile(r"^\s+FLIPPED\s+(#\d+)\s+(\w+)\s+(\S+)\s+margin (\S+) -> (\S+)\s+(\S+?):(\d+):(\d+) in (\S+)"
                      r"(?:\s+\(decided (\w+) -> (\w+)\))?")
_UNCHECKED = re.compile(r"^\s+UNCHECKED\s+(\S+)\s+(.*?)\s{2,}(\S+?):(\d+)\s*$")
_CROSSED = re.compile(r"^\s+CROSSED\s+(#\d+)\s+(\w+)\s+(\S+)\s+margin (\S+) -> (\S+)\s+(\S+?):(\d+):(\d+) in (\S+)(?:\s+\((.*)\))?")
_OUTROW = re.compile(r"^\s+(#\d+)\s+=\s+(\S+) -> (\S+)(?:\s+(RECORDED-PATH))?")
_STATROW = re.compile(r"^(entries|sites|inputs|outputs|frozen branches|recorded switches|dead entries)\s+(\S+)"
                      r"(?:\s+(attributed|files|hardcoded|constants)\s+(\S+))?")
_ATTRIB = re.compile(r"attributed\s+(\d+)\s+\((\d+)%\)")
_SEALED = re.compile(r"sealed: (\d+) active-to-passive SITE\(S\), (\d+) conversion\(s\)")
_OUTPUTS = re.compile(r"outputs: (\d+) \((\d+) named by AADC_TRACE_OUTPUTS, (\d+) switch function\(s\), (\d+) marked by the program\)")
_TAPE = re.compile(r"tape -> (\S+) \((\d+) bytes\)")


class TapeError(ValueError):
    """A request this server refuses, with the reason in the message."""


def header(text: str) -> dict:
    """The first line of every answer, ``# aadc-tape/2 verb=... key=value ...``, as a dict."""
    first = (text.splitlines() or [""])[0]
    out = {}
    for token in first.split()[1:]:
        if "=" in token:
            k, v = token.split("=", 1)
            out[k] = v
    return out


def _num(s):
    try:
        return float(s)
    except (TypeError, ValueError):
        return None


class TapeStore:
    """Tapes this server knows about, by id. Files live under ``$AADC_MCP_HOME/tapes`` (default ``~/.aadc-mcp``)."""

    def __init__(self, home: str | None = None):
        self.home = home or os.environ.get("AADC_MCP_HOME") or os.path.join(os.path.expanduser("~"), ".aadc-mcp")
        self.dir = os.path.join(self.home, "tapes")
        os.makedirs(self.dir, exist_ok=True)
        self._tapes: dict[str, dict] = {}
        self._fn: dict[str, object] = {}
        self._lock = threading.Lock()
        self.default_roots = self._env_roots()

    # ----------------------------------------------------------------------------------------- configuration
    @staticmethod
    def _env_roots():
        """``AADC_MCP_SOURCE_ROOTS="COMPILED=LOCAL;COMPILED=LOCAL"`` applied to every tape on load."""
        out = []
        for item in os.environ.get("AADC_MCP_SOURCE_ROOTS", "").split(";"):
            if "=" in item:
                a, b = item.split("=", 1)
                out.append((a.strip(), b.strip()))
        return out

    @staticmethod
    def _new_id(stem: str) -> str:
        stem = re.sub(r"[^A-Za-z0-9_-]+", "-", stem)[:40] or "tape"
        return f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"

    # ------------------------------------------------------------------------------------------------ tracing
    def trace_script(self, path: str, args=(), outputs=(), timeout_s: int = 120, workdir: str | None = None,
                     python: str | None = None, explicit: bool | None = None) -> dict:
        """Run ``python path args...`` with tracing on, in the script's own directory, and keep the tape it writes.

        ``explicit=True`` means the script records itself (``start_recording`` ... ``save_tape``) and only needs to
        know where to write: it gets ``AADC_TRACE_OUT`` and not ``AADC_TRACE``. ``None`` reads the script's first
        line for the marker ``mode=explicit``.
        """
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(path):
            raise TapeError(f"no such file: {path}")
        if not path.endswith(".py"):
            raise TapeError("trace_script runs a Python file (.py)")
        workdir = os.path.abspath(os.path.expanduser(workdir)) if workdir else os.path.dirname(path)
        if not os.path.isdir(workdir):
            raise TapeError(f"workdir is not a directory: {workdir}")
        if explicit is None:
            with open(path, encoding="utf-8", errors="replace") as fh:
                explicit = EXPLICIT_MARK in fh.readline()
        interpreter = python or sys.executable
        timeout_s = max(1, min(int(timeout_s), 3600))

        tape_id = self._new_id(os.path.splitext(os.path.basename(path))[0])
        dest = os.path.join(self.dir, tape_id + ".tape")
        env = dict(os.environ)
        env["AADC_TRACE_OUT"] = dest
        if not explicit:
            env["AADC_TRACE"] = "1"
        if outputs:
            env["AADC_TRACE_OUTPUTS"] = ",".join(str(o) for o in outputs)
        env.setdefault("OMP_NUM_THREADS", "1")
        env["PYTHONUNBUFFERED"] = "1"

        t0 = time.perf_counter()
        try:
            proc = subprocess.run([interpreter, path, *[str(a) for a in args]], cwd=workdir, env=env,
                                  capture_output=True, text=True, errors="replace", timeout=timeout_s)
        except subprocess.TimeoutExpired:
            raise TapeError(f"the script did not finish within {timeout_s} s; raise timeout_s or shorten the run") from None
        except OSError as exc:
            raise TapeError(f"could not start {interpreter}: {exc}") from None
        wall = time.perf_counter() - t0

        auto = [l for l in proc.stderr.splitlines() if l.startswith(AUTOTRACE)]
        other = [l for l in proc.stderr.splitlines() if not l.startswith(AUTOTRACE)]
        result = {
            "script": path, "workdir": workdir, "interpreter": interpreter, "mode": "explicit" if explicit else "auto",
            "exit_code": proc.returncode, "wall_s": round(wall, 3),
            "stdout": proc.stdout[-6000:],
            "stderr": "\n".join(l for l in other if "Community Edition" not in l)[-4000:],
            "autotrace": self._census(auto),
        }
        # the engine honours AADC_TRACE_OUT; an older engine, or an explicit script that ignores it, writes to cwd
        fallback = os.path.join(workdir, TAPE_FILE)
        if not os.path.exists(dest) and os.path.exists(fallback) and os.path.getmtime(fallback) >= t0 - 1:
            shutil.move(fallback, dest)
        if not os.path.exists(dest):
            result["tape_id"] = None
            result["why_no_tape"] = self._why_no_tape(proc, auto, explicit)
            return result

        record = {"id": tape_id, "path": dest, "bytes": os.path.getsize(dest), "script": path, "args": list(args),
                  "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "source_roots": list(self.default_roots)}
        with self._lock:
            self._tapes[tape_id] = record
        result.update({"tape_id": tape_id, "tape_path": dest, "tape_bytes": record["bytes"]})
        try:
            result["stats"] = self.stats(tape_id)
        except Exception as exc:  # noqa: BLE001 - the tape exists; say what the engine said
            result["stats_error"] = f"{type(exc).__name__}: {exc}"
        return result

    @staticmethod
    def _census(lines):
        out = {"lines": lines[:80]}
        for line in lines:
            m = _SEALED.search(line)
            if m:
                out["frozen_sites"], out["frozen_conversions"] = int(m.group(1)), int(m.group(2))
            m = _OUTPUTS.search(line)
            if m:
                out["outputs"] = {"total": int(m.group(1)), "named": int(m.group(2)), "switch_functions": int(m.group(3)),
                                  "marked_by_program": int(m.group(4))}
            m = _TAPE.search(line)
            if m:
                out["tape_bytes"] = int(m.group(2))
            if "WARNING" in line and "INSTRUMENT" in line:
                out["caveat"] = line.split(AUTOTRACE, 1)[1].strip()
        return out

    @staticmethod
    def _why_no_tape(proc, auto, explicit):
        text = proc.stderr
        if "running UNTRACED" in text:
            return "the engine refused the AADC_TRACE value and ran untraced"
        if "ModuleNotFoundError" in text and ("aadc" in text or "QuantLib" in text):
            return ("the interpreter that ran the script cannot import the AADC packages; pass python=<interpreter of "
                    "the environment where aadc and aadc-quantlib-tracing are installed>")
        if proc.returncode != 0:
            return f"the script exited with code {proc.returncode} before a tape was written (see stderr)"
        if explicit:
            return ("the script is marked mode=explicit but wrote no tape: it must end with "
                    "open(os.environ.get('AADC_TRACE_OUT', 'aadc-trace.tape'), 'wb').write(f.save_tape())")
        if not auto:
            return ("nothing was recorded: the script never touched an AADC value. It must use aadc types or an "
                    "AADC-built library (from aadc_quantlib_tracing import QuantLib as ql); PyPI QuantLib is never traced")
        return "the engine reported tracing but no tape file appeared; see autotrace.lines"

    # ----------------------------------------------------------------------------------------------- loading
    def load_tape(self, path: str) -> dict:
        """Register an existing .tape file (for example one downloaded from a report) without moving it."""
        path = os.path.abspath(os.path.expanduser(path))
        if not os.path.isfile(path):
            raise TapeError(f"no such file: {path}")
        tape_id = self._new_id(os.path.splitext(os.path.basename(path))[0])
        record = {"id": tape_id, "path": path, "bytes": os.path.getsize(path), "script": None, "args": [],
                  "created": time.strftime("%Y-%m-%dT%H:%M:%S"), "source_roots": list(self.default_roots)}
        with self._lock:
            self._tapes[tape_id] = record
        stats = self.stats(tape_id)     # raises if the file is not a tape
        return {"tape_id": tape_id, "tape_path": path, "tape_bytes": record["bytes"], "stats": stats}

    def _record(self, tape_id: str) -> dict:
        try:
            return self._tapes[tape_id]
        except KeyError:
            raise TapeError(f"unknown tape_id {tape_id!r}; list_tapes shows the ids this server holds") from None

    def functions(self, tape_id: str):
        """The engine object holding this tape, loaded once and kept; remembered source roots re-applied."""
        record = self._record(tape_id)
        with self._lock:
            f = self._fn.get(tape_id)
        if f is None:
            import aadc
            f = aadc.Functions()
            with open(record["path"], "rb") as fh:
                f.load_tape(fh.read())
            for compiled, local in record["source_roots"]:
                f.trace_inspect(f"source root={compiled}={local}")
            with self._lock:
                self._fn[tape_id] = f
        return f

    def list(self) -> list[dict]:
        with self._lock:
            return [dict(r) for r in self._tapes.values()]

    # --------------------------------------------------------------------------------------------- questions
    def inspect(self, tape_id: str, request: str, max_lines: int = 40) -> dict:
        request = (request or "").strip()
        verb = request.split(" ", 1)[0] if request else ""
        if verb not in VERBS:
            raise TapeError(f"the request must start with one of {', '.join(VERBS)}; got {request!r}")
        max_lines = max(0, min(int(max_lines), 400))
        f = self.functions(tape_id)
        text = f.trace_inspect(request, max_lines=max_lines)
        h = header(text)
        if verb == "source" and h.get("status") == "ok" and "root=" in request:
            for token in request.split()[1:]:
                if token.startswith("root=") and token.count("=") >= 2:
                    _, compiled, local = token.split("=", 2)
                    self._record(tape_id)["source_roots"].append((compiled, local))
        return {"tape_id": tape_id, "request": request, "header": h, "text": text}

    def set_source_root(self, tape_id: str, compiled_prefix: str, local_dir: str) -> dict:
        local_dir = os.path.abspath(os.path.expanduser(local_dir))
        if not os.path.isdir(local_dir):
            raise TapeError(f"local_dir is not a directory: {local_dir}")
        if not compiled_prefix or " " in compiled_prefix or " " in local_dir:
            raise TapeError("paths with spaces cannot be passed to the engine's source root grammar")
        return self.inspect(tape_id, f"source root={compiled_prefix}={local_dir}", max_lines=20)

    def stats(self, tape_id: str) -> dict:
        text = self.functions(tape_id).trace_inspect("stats", max_lines=0)
        out = {"raw": text, "status": header(text).get("status")}
        for line in text.splitlines():
            m = _STATROW.match(line)
            if m:
                out[m.group(1).replace(" ", "_")] = m.group(2)
                if m.group(3):
                    out[m.group(3)] = m.group(4)
            m = _ATTRIB.search(line)
            if m:
                out["attributed_entries"], out["attributed_pct"] = int(m.group(1)), int(m.group(2))
        if out.get("attributed_pct") == 0:
            out["warning"] = ("0% attributed: nothing in this tape points at source. An uninstrumented build or "
                              "tracing off, never evidence that the code has nothing to say.")
        return out

    def replay(self, tape_id: str, assignments: str, out: str, path_recorded: bool = False) -> dict:
        """``replay set=<assignments> out=<out>``, with the verdict parsed: survives / flipped / unchecked / crossed."""
        assignments = (assignments or "").replace(" ", "")
        out = (out or "").strip()
        if not out.startswith("#"):
            raise TapeError("out must be a tape id such as #384 (take it from find or leaves; a bare number is a value)")
        if not assignments or any("=" not in item for item in assignments.split(",")):
            raise TapeError("assignments must read like '#12=101' or '#12=101,#15=0.21' (ids from leaves)")
        request = f"replay set={assignments} out={out}" + (" path=recorded" if path_recorded else "")
        text = self.functions(tape_id).trace_inspect(request, max_lines=0)
        h = header(text)
        value = recorded = None
        flipped, unchecked, crossed = [], [], []
        for line in text.splitlines():
            m = _OUTROW.match(line)
            if m and m.group(1) == out:
                v = _num(m.group(3))
                if m.group(4):
                    recorded = v
                elif v is not None:
                    value = v
                continue
            m = _FLIPPED.match(line)
            if m:
                flipped.append({"entry": m.group(1), "kind": m.group(2), "op": m.group(3),
                                "margin_from": _num(m.group(4)), "margin_to": _num(m.group(5)),
                                "file": m.group(6), "line": int(m.group(7)), "col": int(m.group(8)), "fn": m.group(9),
                                "decided_from": m.group(10), "decided_to": m.group(11)})
                continue
            m = _UNCHECKED.match(line)
            if m:
                unchecked.append({"entry": m.group(1), "why": m.group(2).strip(), "file": m.group(3), "line": int(m.group(4))})
                continue
            m = _CROSSED.match(line)
            if m:
                crossed.append({"entry": m.group(1), "kind": m.group(2), "op": m.group(3),
                                "margin_from": _num(m.group(4)), "margin_to": _num(m.group(5)),
                                "file": m.group(6), "line": int(m.group(7)), "col": int(m.group(8)), "fn": m.group(9),
                                "note": (m.group(10) or "").strip()})
        survives = h.get("status") == "ok" and h.get("flips") == "0" and not unchecked and value is not None
        du = re.search(r"downstream-unknown=(\d+)", text)
        dp = re.search(r"downstream-passive=(\d+)", text)
        verdict = ("SURVIVES: the recorded path holds at these inputs; value is exact" if survives else
                   "WITHHELD: a recorded decision flips or cannot be checked at these inputs; there is no value to quote"
                   if value is None or flipped or unchecked else
                   "SUSPECT: a value is shown but the verdict is not clean; read the text")
        return {"tape_id": tape_id, "request": request, "status": h.get("status"), "flips": int(h.get("flips", "0") or 0),
                "crossings": int(h.get("crossings", "0") or 0), "survives": survives, "verdict": verdict,
                "value": value if survives else None, "value_if_path_recorded": recorded,
                "flipped": flipped, "unchecked": unchecked, "crossed": crossed,
                "downstream_unknown": int(du.group(1)) if du else 0, "downstream_passive": int(dp.group(1)) if dp else 0,
                "text": text}
