# Using the Tracer from an agent

The Tracer is the AADC engine recording with source coordinates: every operation on the record knows the file, line
and function that produced it, across the pricer and the libraries it calls, provided those libraries were built
with AADC (`aadc-quantlib-tracing` is QuantLib 1.41 built that way). The record answers questions that reading the
source cannot: which constants reached the price and from where, which decisions were taken and how close each was
to going the other way, where a printed number was computed, and what the price would be at other inputs.

Every snippet below runs as written; the package's tests execute them.

## Two ways to record

**1. An unmodified script, with the environment switch.** Nothing in the script changes. `trace_script` does this
for you; by hand it is `AADC_TRACE=1 python pricer.py`. Every value the script created is a constant on the record,
attributed to the library line that first used it. This record is a code-flow instrument: use it to find constants,
decisions and origins. Do not use it for what-ifs on the script's own inputs (section "When a replay is exact").

**2. An explicit recording with marked inputs.** The script opens a recording, hands `aadc.idouble` values to the
library, marks them as inputs and the price as output, and saves the record. Each marked input is one leaf, so a
what-if moves it in one assignment, the replay is exact, and one reverse pass gives exact sensitivities. The bundled
`european_greeks` is the pattern; the `add_sensitivities` prompt writes one from an existing script.

## The switches (measured on the bundled `european_option`, aadc 2.25.2, aadc-quantlib-tracing 1.41.4)

| variable | effect |
|---|---|
| `AADC_TRACE=1` | record the whole run; at exit write `aadc-trace.tape` in the working directory and print a census to stderr (`[aadc-autotrace] sealed: 38 active-to-passive SITE(S), 74 conversion(s)`) |
| `AADC_TRACE_OUT=<path>` | write the record there instead |
| `AADC_TRACE_OUTPUTS=value=<number>` | declare the program's result on the record, so `find` reports it as `marked OUTPUT` and `replay` can target it; several selectors are separated by commas; `file.py:line` selects by site |
| `AADC_TRACE_REPORT=1` | also write `<out>.md`, a readable report of the record |
| `AADC_TRACE_JSON=1` | also write `<out>.json`, the census as data |
| `AADC_TRACE_INCLUDE=<file>` / `AADC_TRACE_EXCLUDE=<file>` | record only, or everything but, operations attributed to matching files (`INCLUDE=blackcalculator.cpp` kept 19 of 38 decision sites and a fifth of the bytes) |
| `AADC_TRACE_START=<file:line>` / `AADC_TRACE_END=<file:line>` | recording starts paused until that site executes, or stops when it does; a site that never executes leaves an empty record |
| `AADC_TRACE_LEAVES=random` | how the script's values enter the record: `random` (default) makes each a settable leaf (`leaves` lists 95 inputs, `replay` can move them); `diff` makes each a differentiable hard-coded leaf (the census then counted 0 conversion sites and `leaves` lists 95 hard-coded); any other value runs the script untraced, with one warning line |
| `AADC_SOURCE_ROOTS=COMPILED=LOCAL;...` | read when a record is inspected: maps the compiled source prefix (`/project/work/QLAADC/ql` for the 1.41 wheel) to a local tree, so `at` shows the code with `hash=ok` or `hash=MISMATCH`; the `source root=` verb and `set_source_root` do the same per record |

The variables are read by the engine inside the traced process; `trace_script` sets `AADC_TRACE`, `AADC_TRACE_OUT`
and, from its `outputs` argument, `AADC_TRACE_OUTPUTS`.

```python
# needs: quantlib-tracing
import os, subprocess, sys, aadc

script = "pricer.py"
with open(script, "w") as fh:
    fh.write(
        "from aadc_quantlib_tracing import QuantLib as ql\n"
        "today = ql.Date(15, 6, 2026); ql.Settings.instance().evaluationDate = today\n"
        "r = ql.InterestRate(0.03, ql.Actual365Fixed(), ql.Continuous, ql.Annual)\n"
        "print('DF', r.discountFactor(2.0))\n")
env = dict(os.environ, AADC_TRACE="1", AADC_TRACE_OUT="pricer.tape", AADC_TRACE_REPORT="1", OMP_NUM_THREADS="1")
run = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True, check=True)
df = run.stdout.split("DF")[1].split()[0]
assert "[aadc-autotrace] sealed:" in run.stderr               # the census; a run without this line was not traced
assert os.path.exists("pricer.tape") and os.path.exists("pricer.tape.md")

f = aadc.Functions()
f.load_tape(open("pricer.tape", "rb").read())
stats = f.trace_inspect("stats")
assert stats.startswith("# aadc-tape/2 verb=stats status=ok")
assert "attributed" in stats and "interestrate" in f.trace_inspect("sites limit=20")
assert "exact=" in f.trace_inspect(f"find value={df}").splitlines()[0]
```

