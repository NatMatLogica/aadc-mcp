<!-- From the MatLogica aadc-tracing documentation (docs/FOR-HUMANS.md, 2026-10-19), bundled unchanged. It was written
for that tutorial repository: paths such as examples/..., setup.sh, debug/... and tests/... refer to it. In this
server the equivalents are list_examples / run_example (the bundled scripts), check_environment (the attribution
self-test setup.sh performs) and inspect_tape (the trace_inspect verbs, which postdate this text and add replay,
branches with margins, find, origin, cone and at). -->

# What tracing is good for — people

Five things you can do with a traced tape that you cannot do by reading the
source, each with the command that does it.

## 1. Find the numbers nobody passed in

Every pricing library accumulates them: a correlation, a barrier multiple, a
day count, a tolerance. They are arguments to nothing, so they appear in no
risk report, and the only way to find them is to read the C++.

```python
for leaf in f.traced_leaves():
    if leaf["file"] and leaf["file"].endswith(".cpp"):
        print(leaf["name"], "=", leaf["value"], "at",
              leaf["file"], leaf["line"], "in", leaf["function"])
```

Run `examples/01_hello_tracing.py`. Eight parameters come back from a
forty-line pricer, **named**. On QuantLib (`examples/13_quantlib_tour.py`) it
is 141 leaves over 46 declaration sites for a single vanilla option.

**The payoff is not the list, it is the pairs.** In the example pricer,
`daysPerYear = 365.25` and `couponBasis = 360.0` are declared eight lines
apart and are individually reasonable. Together they are a coupon accruing on
the wrong basis — roughly 1.5% too much, forever. That is a mispricing you can
see in the report and cannot see in a risk system.

## 2. Find the branches that will silently lie to you at replay

An AADC tape is one execution. Every `if` on an active value froze its
direction when you recorded, so replaying at inputs on the other side of that
comparison returns a wrong price *and* a wrong adjoint, with nothing raised.

```python
for w in f.passive_warnings():
    print(w["file"], w["line"], w["kind_name"], "x", w["count"])
```

This is the check to run before trusting a tape for bumped-scenario risk. The
production rule in AADC is that this list must be **empty**; tracing is what
tells you *which line* to fix when it is not.

Worth knowing: the answer is often not where you would guess. In this
tutorial, the American option with early exercise at every node reports **0**
frozen branches (the decision is carried as a blend of both arms), while the
much simpler curve bootstrap reports **3**. Which code freezes a branch is a
property of the implementation, not of how complicated it looks.

## 3. Understand an unfamiliar pricer in minutes

Point it at code you did not write, price something ordinary, and read what
the tape says actually ran:

```sh
bash setup.sh && .venv/bin/python examples/13_quantlib_tour.py
```

The report names `ActualActual::ISMA` deriving its own coupons-per-year,
`interestrate.cpp` discounting through `exp(r·t)`, `cashflows.cpp` accumulating
`npv += cf.amount() * df`. No call-graph reading, no guessing which of six
overloads was reached — the tape only contains what executed.

`f.trace_report()` gives the whole thing as Markdown: an operation census, the
input→output dependency, every operation in order with its source line, the
call structure and the embedded source.

## 4. Diff two releases by what they actually compute

The constant set and the site list are stable, comparable artifacts. Record
the same pricing against two versions of a library and diff:

* a constant that changed value without a release note;
* a new frozen branch that was not there last quarter;
* a site that vanished because a code path stopped being reached.

This is a behavioural diff. A source diff tells you what changed in the
repository; this tells you what changed in the calculation.

## 5. Step from the report into the debugger

The `-tracing` wheels are built with `-O2 -g`, so the same artifact carries
DWARF. The report says a constant came from `pricer.cpp:340`; you can stop
there and look at it.

```sh
bash debug/debug_hello.sh            # interactive
bash debug/debug_hello.sh --batch    # non-interactive proof it stops
```

Two instruments, one claim. Note the asymmetry, though: at `-O2` a **line**
breakpoint binds to the nearest surviving instruction (`break pricer.cpp:340`
lands on 353, because the constant is folded and that address "contains no
code"), and some locals read `<optimized out>`. Break on the **function**.
The report is exact where the debugger is approximate.

## What it will not do

* It will not tell you about a branch you did not take. The tape is one
  execution; an unexplored path is absent, not flagged.
* It will not give you a cross-library identity. A site is (file, line) in
  *that* build's source.
* It will not survive `-fno-inline`, which collapses every leaf onto one
  header line while still looking like it worked.
* It is not free at record time in the `trace_inputs_as_random` mode: Random
  leaves stop constants folding and make dead branches record. Use it to
  audit, not to benchmark.
* **Without `trace_inputs_as_random` the branch list is INCOMPLETE, not
  empty.** Measured on the example pricer: 2 sites without it, 3 with. An
  audit run must set it, or it will under-report.
