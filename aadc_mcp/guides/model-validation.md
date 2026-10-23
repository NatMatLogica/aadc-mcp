<!-- From the MatLogica aadc-tracing documentation (docs/MODEL-VALIDATION.md, 2026-10-19), bundled unchanged. It was written
for that tutorial repository: paths such as examples/..., setup.sh, debug/... and tests/... refer to it. In this
server the equivalents are list_examples / run_example (the bundled scripts), check_environment (the attribution
self-test setup.sh performs) and inspect_tape (the trace_inspect verbs, which postdate this text and add replay,
branches with margins, find, origin, cone and at). -->

# Model documentation, validation, and corner cases

*How a traced tape is used as **ground truth** — by a validation team, and by
an agent working on their behalf.*

## The gap this closes

Model documentation is written **from the source**, and the source is not the
calculation. Between the two sits everything a reader cannot resolve by
reading:

* which branch was taken, for the inputs that matter;
* which of six overloads, adapters or handlers was actually reached;
* which constants were baked in, and where they came from;
* whether a clever-looking optimisation is on the path at all.

A competent writer bridges that gap by **inferring**, and inference is exactly
where a confident, fluent, wrong sentence comes from. Traditional tools do not
close it either: a profiler tells you where time went, not what was computed; a
debugger tells you about one step; a log tells you what someone thought to log.

**A traced tape is a record of what the model actually computed**, with every
operation carrying the C++ file, line and function that produced it.

## 1. Model documentation from ground truth

The workflow is the inverse of the usual one. Instead of reading the code and
describing it, you **run** the model and read what it recorded.

```sh
.venv/bin/python examples/13_quantlib_tour.py
```

For one vanilla European option through QuantLib: **141 leaves over 46 distinct
declaration sites**, and `f.trace_report()` returns the whole thing as Markdown
— an operation census, the input→output dependency, every recorded operation in
order with its source line, the call structure, and the embedded source of every
file cited.

Three properties make that document different from a written one:

* **It cannot describe a path that did not execute.** The tape contains what
  ran.
* **Every claim carries coordinates.** "This constant is 365.25, declared at
  `pricer.cpp:345` in `structuredNoteNpv`" can be checked in ten seconds by
  opening the file. A claim derived from reading the source carries no such
  handle, and the reviewer has to redo the work.
* **It is reproducible.** Same inputs, same report. Two releases can be diffed
  by what they compute rather than by what changed in the repository.

## 2. Verifying documentation against the code

This is the check that is normally impossible to automate, because the
documentation is prose and the code is code. A tape makes one side machine
readable:

| the document claims | the tape can settle it |
|---|---|
| "the model uses a 365-day year" | is there a `daysPerYear` leaf, and is it 365.0 or 365.25? |
| "correlation is a calibrated input" | does `correlation` appear as a **leaf** (hardcoded) or as a marked **input**? |
| "the coupon accrues ACT/365" | `couponBasis = 360.0` at `pricer.cpp:346` says otherwise |
| "no early-exercise approximation" | the operation census and call structure show what ran |
| "this path is not exercised for vanilla trades" | it is either in the tape or it is not |

The example library is written to make this concrete: `daysPerYear = 365.25`
and `couponBasis = 360.0` are declared **eight lines apart** and individually
reasonable. Together they are a coupon accruing on the wrong basis — about 1.5%
too much, forever. No risk report shows it, no caller passes either number, and
a document written from the source would very likely repeat the intent rather
than the behaviour.

## 3. Corner cases: where the model is wrong, and by how much

Run `examples/04_corner_cases.py`. This is the part that is hard to do any
other way.

**The tape tells you where the conditionals are.** Every `if` on an active
value appears in `passive_warnings()` with its file and line. You do not search
for them; the model reports them.

**Then you measure what each one costs.** For each site, pick inputs on the
other side of it, and compare a freshly recorded tape (the truth) against the
original tape replayed there (what a cached tape would have said):

```
scenario                      re-recorded  base replayed        error
base — at the money              8.847184       8.847184    +0.000000  (0%)
spots above the barrier          4.101681      88.840556   +84.738874  (2,066%)
spots far below strike           6.46e-12       1.29e-11    +6.46e-12  (x2.0)
vol below the floor              6.083295       5.964683    -0.118612  (2%)
```

The tape recorded at the money contains **no knock-out at all**, so above the
barrier it keeps pricing a note that has in fact knocked out — a 2,066% error.

**Nothing raises.** The replay returns a number, the adjoints come back, every
mechanical check passes. The active-to-passive list is the only signal, which
is why the production rule is that it must be **empty**, and why a non-empty
one is a map of where to look rather than a nuisance.

