"""aadc-mcp: a local MCP server for AADC and the AADC Tracer.

It runs on the developer's own machine over stdio, inside the Python environment where ``aadc`` (and, on Linux
x86-64 or macOS arm64, ``aadc-quantlib-tracing``) are installed. It runs the developer's own scripts with tracing on and answers
questions about the records they leave. Every number and every file:line in an answer is the engine's own output;
the client's model narrates, it never computes.
"""
from __future__ import annotations

import json
import os
import sys

from . import __version__

GUIDES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guides")
EXAMPLES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "examples")


def _protect_stdout():
    """stdio MCP owns file descriptor 1. The engine prints its edition banner to fd 1 on import, so route fd 1 to
    stderr for the whole process and hand the protocol a private copy of the original stdout."""
    proto = os.dup(1)
    os.dup2(2, 1)
    sys.stdout = os.fdopen(proto, "w", buffering=1, encoding="utf-8")


from mcp.server.mcpserver import MCPServer  # noqa: E402  (mcp >= 2)

INSTRUCTIONS = """MatLogica's AADC engine and the AADC Tracer on this machine, through the engine's own calls.

Start with check_environment. Then either run_example (bundled scripts) or trace_script on the user's own .py file:
both return a tape_id. Question the tape with inspect_tape (verbs: stats, leaves, branches, sites, at, find, origin,
uses, cone) and replay.

Before writing code, read the how-to that matches the task: aadc://guide/aadc-howto (record once, replay, exact
derivatives, batch evaluation, QuantLib sensitivities) or aadc://guide/tracer-howto (the two ways to record, the
switches, the questions in order, when a replay is exact). Every snippet in them runs as written.
aadc://guide/release-notes is the installed engine's own change log.

Rules that keep answers true:
- Ids are written #N and come from answers (find, leaves, branches). A bare number is always a VALUE, never an id.
- Read stats first. attributed_pct 0 means an uninstrumented build or tracing off, not a library with nothing to say.
- replay with survives=false is WITHHELD: it carries no value. Say which decision flipped (file:line) and stop; never
  estimate the number.
- Keep the coordinates. A finding without its file:line is a guess; with it the reader can check in ten seconds.
- A tape is one execution at one input point. It supports "this executed" and "this constant is declared at
  file:line"; it never supports "this is the only path" or "the code has no other branches".
- trace_script runs the user's own code on the user's own machine with tracing on; it is not a sandbox.
"""

mcp = MCPServer("aadc", title="MatLogica AADC and Tracer (local)", instructions=INSTRUCTIONS, version=__version__)
_store = None


def store():
    global _store
    if _store is None:
        from .tapes import TapeStore
        _store = TapeStore()
    return _store


def _refuse(exc) -> dict:
    return {"error": str(exc)}


# ------------------------------------------------------------------------------------------------------ tools
@mcp.tool()
def check_environment() -> dict:
    """What this interpreter can do with AADC and the Tracer, measured: installed packages and versions, platform,
    licence state, an engine self-test (record, replay, reverse: dz/dx = 6 at x = 3), a tracing self-test (one traced
    QuantLib call must attribute leaves to QuantLib's C++), and findings with the pip command that fixes each.
    Call it first; call it again after installing anything."""
    from .env import check_environment as _check
    return _check()


@mcp.tool()
def trace_script(path: str, args: list[str] | None = None, outputs: list[str] | None = None, timeout_s: int = 120,
                 workdir: str | None = None, python: str | None = None) -> dict:
    """Run a Python script with tracing on and keep the record (tape) it leaves. The script needs no changes: it runs
    in its own directory with AADC_TRACE=1, so every calculation through aadc types or an AADC-built library such as
    aadc-quantlib-tracing is recorded with its source coordinates. Returns tape_id, the script's stdout and stderr,
    the engine's census (frozen branch sites, outputs) and stats. A script that records itself and ends with
    f.save_tape() writes to AADC_TRACE_OUT; mark its first line with 'mode=explicit'.
    outputs: optional AADC_TRACE_OUTPUTS entries, e.g. ['value=123.45'] or ['pricer.py:42'], to name the program's
    results on the tape. python: another interpreter to run under (the one where the user's packages live).
    This runs the user's own code on the user's own machine; it is not a sandbox."""
    try:
        return store().trace_script(path, args or [], outputs or [], timeout_s=timeout_s, workdir=workdir, python=python)
    except Exception as exc:  # noqa: BLE001 - every refusal is an answer
        return _refuse(exc)


