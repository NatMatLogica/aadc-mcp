# Using AADC from an agent: the recipe

AADC records a calculation once as it runs, then replays the record at new inputs and returns every first-order
derivative from one reverse pass, at a fraction of the cost of running the original code again. The calculation can
be Python arithmetic on `aadc.idouble`, or a library built with AADC such as `aadc-quantlib`.

Three packages, one rule each:

- `aadc`: your own Python. Everything that must be differentiated flows through `aadc.idouble` or `aadc.array`. A
  plain `float`, or a `math`/NumPy call that leaves the active type, is a constant on the record with zero derivative.
- `aadc-quantlib`: QuantLib 1.38 with `Real` as the active type. Mark the quotes you care about as inputs and the NPV
  as output; the QuantLib code in between needs no change.
- `aadc-quantlib-tracing`: QuantLib 1.41 built with source tracing. Same code, and the record also carries the
  `file:line` of every operation (the tracer how-to, `aadc://guide/tracer-howto`).

Every snippet below runs as written; the package's tests execute them.

## 1. Record once, replay many

```python
import math
import aadc

f = aadc.Functions()
f.start_recording()
x, y = aadc.idouble(1.0), aadc.idouble(2.0)
ax, ay = x.mark_as_input(), y.mark_as_input()      # handles: replay is addressed through these, never through x and y
z = x * y + aadc.math.exp(x)
az = z.mark_as_output()
f.stop_recording()

ws = f.create_workspace()
ws.set_val(ax, 1.5)
ws.set_val(ay, -0.5)                                # set EVERY input: an unset input reads as NaN, not as its recorded value
ws.forward()
ws.set_diff(az, 1.0)                                # seed the output, then reverse; no seed means zero derivatives
ws.reverse()
assert abs(float(ws.val(az)) - (1.5 * -0.5 + math.exp(1.5))) < 1e-12
assert abs(float(ws.diff(ax)) - (-0.5 + math.exp(1.5))) < 1e-12
assert abs(float(ws.diff(ay)) - 1.5) < 1e-12
assert f.num_passive_warnings() == 0               # no decision was frozen while recording
```

The record is fixed at recording time: a new input is a replay, a new structure is a new recording. `aadc.Kernel` is
the same class as `aadc.Functions`; `with aadc.record_kernel() as k:` records a block with less ceremony.

## 2. The one trap: a Python `if` on an active value

`if s > k:` needs a plain `bool`, so the comparison collapses and the direction taken while recording is frozen into
the record. A replay on the other side of the threshold follows the recorded branch and returns a plausible wrong
number. The engine counts every such collapse; report the count with every recording.

```python
import aadc

def record(use_iif):
    f = aadc.Functions()
    f.start_recording()
    s, k = aadc.idouble(110.0), aadc.idouble(100.0)
    a_s = s.mark_as_input()
    if use_iif:
        pay = aadc.iif(s > k, s - k, aadc.idouble(0.0))    # the comparison stays on the record
    else:
        pay = s - k if s > k else aadc.idouble(0.0)        # collapses to a Python bool: frozen at "true"
    r = pay.mark_as_output()
    f.stop_recording()
    ws = f.create_workspace()
    ws.set_val(a_s, 90.0)                                   # replay out of the money
    ws.forward()
    return float(ws.val(r)), f.num_passive_warnings()

assert record(True) == (0.0, 0)                   # right, and nothing frozen
wrong, frozen = record(False)
assert wrong == -10.0 and frozen == 1             # the recorded branch replays; the engine counted the collapse
```

For arrays use `aadc.where_arr`; for whole functions `aadc.branching_function`. A non-zero passive-warning count is a
finding to explain, never noise.

## 3. Many scenarios: compile, then evaluate in batch

```python
import numpy as np
import aadc

f = aadc.Functions()
f.start_recording()
s, v = aadc.idouble(100.0), aadc.idouble(0.2)
a_s, a_v = s.mark_as_input(), v.mark_as_input()
r = (s * aadc.math.exp(v)).mark_as_output()
f.stop_recording()
f.compile("auto")                                  # the host's vector lanes; compile() alone is the portable scalar kernel

spots = np.linspace(90.0, 110.0, 16)
values, derivs, errors = aadc.evaluate(f, {r: [a_s, a_v]}, {a_s: spots, a_v: np.full(16, 0.2)}, aadc.ThreadPool(2))
assert np.allclose(values[r], spots * np.exp(0.2))
assert np.allclose(derivs[r][a_s], np.exp(0.2))
assert np.allclose(derivs[r][a_v], spots * np.exp(0.2))
```

