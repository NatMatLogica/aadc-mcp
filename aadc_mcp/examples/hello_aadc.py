# aadc-mcp: mode=explicit needs=aadc platforms=all
"""Plain AADC, no QuantLib: record z = x*y + exp(x) once, replay at new inputs, exact derivatives from one reverse pass."""
import math
import os

import aadc

f = aadc.Functions()
f.start_recording(trace=True, trace_inputs_as_random=False)
x, y = aadc.idouble(1.0), aadc.idouble(2.0)
ax, ay = x.mark_as_input(), y.mark_as_input()
z = x * y + aadc.math.exp(x)
az = z.mark_as_output()
f.stop_recording()

ws = f.create_workspace()
for xv, yv in ((1.0, 2.0), (1.5, -0.5)):
    ws.set_val(ax, xv)
    ws.set_val(ay, yv)
    ws.forward()
    ws.set_diff(az, 1.0)
    ws.reverse()
    print(f"x={xv} y={yv}: z={float(ws.val(az))!r}  dz/dx={float(ws.diff(ax))!r} (analytic {yv + math.exp(xv)!r})"
          f"  dz/dy={float(ws.diff(ay))!r} (analytic {xv!r})")
print("frozen branches on this recording:", f.num_passive_warnings())

with open(os.environ.get("AADC_TRACE_OUT", "aadc-trace.tape"), "wb") as out:
    out.write(f.save_tape())