@mcp.tool()
def inspect_tape(tape_id: str, request: str, max_lines: int = 40) -> dict:
    """Ask the tape one question in the engine's own grammar and get its text answer plus the parsed header.
    Verbs: 'stats' | 'leaves [kind=input|constant] [by=leaf] [limit=N]' | 'branches order=margin [limit=N]' |
    'sites [file=NAME] [limit=N]' | 'at FILE:LINE [context=N]' (source with the recorded values; hash=ok means the
    file shown is the one compiled) | 'find value=X' (where a printed number was computed) | 'origin #N' (the formula
    behind a value) | 'uses #N' | 'cone #N' (which leaves can move a value, by derivative or only by a branch) |
    'source root=COMPILED=LOCAL' (map compiled paths to a local source tree) | 'replay ...' (prefer the replay tool).
    Ids are #N from earlier answers. A malformed request answers status=error in the header, never an exception."""
    try:
        return store().inspect(tape_id, request, max_lines=max_lines)
    except Exception as exc:  # noqa: BLE001
        return _refuse(exc)


@mcp.tool()
def replay(tape_id: str, assignments: str, out: str, path_recorded: bool = False) -> dict:
    """Re-evaluate the tape at new inputs without re-running the model. assignments: '#12=101' or '#12=101,#15=0.21'
    (leaf ids from 'leaves kind=input' or 'leaves by=leaf'); out: the output id from 'find value=<printed price>'.
    survives=true: the recorded path holds and value is exact (equal to a fresh run to the last digit).
    survives=false: WITHHELD; flipped names the decision (file:line, decided true -> false) and unchecked the
    conversions the tape cannot check. There is no value to quote in that case. A tape read back from a file keeps
    no operand for a counted conversion, so on most QuantLib tapes a replay is withheld with unchecked naming the
    line (often errorfunction.cpp:200); say so and re-run the script at the new inputs for the price.
    path_recorded=true returns the recorded path's value labelled as such, for comparison only."""
    try:
        return store().replay(tape_id, assignments, out, path_recorded=path_recorded)
    except Exception as exc:  # noqa: BLE001
        return _refuse(exc)


@mcp.tool()
def set_source_root(tape_id: str, compiled_prefix: str, local_dir: str) -> dict:
    """Map the compiled source prefix recorded on the tape (for aadc-quantlib-tracing 1.41 it is
    /project/work/QLAADC/ql) to a local directory holding that source, so 'at FILE:LINE' and 'origin' can show the
    code. Later answers say hash=ok when the local file is the one the library was compiled from and hash=MISMATCH
    when it is not; a mismatch is reported, never silent. Remembered for this tape."""
    try:
        return store().set_source_root(tape_id, compiled_prefix, local_dir)
    except Exception as exc:  # noqa: BLE001
        return _refuse(exc)


@mcp.tool()
def load_tape(path: str) -> dict:
    """Register an existing .tape file written earlier (by trace_script, by a script's own save_tape(), or downloaded
    from a report) and return its tape_id and stats."""
    try:
        return store().load_tape(path)
    except Exception as exc:  # noqa: BLE001
        return _refuse(exc)


@mcp.tool()
def list_tapes() -> dict:
    """The tapes this server holds: id, file, size, the script that produced each, and the source roots applied."""
    return {"tapes": store().list(), "home": store().home}


def _examples() -> list[dict]:
    out = []
    for name in sorted(os.listdir(EXAMPLES_DIR)):
        if not name.endswith(".py"):
            continue
        with open(os.path.join(EXAMPLES_DIR, name), encoding="utf-8") as fh:
            first = fh.readline().strip()
            second = fh.readline().strip().strip('"').strip()
        meta = {}
        for token in first.replace("# aadc-mcp:", "").split():
            if "=" in token:
                k, v = token.split("=", 1)
                meta[k] = v
        out.append({"name": name[:-3], "mode": meta.get("mode", "auto"), "needs": meta.get("needs", "aadc"),
                    "platforms": meta.get("platforms", "all"), "summary": second})
    return out


@mcp.tool()
def list_examples() -> dict:
    """Bundled scripts to start from: plain AADC (any platform), and unmodified QuantLib pricers that
    aadc-quantlib-tracing records (Linux x86-64, macOS arm64). mode=auto scripts are traced as they are; mode=explicit scripts
    record themselves and print sensitivities. Each is a starting point to copy and edit."""
    return {"examples": _examples(), "run": "run_example(name) traces one and returns its tape_id",
            "source": "get_example(name) returns the script text"}


@mcp.tool()
def get_example(name: str) -> dict:
    """The source of one bundled example, to read, copy or adapt."""
    path = os.path.join(EXAMPLES_DIR, os.path.basename(name) + ".py")
    if not os.path.isfile(path):
        return _refuse(f"no example named {name!r}; list_examples shows the names")
    with open(path, encoding="utf-8") as fh:
        return {"name": name, "path": path, "source": fh.read()}


