# aadc-mcp: mode=auto needs=quantlib-tracing platforms=linux-x86_64,macos-arm64
"""A European call priced with QuantLib's analytic engine. An ordinary script with no AADC calls; the tracer records it."""
from aadc_quantlib_tracing import QuantLib as ql

today = ql.Date(15, 6, 2026)
ql.Settings.instance().evaluationDate = today
day_count = ql.Actual365Fixed()

rates = ql.YieldTermStructureHandle(ql.FlatForward(today, 0.03, day_count))
dividends = ql.YieldTermStructureHandle(ql.FlatForward(today, 0.0, day_count))
vols = ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.TARGET(), 0.20, day_count))
spot = ql.QuoteHandle(ql.SimpleQuote(100.0))

option = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call, 105.0),
                          ql.EuropeanExercise(ql.Date(15, 6, 2027)))
option.setPricingEngine(ql.AnalyticEuropeanEngine(ql.BlackScholesMertonProcess(spot, dividends, rates, vols)))
print("NPV", option.NPV())