Note the deep-OTM row: the ratio is exactly 2 — the branch genuinely flipped —
while both prices are ~1e-11 and the money is immaterial. **A structural
finding and a material one are different things**, and a report that prints
only percentages cannot tell you which you have.

### The two fixes

1. **Re-record per region.** Correct, and it means the tape is only valid where
   it was recorded — which someone has to remember.
2. **Rewrite the conditional with `iIf`** so both arms reach the tape and the
   blend is selected at replay. The site then disappears from the A2P list and
   one tape covers the whole space.

Route 2 is why the American option in `examples/12` — early exercise at *every*
node — reports **0** frozen branches, while the much simpler curve bootstrap
reports 3. Which code freezes a branch is a property of the implementation, not
of how complicated it looks.

## 4. The agent loop

An agent is well suited to this because the work is repetitive and the output
is checkable. The three calls return **structured data**, not prose:

```python
f.traced_leaves()      # [{name, function, file, line, col, value, arg, random, superseded}, ...]
f.passive_warnings()   # [{file, line, col, kind, kind_name, count}, ...]
f.trace_report(...)    # Markdown, for a human reader
```

### Loop A — document an unfamiliar library

1. install the `-tracing` wheel for it;
2. record the smallest representative call;
3. **assert attribution is non-zero** (below);
4. group `traced_leaves()` by `(file, function)` — that is the map of where the
   model's own numbers live;
5. read the operation census and call structure from `trace_report()`;
6. write it up, **keeping the file/line on every claim**;
7. state what was not covered: one execution, one input point.

### Loop B — verify a document against the code

For each factual claim in the document, find the tape evidence for or against
it, and mark claims the tape **cannot** settle as unsettled rather than
guessing. That third category is the valuable one, and it is the one an agent
reading source alone will silently fill in.

### Loop C — explore the branches

This is the loop the A2P list makes possible:

1. record once; read `passive_warnings()` → the set of conditional sites;
2. for each site, search the input space for a point that lands on the other
   arm (bisect on an input the site plausibly depends on; the file and line tell
   you *which* input to move);
3. re-record there, and diff: a changed A2P set, a changed operation census, or
   a large fresh-vs-replayed divergence all mean a genuinely different path;
4. repeat until no new path appears;
5. report the regions found, each with the site that defines it and the error
   from using one tape across the boundary.

`examples/04_corner_cases.py` is steps 1–3 with the scenarios chosen by hand.
Automating step 2 is the obvious extension, and the honest limit is stated
below: **this explores the paths you reach, and cannot prove you reached them
all.**

### Programmatic and MCP access

Everything above is ordinary Python returning dicts and strings, so an agent
with a Python tool, a notebook, or an MCP server wrapping these three calls has
full access. Three things are worth designing in:

* **Return the structured lists, not the rendered report**, when the agent is
  going to compute over the result. Reserve `trace_report()` for human reading
  and for artifacts you want to diff.
* **Keep the coordinates.** A tracing-derived summary that paraphrases away the
  file and line has thrown away the only thing that made it better than a
  guess.
* **Make the attribution assertion part of the tool**, not of the prompt. An
  agent cannot be relied on to remember a precondition that fails silently.

## The failure mode that matters most

**A report with 0% attribution looks exactly like a report about code that has
nothing to say.** Nothing errors: the wheel imports, prices correctly,
differentiates correctly, and reports nothing.

So never conclude "this library has no hardcoded constants" from an empty list:

```python
own = [l for l in f.traced_leaves()
       if l["file"] and "aadcNG" not in l["file"]]
if not own:
    raise SystemExit("attributed nothing — uninstrumented build, or tracing off. "
                     "Not evidence about the library.")
```

Every example here does that, and `setup.sh` refuses to report success if any
installed library attributes nothing.

## What a tape cannot tell you

| supported | NOT supported |
|---|---|
| "this executed" | "this is the only path" |
| "this constant is declared at file:line in function F" | "this constant is used everywhere" |
| "N branches froze on this recording" | "the code has no other branches" |
| "these operations ran, in this order" | "this is what the code means to do" |
| "the value at record time was X" | "X is the value in production" |

And two specific traps:

* **`trace_inputs_as_random=True` widens the branch list; it does not switch it
  on.** Measured on the example pricer: 2 sites without it, 3 with. An audit run
  must set it or it will under-report.
* **A site is (file, line) in that build's own source** — not a cross-library
  identity, and the recorded path is the build machine's.