@mcp.tool()
def run_example(name: str, timeout_s: int = 180) -> dict:
    """Copy one bundled example into the server's working folder, run it with tracing on and return its tape_id,
    its printed output and the tape's stats. Then question the tape with inspect_tape and replay."""
    src = os.path.join(EXAMPLES_DIR, os.path.basename(name) + ".py")
    if not os.path.isfile(src):
        return _refuse(f"no example named {name!r}; list_examples shows the names")
    workdir = os.path.join(store().home, "examples")
    os.makedirs(workdir, exist_ok=True)
    dst = os.path.join(workdir, os.path.basename(src))
    with open(src, encoding="utf-8") as fh, open(dst, "w", encoding="utf-8") as out:
        out.write(fh.read())
    try:
        return store().trace_script(dst, timeout_s=timeout_s, workdir=workdir)
    except Exception as exc:  # noqa: BLE001
        return _refuse(exc)


# -------------------------------------------------------------------------------------------------- resources
def _guide(name: str) -> str:
    path = os.path.join(GUIDES_DIR, name)
    with open(path, encoding="utf-8") as fh:
        return fh.read()


@mcp.resource("aadc://guide/agent", name="aadc-agent-guide", title="AADC for Python: the agent guide shipped in the wheel",
              description="aadc.llms_txt() from the installed wheel, so it describes the version actually imported.",
              mime_type="text/markdown")
def guide_agent() -> str:
    try:
        import aadc
        return aadc.llms_txt()
    except Exception as exc:  # noqa: BLE001
        return f"# aadc is not importable here\n\n{type(exc).__name__}: {exc}\n\nInstall: pip install \"aadc>=2.25.2\"\n"


@mcp.resource("aadc://guide/get-started", name="get-started", title="Get started: install, register, first three calls",
              mime_type="text/markdown")
def guide_get_started() -> str:
    return _guide("get-started.md")


@mcp.resource("aadc://guide/inspect-verbs", name="inspect-verbs", title="The tape-inspection verbs, with measured examples",
              mime_type="text/markdown")
def guide_verbs() -> str:
    return _guide("inspect-verbs.md")


@mcp.resource("aadc://guide/versions", name="versions", title="Packages, platforms and pins",
              mime_type="text/markdown")
def guide_versions() -> str:
    return _guide("versions.md")


@mcp.resource("aadc://guide/tracing-for-agents", name="tracing-for-agents",
              title="What tracing is good for, for agents: the calls, the recipes, what you may not claim",
              mime_type="text/markdown")
def guide_for_agents() -> str:
    return _guide("tracing-for-agents.md")


@mcp.resource("aadc://guide/tracing-for-humans", name="tracing-for-humans",
              title="Five things a traced tape gives you that reading the source cannot", mime_type="text/markdown")
def guide_for_humans() -> str:
    return _guide("tracing-for-humans.md")


@mcp.resource("aadc://guide/model-validation", name="model-validation",
              title="Model documentation and validation from a traced tape; the agent loops", mime_type="text/markdown")
def guide_model_validation() -> str:
    return _guide("model-validation.md")


@mcp.resource("aadc://guide/how-it-works", name="how-it-works",
              title="How source tracing works: the plugin, the four gates, the limits", mime_type="text/markdown")
def guide_how_it_works() -> str:
    return _guide("how-it-works.md")


@mcp.resource("aadc://guide/aadc-howto", name="aadc-howto",
              title="Using AADC from an agent: record once, replay, exact derivatives, batch, QuantLib sensitivities",
              description="Six runnable snippets with the rules that keep the numbers right; the package's tests execute them.",
              mime_type="text/markdown")
def guide_aadc_howto() -> str:
    return _guide("aadc-howto.md")


@mcp.resource("aadc://guide/tracer-howto", name="tracer-howto",
              title="Using the Tracer from an agent: two ways to record, the switches, the questions in order",
              description="When a replay is exact and when it is withheld; what to ask first; runnable snippets.",
              mime_type="text/markdown")
def guide_tracer_howto() -> str:
    return _guide("tracer-howto.md")


@mcp.resource("aadc://guide/release-notes", name="release-notes",
              title="Release notes of the installed aadc engine",
              description="aadc.release_notes() from the installed wheel: what changed, version by version.",
              mime_type="text/markdown")
def guide_release_notes() -> str:
    try:
        import aadc
        return aadc.release_notes()
    except Exception as exc:  # noqa: BLE001
        return f"# aadc is not importable here\n\n{type(exc).__name__}: {exc}\n"


