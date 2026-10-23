<!-- From the MatLogica aadc-tracing documentation (docs/FOR-AGENTS.md, 2026-10-19), bundled unchanged. It was written
for that tutorial repository: paths such as examples/..., setup.sh, debug/... and tests/... refer to it. In this
server the equivalents are list_examples / run_example (the bundled scripts), check_environment (the attribution
self-test setup.sh performs) and inspect_tape (the trace_inspect verbs, which postdate this text and add replay,
branches with margins, find, origin, cone and at). -->

# What tracing is good for — agents

*The long-form argument is `slides/WHY-TRACING-HELPS-AGENTS.md`. This is the
practical version: what to call, what you get, and what you must not claim.*

## The one-sentence case

An agent asked to document or validate a numerical library reads the source and
**infers** which paths matter — and inference is precisely where a confident,
fluent, wrong sentence comes from. A traced tape replaces inference with a
record of what executed.

**Source describes what can happen. A tape describes what did.**

## The three calls

```python
f = aadc.Functions()
f.start_recording(trace=True, trace_inputs_as_random=True)
...the model...
f.stop_recording()

f.traced_leaves()      # [{name, function, file, line, col, value, arg, random, superseded}, ...]
f.passive_warnings()   # [{file, line, col, kind, kind_name, count}, ...]
f.trace_report(inputs={...}, outputs={...})   # Markdown, ~9 KB for a tiny model
```

The first two are **structured data** — dicts, not prose. Prefer them when you
are going to compute over the result. Use `trace_report()` when a human is
going to read it, or when you want the operation-by-operation listing and the
embedded source in one artifact.

## Recipes

**"Which constants does this model depend on that no caller supplies?"**

```python
own = [l for l in f.traced_leaves()
       if l["file"] and l["file"].endswith((".cpp", ".hpp"))
       and "aadcNG" not in l["file"]]
```

Filter on the **file**, not the count. A wrapper line tells you how an argument
crossed the Python/C++ boundary, not how the model values anything.

**"Is this tape safe to replay under bumped inputs?"**

```python
assert not f.passive_warnings(), "frozen branches — replay may be silently wrong"
```

**"What does this function actually call?"** — the census and call structure in
`trace_report()`, not the call graph in the source.

**"Did this release change the calculation?"** — diff the `(file, line, name,
value)` tuples between two runs.

## The failure mode you must guard against

**A report with 0% attribution looks exactly like a report about code that has
nothing to say.** Nothing errors. The wheel imports, prices correctly,
differentiates correctly, and reports nothing.

So never conclude "this library has no hardcoded constants" from an empty list.
Assert attribution first:

```python
leaves = f.traced_leaves()
own = [l for l in leaves if l["file"] and "aadcNG" not in l["file"]]
if not own:
    raise SystemExit("attributed nothing — uninstrumented build, or tracing off. "
                     "Not evidence about the library.")
```

Every example in this repo does that, and `setup.sh` does it for all three
libraries before it will report success.

## What you may and may not claim

| the tape supports | the tape does NOT support |
|---|---|
| "this executed" | "this is the only path" |
| "this constant is declared at file:line in function F" | "this constant is used everywhere" |
| "N branches froze on this recording" | "this code has no other branches" |
| "these operations ran, in this order" | "this is what the code means to do" |
| "the value at record time was X" | "X is the value in production" |

Two specific traps:

* **A site is (file, line) in that build's own source.** Not a cross-library
  identity. Two repos carrying sibling copies of one function report a constant
  line offset — measured at 11 in `examples/03_toy_swig.py`. Compare values and
  structure across libraries; compare line numbers only within one.

* **Recorded paths are the build machine's** (`/project/packaging/...`). Do not
  report them as if they were the user's checkout, and do not claim the source
  "is missing" — map the prefix.

## Why the answer is checkable

This is the property that matters for an agent, and it is the reason to prefer
a tape over a summary: **every claim carries its own coordinates**. A statement
like

> the coupon accrues on a hardcoded 360 while the schedule uses 365.25

comes with `pricer.cpp:346` and `pricer.cpp:345`, so the human reviewing your
output can open both lines and settle it in ten seconds. A claim derived from
reading the source carries no such handle, and the reviewer has to redo your
work to check it.

Write output that preserves the coordinates. A tracing-derived report that
paraphrases away the file and line has thrown away the only thing that made it
better than a guess.

## A worked loop

1. Install the `-tracing` wheel for the library under study.
2. Record the smallest representative call.
3. **Assert attribution is non-zero.** Stop if it is zero.
4. Pull `traced_leaves()` and `passive_warnings()`.
5. Report findings with file/line/function attached to each.
6. State what you did not cover: one execution, one input point, branches not
   taken are absent.

`examples/01_hello_tracing.py` is that loop in sixty lines, with the assertions
written out.