## The questions, in order

1. `stats`: how many entries, how many attributed, how many frozen decisions. **An attributed share of 0 means an
   uninstrumented build or tracing off, not a library with nothing to say. Stop there.**
2. `leaves kind=constant limit=40`: every constant that reached the price with its declaration line and value,
   including the ones the script never passed in (tolerances, day counts, solver brackets).
3. `branches order=margin limit=10`: every decision frozen at record time, closest to flipping first, with the
   margin and the `file:line`.
4. `find value=<the printed price>`: where the number was computed; the row marked OUTPUT is the one to replay.
5. `origin #N` and `at file:line`: the formula behind a value, and the source line with the recorded values written
   in (`hash=ok` when the local file is the one compiled; `set_source_root` maps the paths).
6. `replay set=#N=<value> out=#M`: the price at other inputs, with a verdict.

The grammar and the verdict table are in `aadc://guide/inspect-verbs`.

## When a replay is exact

A replay re-evaluates the record at new inputs and re-checks every recorded decision. Three facts decide whether the
number it returns is the price:

- **In the process that recorded, with marked inputs, it is exact**: the same digits as pricing again. The snippet
  below shows it.
- **From a record read back from a file, some decisions cannot be re-checked** (a counted conversion of a comparison
  to a plain `bool` keeps no operand in the file). The engine then answers `UNCHECKED` for that decision and the value
  is withheld. Say so, name the `file:line`, and re-run the script at the new inputs for the price. Never estimate.
- **On an unmodified-script record, moving a constant is not a what-if on the script's input**, even in process: the
  script's value may sit in several leaves, and a value derived from it before it entered the record (a variance from
  a volatility) does not move at all. For a what-if, record explicitly with that input marked.

```python
# needs: quantlib-tracing
import aadc
from aadc_quantlib_tracing import QuantLib as ql

today = ql.Date(15, 6, 2026)
ql.Settings.instance().evaluationDate = today
dc = ql.Actual365Fixed()

f = aadc.Functions()
f.start_recording(trace=True, trace_inputs_as_random=False)
spot = aadc.idouble(100.0)
a_spot = spot.mark_as_input()
process = ql.BlackScholesMertonProcess(
    ql.QuoteHandle(ql.SimpleQuote(spot)),
    ql.YieldTermStructureHandle(ql.FlatForward(today, 0.0, dc)),
    ql.YieldTermStructureHandle(ql.FlatForward(today, 0.03, dc)),
    ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.TARGET(), 0.20, dc)))
option = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call, 105.0), ql.EuropeanExercise(ql.Date(15, 6, 2027)))
option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
out = option.NPV().mark_as_output()
f.stop_recording()

# the ids come from answers: rows start with #N; header lines start with "# " and are not rows
import re
leaves = f.trace_inspect("leaves kind=input by=leaf")
spot_id = re.search(r"^\s+(#\d+)\s", leaves, re.M).group(1)             # the one marked input
found = f.trace_inspect("find value=%r" % float(option.NPV()))
out_id = re.search(r"^\s+(#\d+)\s.*marked OUTPUT", found, re.M).group(1)

# exact, in the recording process: the same digits as pricing again at 101
replay = f.trace_inspect(f"replay set={spot_id}=101 out={out_id}")
assert "flips=0" in replay.splitlines()[0] and "SURVIVES" in replay
value = float(next(l for l in replay.splitlines() if l.strip().startswith(out_id)).split("->")[-1])
ws = f.create_workspace(); ws.set_val(a_spot, 101.0); ws.forward()
assert value == float(ws.val(out))

# the same request on the record read back from a file carries a verdict; it is exact only when every decision re-checks
g = aadc.Functions(); g.load_tape(f.save_tape())
again = g.trace_inspect(f"replay set={spot_id}=101 out={out_id}")
assert again.startswith("# aadc-tape/2 verb=replay")
```

## What to tell the user

- Every number and every `file:line` comes from the engine's answer. Quote them as returned.
- A record is one execution at one input point: it supports "this executed" and "this constant is declared at
  file:line", never "this is the only path".
- A withheld replay is an answer: the decision that could not be checked, with its coordinates. Offer the re-run.
- The validation loop that turns a record into a document a reviewer can check is `aadc://guide/model-validation`;
  the `validate_pricer` prompt runs it.