`aadc.evaluate` replays the record over every row of the inputs, across threads, and returns values and derivatives
together. `aadc.ThreadPool(n)` sizes the workers; keep `n` within the cores you are allowed to use. A `Workspace` is
never shared between threads.

## 4. QuantLib sensitivities without touching the pricer

```python
# needs: quantlib
import aadc
try:
    from aadc_quantlib_tracing import QuantLib as ql     # the traced build: the record also carries file:line
except ImportError:
    from aadc_quantlib import QuantLib as ql             # the production build: same prices, no coordinates

today = ql.Date(15, 6, 2026)
ql.Settings.instance().evaluationDate = today
dc = ql.Actual365Fixed()

f = aadc.Functions()
f.start_recording()
spot, vol = aadc.idouble(100.0), aadc.idouble(0.20)
a_spot, a_vol = spot.mark_as_input(), vol.mark_as_input()
process = ql.BlackScholesMertonProcess(
    ql.QuoteHandle(ql.SimpleQuote(spot)),
    ql.YieldTermStructureHandle(ql.FlatForward(today, 0.0, dc)),
    ql.YieldTermStructureHandle(ql.FlatForward(today, 0.03, dc)),
    ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.TARGET(), ql.QuoteHandle(ql.SimpleQuote(vol)), dc)))
option = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call, 105.0), ql.EuropeanExercise(ql.Date(15, 6, 2027)))
option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
npv = option.NPV().mark_as_output()
f.stop_recording()

ws = f.create_workspace()
ws.set_val(a_spot, 100.0)
ws.set_val(a_vol, 0.20)
ws.forward()
ws.set_diff(npv, 1.0)
ws.reverse()
delta, vega = float(ws.diff(a_spot)), float(ws.diff(a_vol))
assert 0.0 < delta < 1.0 and vega > 0.0

# verify once against a bumped replay of the same record (a check, never the production derivative)
h = 1e-6
ws.set_val(a_spot, 100.0 + h); ws.forward(); up = float(ws.val(npv))
ws.set_val(a_spot, 100.0); ws.forward(); base = float(ws.val(npv))
assert abs((up - base) / h - delta) < 1e-5
```

The inputs are the `aadc.idouble` values handed to QuantLib's quotes; everything QuantLib does with them is on the
record. One reverse pass gives every marked sensitivity at once; more inputs cost almost nothing extra.

## 5. Keep the record

```python
import aadc

f = aadc.Functions()
f.start_recording(trace=True)                      # trace=True: the record carries file:line for every operation
x = aadc.idouble(2.0)
ax = x.mark_as_input()
ay = (x * x).mark_as_output()
f.stop_recording()

blob = f.save_tape()                               # bytes: the whole record, loadable in another process
g = aadc.Functions()
g.load_tape(blob)
assert g.trace_inspect("stats").startswith("# aadc-tape/2 verb=stats status=ok")
```

A saved record can be inspected anywhere (`inspect_tape` on this server, `load_tape` to register a file). A replay
at new inputs is exact in the process that recorded; from a file it is exact when every recorded decision can be
re-checked, and withheld otherwise (the tracer how-to explains which recordings qualify).

## 6. What to tell the user

- Every number comes from the engine: `ws.val`, `ws.diff`, `aadc.evaluate`, `trace_inspect`. Never derive a
  sensitivity by hand from a formula.
- Report the passive-warning count with every recording. If an AAD derivative disagrees with a bumped replay,
  suspect a frozen branch first, then an input that was never marked, then a bug, in that order.
- `aadc.version()` names the engine; `aadc.license_status()` names the edition and the features it enables. Without
  a licence file the engine runs in Community Edition: non-commercial and academic use.
- What changed in the installed engine is the resource `aadc://guide/release-notes`; the wider API map is
  `aadc://guide/agent`.