# ---------------------------------------------------------------------------------------------------- prompts
@mcp.prompt(name="get_started", title="Get started with AADC and the Tracer here")
def prompt_get_started() -> str:
    return ("Check this machine with check_environment and tell me, in plain words, what runs here and what does not. "
            "If tracing is ready, run_example('european_option'), read its stats, then show me the three decisions "
            "closest to flipping (inspect_tape 'branches order=margin limit=3') with their file:line. If tracing is not "
            "available on this platform, run_example('hello_aadc') and explain what the derivatives show. Quote numbers "
            "and coordinates exactly as returned.")


@mcp.prompt(name="validate_pricer", title="Validate a pricing script from its record")
def prompt_validate_pricer(script_path: str) -> str:
    return (f"Trace {script_path} with trace_script. Then: (1) read stats and stop if attributed_pct is 0; "
            f"(2) list the constants the price depends on that the script never passed in (inspect_tape 'leaves "
            f"kind=constant limit=40'), grouped by file; (3) list every frozen decision with its margin (inspect_tape "
            f"'branches order=margin limit=20'); (4) for the output found with 'find value=<the printed price>', try a "
            f"replay that moves one input by 1% and report whether it SURVIVES or is WITHHELD and why; (5) write up the "
            f"findings keeping file:line on every claim, and state what one execution cannot tell us.")


@mcp.prompt(name="add_sensitivities", title="Give a pricing script exact sensitivities with AADC")
def prompt_add_sensitivities(script_path: str) -> str:
    return (f"Read aadc://guide/aadc-howto, then make a copy of {script_path} that records itself once with AADC: wrap the "
            f"pricing in aadc.Functions().start_recording(trace=True, trace_inputs_as_random=False) ... stop_recording(); "
            f"turn each market input the user may want to move into aadc.idouble and mark it with mark_as_input(); mark "
            f"the price with mark_as_output(); after stop_recording, set every input, forward, seed the output, reverse, "
            f"and print the price and each sensitivity with repr(); print f.num_passive_warnings(); end with "
            f"f.save_tape() written to AADC_TRACE_OUT (first line of the file: '# aadc-mcp: mode=explicit'). Run it with "
            f"trace_script and report the numbers exactly as printed. If the passive-warning count is not zero, list "
            f"the frozen decisions with inspect_tape 'branches order=margin limit=20' and explain each before trusting "
            f"any derivative. Do not change the pricing itself.")


def _usage() -> str:
    me = os.path.abspath(sys.argv[0]) if sys.argv and sys.argv[0] else "aadc-mcp"
    return f"""aadc-mcp {__version__}: a local MCP server for MatLogica's AADC engine and the AADC Tracer.

It is not run by hand. Register it once with your coding agent, which starts it and talks to it over stdio:

  claude mcp add aadc -- {me}
  {{ "mcpServers": {{ "aadc": {{ "command": "{me}" }} }} }}

Then ask the agent: check the AADC environment; run the european_option example; show the three decisions closest to
flipping, with file and line.

Options:
  --check     measure what runs here (packages, platform, engine self-test, tracing self-test) and print the findings
  --version   print the version of aadc-mcp and of the installed aadc engine
  --help      this message
"""


def _print_check() -> int:
    from .env import check_environment as _check
    report = _check()
    print(report["summary"])
    print(f"python {report['python']} at {report['executable']}; platform {report['platform']}")
    for name, version in report["packages"].items():
        if version:
            print(f"  {name} {version}")
    for finding in report["findings"]:
        print(f"  {finding['level']}: {finding['what']}")
        print(f"      fix: {finding['fix']}")
    return 0 if report["ready"] else 1


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(_usage())
        return 0
    if args and args[0] == "--version":
        print(f"aadc-mcp {__version__}")
        try:
            import aadc
            print(f"aadc {getattr(aadc, '__version__', '?')} ({aadc.version()})")
        except Exception as exc:  # noqa: BLE001
            print(f"aadc not importable here: {type(exc).__name__}: {exc}")
        return 0
    if args and args[0] == "--check":
        return _print_check()
    if args:
        print(f"aadc-mcp: unknown option {args[0]}", file=sys.stderr)
        print(_usage(), file=sys.stderr)
        return 2
    if sys.stdin.isatty():
        # a person typed the bare command: an MCP client never hands the server a terminal
        print(_usage(), file=sys.stderr)
        return 2
    _protect_stdout()
    mcp.run("stdio")
    return 0


if __name__ == "__main__":
    sys.exit(main())
