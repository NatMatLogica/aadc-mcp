<!-- From the MatLogica aadc-tracing documentation (docs/HOW-IT-WORKS.md, 2026-10-19), bundled unchanged. It was written
for that tutorial repository: paths such as examples/..., setup.sh, debug/... and tests/... refer to it. In this
server the equivalents are list_examples / run_example (the bundled scripts), check_environment (the attribution
self-test setup.sh performs) and inspect_tape (the trace_inspect verbs, which postdate this text and add replay,
branches with margins, find, origin, cone and at). -->

# How source tracing works

## The problem

An AADC tape is a record of **one execution**. It replays fast and
differentiates exactly, and by default it is anonymous: a sequence of
operations on numbered slots, with no memory of the source that produced it.

Two things about the recorded code are therefore invisible, and both change
what the tape *means*:

1. **Numbers baked into the library.** A correlation, a barrier level, a day
   count. No caller passes them, so no risk report shows them, and nobody can
   discover them without reading the C++.

2. **Branches taken on active values.** Every `if` the recording walked one arm
   of. The tape contains that arm and not the other, so replaying at inputs
   that would have gone the other way returns a wrong number — silently, with
   no error at replay.

Source tracing makes both reportable from Python, with the C++ file, line,
column and enclosing function that produced them.

## The mechanism

### 1. The compiler plugin

`aadcpp` is a clang wrapper carrying an LLVM pass. With `-faadc-debug` it
rewrites every `CAADNG_*` call site into its `_DBG` twin, which takes an extra
payload describing the source location and the declared identifier.

That payload is emitted into a dedicated ELF section, **`.caadng_dbg`**, in the
compiled object. You can see it on any instrumented artifact:

```sh
unzip -q <wheel> -d /tmp/w && SO=$(find /tmp/w -name '*.so' | head -1)
objdump -h "$SO" | grep caadng_dbg      # expect a section, ~100 KB+
nm -uC "$SO" | grep -c '_DBG'           # expect dozens of _DBG imports
```

**`-faadc-debug` requires `-O2` AND `-g`**, and the wrapper refuses otherwise.
The `-g` is incidental but useful: it means the shipped wheel carries full
DWARF, so the same artifact that produces a tracing report is also debuggable
(see `debug/debug_hello.sh`).

**Never add `-fno-inline`.** Attribution follows inlining, and with that flag
every leaf collapses onto one header line — the same answer for every variable
in the program. Nothing fails loudly; the report just becomes useless.

### 2. The engine side

`libaadc-ng` retains the payloads when recording is started with tracing on.
Each recorded operation gets a side-table entry keyed by tape position, and
each *leaf* — a value constructed from a literal — gets a record carrying its
declaration site and its record-time value.

### 3. The Python surface

```python
f.start_recording(trace=True, trace_inputs_as_random=True)
...
f.traced_leaves()      # constants, with their C++ site
f.passive_warnings()   # frozen branches, with their C++ site
f.trace_report(...)    # the whole thing as Markdown
```

## The four gates

Missing any one produces a report with **0% attribution that otherwise looks
perfectly healthy**. That is the failure mode this whole subject has to be
defensive about: a report that says nothing reads exactly like a report about
code that has nothing to say.

| # | gate | what it means |
|---|---|---|
| 1 | the TU compiled with `aadcpp -faadc-debug` | that is what a `-tracing` wheel *is* |
| 2 | `libaadc-ng` built with source tracing | the published core is, from 2.12.0 |
| 3 | `trace=True` at `start_recording` | otherwise payloads are dropped |
| 4 | `trace_inputs_as_random=True` | **widens the BRANCH list** — incomplete without it; see below |

`setup.sh` checks all of it by recording through each installed library and
refusing to report success if any attributes nothing.

## What `trace_inputs_as_random` does

By default a traced leaf is minted **frozen** — its value is nailed at record
time. With `trace_inputs_as_random=True` each becomes a genuine **input**, so a
comparison against one is an *active* comparison, and collapsing it to a `bool`
is a reportable active-to-passive conversion.

**The trade.** A Random leaf *changes the tape*: constants stop folding, dead
branches record, `iIf` records both arms. The tape becomes a code-flow
instrument rather than a faithful image of the production tape. That is the
right tool for auditing and the wrong one for benchmarking.

**What it actually buys, measured — not "branches on/off".** An earlier draft
of this page said the A2P list is empty without the flag. That was an
assumption and it is wrong. On the example pricer:

| | reported sites |
|---|---|
| `trace=True` only | 2 — `pricer.cpp:394`, `:409` |
| `+ trace_inputs_as_random=True` | 3 — adds `pricer.cpp:384` |

So the flag **strictly widens** the reported set; it does not switch reporting
on. Constants are attributed identically either way (10 pricer leaves in both).

Why line 384 in particular needs it is **not established here**, and this page
does not offer a mechanism it has not verified. The relationship — without-flag
is a strict subset of with-flag — is pinned by
`tests/test_tracing.py::test_branches_need_random`, which fails if it ever
stops holding.

The practical rule is unchanged: **turn it on when you are auditing for frozen
branches**, because the set you get without it is incomplete.

## What a leaf carries

Nine fields. `01_hello_tracing.py` prints all of them.

| field | meaning |
|---|---|
| `name` | the **declared variable** — `'correlation'` |
| `function` | the **enclosing function** — `'structuredNoteNpv'` |
| `file`, `line`, `col` | where it was declared |
| `value` | its value **at record time** |
| `arg` | a handle, if it is settable at replay |
| `random` | live input, or frozen at the recorded value |
| `superseded` | was this declaration later overwritten |

`name` is `None` for an unnamed temporary: the plugin reports a **declared
identifier of the attributed frame**, never reconstructed source text. `file`,
`line` and `function` are always exact.

Do not confuse `name` with `function`. An early draft of the hello-world
printed only `function` and `value`, which made a traced constant look like
`structuredNoteNpv = 0.35` and read as a missing name. It was never missing.

## What a frozen branch carries

| field | meaning |
|---|---|
| `file`, `line`, `col` | the conditional's source position |
| `kind_name` | e.g. `IBOOL2BOOL` — an `ibool` collapsed to a `bool` |
| `kind` | the numeric kind id |
| `count` | how many times this site converted |

## Limits, stated

* **A site is (file, line) in that library's own source.** Exact for the build
  that produced it; **not** a cross-library identity. Two repositories holding
  sibling copies of the same function report a constant line-number offset —
  `03_toy_swig.py` demonstrates exactly that, with an offset of 11.

* **Recorded paths are the build machine's.** The wheels are built in a
  manylinux container, so a path reads `/project/packaging/...`. File, line and
  function are still exact; map the prefix to a local checkout to see source
  (`debug/debug_hello.sh` does this for gdb).

* **The tape is one execution.** Tracing tells you what *did* happen, never
  what *could*. A branch not taken is absent, not reported as unexplored.

* **At `-O2` the debugger is approximate where the report is exact.** A line
  breakpoint binds to the nearest surviving instruction; some locals read
  `<optimized out>`. The tracing report has no such ambiguity — it is recorded
  by the running program, not reconstructed from debug info.

* **Attribution follows the translation unit that RECORDED the operation.**
  `idoubleNG` is header-only, so library header code instantiated by a wrapper
  records from the *wrapper's* TU. This is why the instrumented wheels compile
  the wrapper too; instrumenting only the library left bond attribution at
  178/196 instead of 197/197.
