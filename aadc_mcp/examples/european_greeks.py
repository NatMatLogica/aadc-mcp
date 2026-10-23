# aadc-mcp: mode=explicit needs=quantlib-tracing platforms=linux-x86_64,macos-arm64
"""A European call recorded once with four marked inputs; one reverse pass gives the price and its exact sensitivities to spot, rate, dividend and volatility together."""
import os

import aadc

try:
    from aadc_quantlib_tracing import QuantLib as ql      # the traced build: the tape carries source coordinates
except ImportError:                                       # the production build: same prices, no tracing
    from aadc_quantlib import QuantLib as ql

today = ql.Date(15, 6, 2026)
ql.Settings.instance().evaluationDate = today
day_count = ql.Actual365Fixed()
values = {"spot": 100.0, "rate": 0.03, "dividend": 0.0, "vol": 0.20}

f = aadc.Functions()
f.start_recording(trace=True, trace_inputs_as_random=False)
active = {name: aadc.idouble(v) for name, v in values.items()}
handles = {name: x.mark_as_input() for name, x in active.items()}
process = ql.BlackScholesMertonProcess(
    ql.QuoteHandle(ql.SimpleQuote(active["spot"])),
    ql.YieldTermStructureHandle(ql.FlatForward(today, ql.QuoteHandle(ql.SimpleQuote(active["dividend"])), day_count)),
    ql.YieldTermStructureHandle(ql.FlatForward(today, ql.QuoteHandle(ql.SimpleQuote(active["rate"])), day_count)),
    ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.TARGET(), ql.QuoteHandle(ql.SimpleQuote(active["vol"])), day_count)))
option = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call, 105.0), ql.EuropeanExercise(ql.Date(15, 6, 2027)))
option.setPricingEngine(ql.AnalyticEuropeanEngine(process))
npv = option.NPV()
out = npv.mark_as_output()
f.stop_recording()

ws = f.create_workspace()
for name, handle in handles.items():
    ws.set_val(handle, values[name])
ws.forward()
ws.set_diff(out, 1.0)
ws.reverse()
print("NPV", repr(float(ws.val(out))))
for name, handle in handles.items():
    print(f"dNPV/d{name} {float(ws.diff(handle))!r}")
print("frozen branches on this recording:", f.num_passive_warnings())

with open(os.environ.get("AADC_TRACE_OUT", "aadc-trace.tape"), "wb") as tape:
    tape.write(f.save_tape())
