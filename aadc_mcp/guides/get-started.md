# Get started: AADC and the Tracer from your coding agent

`aadc-mcp` is a small local MCP server. It runs on your machine, inside the Python environment where the
AADC packages are installed, and gives your coding agent three things it cannot get by reading documentation:

1. **a measured environment check** (which packages, which platform, does the engine run, does tracing attribute);
2. **a way to trace your own script** with no code changes, and keep the record (the tape);
3. **the questions the tape answers**: which constants the price depends on that nobody passed in, which decisions
   were frozen and how close each was to going the other way, where a printed number was computed, the source line
   with the recorded values written in, and a replay at new inputs that is either exact or withheld.

Every number and every `file:line` in an answer is the engine's own output. The agent narrates; it never computes.

## Install

```sh
python3 -m venv aadc-env && . aadc-env/bin/activate
pip install "aadc-mcp[quantlib]"        # aadc-mcp + aadc + QuantLib 1.41 with source tracing (Linux x86-64, macOS arm64)
pip install aadc-mcp                     # Windows, Linux arm64: aadc-mcp + aadc; tracing of QuantLib needs Linux x86-64 or macOS arm64
pip install "aadc-mcp[greeks]"           # adds aadc-quantlib: QuantLib 1.38 with exact AAD sensitivities, every platform
```

Run `aadc-mcp --check` first: it prints what runs here and the pip command for anything missing. Intel Macs are not
supported, because the engine has no wheel for them.

The server runs under the interpreter it was installed into; your scripts run under the same one unless you pass
`python=` to `trace_script`.

## Register the server

Claude Code:

```sh
claude mcp add aadc -- aadc-env/bin/aadc-mcp
```

Cursor, Windsurf, Claude Desktop and other clients that read a JSON configuration:

```json
{ "mcpServers": { "aadc": { "command": "/absolute/path/to/aadc-env/bin/aadc-mcp" } } }
```

Codex CLI: `codex mcp add aadc -- /absolute/path/to/aadc-env/bin/aadc-mcp`.

Use the absolute path of the console script inside the environment, so the right interpreter and packages are
found whatever the client's working directory is.

## The first three calls

```
check_environment()                      -> what runs here, with the pip command for anything missing
run_example("european_option")           -> a tape_id for an unmodified QuantLib script
inspect_tape(tape_id, "branches order=margin limit=5")
```

Then on your own code:

```
trace_script("/path/to/my_pricer.py")                       -> tape_id, stdout, stats
inspect_tape(tape_id, "leaves kind=constant limit=40")      -> the constants the price depends on, by file:line
inspect_tape(tape_id, "find value=<the printed price>")     -> where it was computed; the OUTPUT id
replay(tape_id, "#<input id>=<new value>", "#<output id>")  -> exact value, or WITHHELD with the decision that flips
```

Ids are written `#N` and come from answers. A bare number is always a value.

## Settings

| environment variable | meaning |
|---|---|
| `AADC_MCP_HOME` | where tapes and example copies are kept (default `~/.aadc-mcp`) |
| `AADC_MCP_SOURCE_ROOTS` | `COMPILED=LOCAL;COMPILED=LOCAL`, applied to every tape so `at` can show source |
| `OMP_NUM_THREADS` | passed through to traced scripts; the server sets 1 when unset |

## Reading the source behind a line

The tape records where each operation was compiled (for `aadc-quantlib-tracing` 1.41 the prefix is
`/project/work/QLAADC/ql`). Point `set_source_root` at a local QuantLib 1.41 `ql/` directory and `at FILE:LINE`
shows the code with the recorded values. Each answer says `hash=ok` when the local file is the one the library was
compiled from, and `hash=MISMATCH` when it is not. A mismatch is reported, never silent.
