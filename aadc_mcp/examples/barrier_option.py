# aadc-mcp: mode=auto needs=quantlib-tracing platforms=linux-x86_64,macos-arm64
"""An up-and-out barrier call (spot 100, strike 105, barrier 130) with QuantLib's analytic barrier engine; the knock test is one of the recorded decisions."""
from aadc_quantlib_tracing import QuantLib as ql

today = ql.Date(15, 6, 2026)
ql.Settings.instance().evaluationDate = today
day_count = ql.Actual365Fixed()

process = ql.BlackScholesMertonProcess(
    ql.QuoteHandle(ql.SimpleQuote(100.0)),
    ql.YieldTermStructureHandle(ql.FlatForward(today, 0.0, day_count)),
    ql.YieldTermStructureHandle(ql.FlatForward(today, 0.03, day_count)),
    ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.TARGET(), 0.20, day_count)))
option = ql.BarrierOption(ql.Barrier.UpOut, 130.0, 0.0,
                          ql.PlainVanillaPayoff(ql.Option.Call, 105.0),
                          ql.EuropeanExercise(today + ql.Period(1, ql.Years)))
option.setPricingEngine(ql.AnalyticBarrierEngine(process))
print("NPV", option.NPV())
