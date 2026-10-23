# aadc-mcp

<!-- mcp-name: com.matlogica/aadc-mcp -->

**MatLogica's AADC engine and AADC Tracer, from your coding agent, on your own machine.**

`aadc-mcp` is a local [MCP](https://modelcontextprotocol.io) server. It runs over stdio inside the Python
environment where the AADC packages are installed, and gives an agent in Claude Code, Cursor, Codex or any other MCP
client three things:

- **a measured environment check**: which packages and versions are here, whether the engine runs (it records,
  replays and differentiates a two-line function and checks the answer), whether QuantLib tracing attributes anything,
  and the pip command for whatever is missing;
- **tracing of your own script with no code changes**: the script runs with recording on and leaves a tape; a
  QuantLib pricer written against `aadc-quantlib-tracing` needs nothing added;
- **the questions a tape answers**: the constants the price depends on that nobody passed in, each at its C++ line;
  every decision frozen at record time and how far it was from going the other way; where a printed number was
  computed and the formula behind it; the source line with the recorded values written in, hash-checked against the
  compiled file; and a replay at new inputs that is exact when every recorded decision can be re-checked, and
  otherwise withheld, naming the decision it cannot vouch for.

Every number and every `file:line` in an answer is the engine's own output. The agent narrates; it never computes.

## Install

```sh
python3 -m venv aadc-env && . aadc-env/bin/activate
pip install "aadc-mcp[quantlib]"      # Linux x86-64, macOS arm64: aadc + QuantLib 1.41 with source tracing
pip install aadc-mcp                   # elsewhere: aadc only (tracing of QuantLib needs Linux x86-64 or macOS arm64)
pip install "aadc-mcp[greeks]"         # adds aadc-quantlib: QuantLib 1.38 with exact AAD sensitivities, every platform
```

`aadc-mcp --check` prints what runs here, and the pip command for anything missing, before you register anything.

Register it with the absolute path of the console script, so the client always finds the right interpreter:

```sh
claude mcp add aadc -- /absolute/path/to/aadc-env/bin/aadc-mcp
```

```json
{ "mcpServers": { "aadc": { "command": "/absolute/path/to/aadc-env/bin/aadc-mcp" } } }
```

## First three calls

```
check_environment()
run_example("european_option")                               -> tape_id
inspect_tape(tape_id, "branches order=margin limit=5")       -> the decisions closest to flipping, with file:line
```

Then on your own code: `trace_script("/path/to/my_pricer.py")`, `inspect_tape(tape_id, "leaves kind=constant")`,
`inspect_tape(tape_id, "find value=<the printed price>")`, `replay(tape_id, "#<input>=<value>", "#<output>")`.

## Tools

| tool | what it does |
|---|---|
| `check_environment` | packages, platform, licence state, engine self-test, tracing self-test, findings with fixes |
| `trace_script` | run a `.py` file with tracing on, keep the tape, return stdout, census and stats |
| `inspect_tape` | one question in the engine's grammar: `stats`, `leaves`, `branches`, `sites`, `at`, `find`, `origin`, `uses`, `cone`, `source` |
| `replay` | re-evaluate the tape at new inputs; exact when every recorded decision re-checks, withheld when one flips or cannot be checked |
| `set_source_root` | map the compiled source prefix to a local tree so `at` shows code, with `hash=ok` or `hash=MISMATCH` |
| `load_tape`, `list_tapes` | register a tape written elsewhere; list what the server holds |
| `list_examples`, `get_example`, `run_example` | six bundled scripts: plain AADC (any platform) and unmodified QuantLib pricers |

Resources: two how-tos whose every snippet the tests run (using AADC: record once, replay, exact derivatives, batch,
QuantLib sensitivities; using the Tracer: the two ways to record, the switches, the questions in order, when a replay
is exact), the agent guide and the release notes shipped inside the `aadc` wheel, the verbs reference, a get-started
page, the package and platform matrix, and the tracing documentation (for agents, for people, model validation, how it
works). Prompts: `get_started`, `validate_pricer`, `add_sensitivities`.

## Scope

The server runs your code on your machine; it is a developer tool, not a sandbox or a hosted service. A tape is one
execution at one input point: it supports "this executed" and "this constant is declared at file:line", never "this is
the only path". The source behind a line is shown when you point `set_source_root` at a matching QuantLib 1.41 `ql/`
tree; the answer says whether the file matches the compiled one.

Platforms follow the packages: `aadc` on Linux x86-64 and arm64, macOS arm64 and Windows x86-64 (CPython 3.10 to 3.14);
`aadc-quantlib-tracing` on Linux x86-64 and macOS arm64. Intel Macs are not supported: the engine has no wheel for them.

## Licence

Proprietary, MatLogica. The `aadc` engine installs in Community Edition: non-commercial and academic use. Commercial
use needs a licence: info@matlogica.com.
