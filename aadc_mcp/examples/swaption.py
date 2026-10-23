# aadc-mcp: mode=auto needs=quantlib-tracing platforms=linux-x86_64,macos-arm64
"""A one-into-five-year European payer swaption under Hull-White with QuantLib's Jamshidian engine: curves, schedules, a short-rate model and a root search, all recorded."""
from aadc_quantlib_tracing import QuantLib as ql

today = ql.Date(6, 10, 2026)
ql.Settings.instance().evaluationDate = today
calendar = ql.TARGET()
curve = ql.YieldTermStructureHandle(
    ql.FlatForward(today, ql.QuoteHandle(ql.SimpleQuote(0.03)), ql.Actual365Fixed()))
index = ql.Euribor6M(curve)
start = calendar.advance(today, ql.Period(1, ql.Years))
end = calendar.advance(start, ql.Period(5, ql.Years))
fixed = ql.Schedule(start, end, ql.Period(ql.Annual), calendar,
                    ql.ModifiedFollowing, ql.ModifiedFollowing, ql.DateGeneration.Forward, False)
floating = ql.Schedule(start, end, ql.Period(ql.Semiannual), calendar,
                       ql.ModifiedFollowing, ql.ModifiedFollowing, ql.DateGeneration.Forward, False)
swap = ql.VanillaSwap(ql.VanillaSwap.Payer, 1_000_000.0, fixed, 0.03,
                      ql.Thirty360(ql.Thirty360.BondBasis), floating, index, 0.0, ql.Actual360())
swaption = ql.Swaption(swap, ql.EuropeanExercise(start))
model = ql.HullWhite(curve, 0.05, 0.01)
swaption.setPricingEngine(ql.JamshidianSwaptionEngine(model))
print("NPV", swaption.NPV())
