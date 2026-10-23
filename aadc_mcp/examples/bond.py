# aadc-mcp: mode=auto needs=quantlib-tracing platforms=linux-x86_64,macos-arm64
"""A seven-year fixed-rate bond priced with QuantLib's discounting engine; day-count and coupon constants come from inside the library."""
from aadc_quantlib_tracing import QuantLib as ql

today = ql.Date(15, 6, 2026)
ql.Settings.instance().evaluationDate = today
calendar, day_count = ql.TARGET(), ql.Actual365Fixed()

curve = ql.YieldTermStructureHandle(ql.FlatForward(today, 0.042, day_count))
issue = calendar.advance(today, ql.Period("2D"))
maturity = calendar.advance(issue, ql.Period("7Y"))
schedule = ql.Schedule(issue, maturity, ql.Period("1Y"), calendar,
                       ql.Unadjusted, ql.Unadjusted, ql.DateGeneration.Backward, False)
bond = ql.FixedRateBond(2, 100.0, schedule, [0.045], ql.ActualActual(ql.ActualActual.ISMA, schedule))
bond.setPricingEngine(ql.DiscountingBondEngine(curve))
print("NPV", bond.NPV())
