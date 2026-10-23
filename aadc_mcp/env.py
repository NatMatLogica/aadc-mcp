"""check_environment: what this interpreter can do with AADC and the Tracer, measured rather than assumed.

Every fact here comes from the installed packages and two tiny runs: the engine records z = x*x and must return
dz/dx = 6 at x = 3; the traced QuantLib build records one discount factor and must attribute at least one leaf to
QuantLib's own C++. A traced build that attributes nothing looks exactly like a healthy one, so that count is the
first thing to check and the self-test refuses to call it ready.
"""
from __future__ import annotations

import importlib.metadata as md
import platform
import sys
import time

DISTS = ("aadc", "aadc-quantlib", "aadc-quantlib-tracing", "QuantLib", "numpy", "scipy", "mcp")
TRACING_PY = (10, 11, 12, 13, 14)        # CPython minors with aadc-quantlib-tracing wheels
TRACING_PLATFORMS = "Linux x86-64 and macOS arm64"   # where aadc-quantlib-tracing wheels exist (1.41.4, 2026-10-22)
MIN_AADC = (2, 25, 2)                    # first wheel with trace_inspect replay verdicts as documented here
TRACING_INSTALL = 'pip install "aadc-quantlib-tracing>=1.41.4,<1.42"'


def _version(name):
    try:
        return md.version(name)
    except md.PackageNotFoundError:
        return None


def _tuple(version):
    out = []
    for part in version.split(".")[:3]:
        digits = "".join(ch for ch in part if ch.isdigit())
        out.append(int(digits) if digits else 0)
    return tuple(out)


def _line(version):
    """'1.41.1' -> '1.41': the QuantLib line a wheel wraps."""
    return ".".join(version.split(".")[:2])


def engine_selftest():
    """Record z = x*x, replay at x = 3, reverse. Proves the engine runs in this interpreter and times it."""
    import aadc

    t0 = time.perf_counter()
    f = aadc.Functions()
    f.start_recording()
    x = aadc.idouble(1.0)
    ax = x.mark_as_input()
    ay = (x * x).mark_as_output()
    f.stop_recording()
    ws = f.create_workspace()
    ws.set_val(ax, 3.0)
    ws.forward()
    value = float(ws.val(ay))
    ws.set_diff(ay, 1.0)
    ws.reverse()
    derivative = float(ws.diff(ax))
    ms = (time.perf_counter() - t0) * 1e3
    return {
        "ok": abs(value - 9.0) < 1e-12 and abs(derivative - 6.0) < 1e-12,
        "value_at_3": value,
        "derivative_at_3": derivative,
        "passive_warnings": int(f.num_passive_warnings()),
        "ms": round(ms, 2),
    }


def tracing_selftest():
    """One traced QuantLib call. The number of leaves attributed to QuantLib's C++ must be above zero."""
    import aadc
    from aadc_quantlib_tracing import QuantLib as ql

    f = aadc.Functions()
    f.start_recording(trace=True, trace_inputs_as_random=True)
    today = ql.Date(15, 9, 2026)
    ql.Settings.instance().evaluationDate = today
    q = aadc.idouble(0.03)
    q.mark_as_input()
    rate = ql.InterestRate(q, ql.Actual365Fixed(), ql.Continuous, ql.Annual)
    df = rate.discountFactor(1.0)
    df.mark_as_output()
    f.stop_recording()
    own = [l for l in f.traced_leaves()
           if l.get("file") and l["file"].endswith((".cpp", ".hpp", ".h")) and "aadcNG" not in l["file"]]
    return {"ok": len(own) > 0, "attributed_leaves": len(own), "trace_inspect": hasattr(f, "trace_inspect")}


def check_environment() -> dict:
    py = sys.version_info
    system, machine = platform.system(), platform.machine()
    packages = {name: _version(name) for name in DISTS}
    tracing_platform = ((system == "Linux" and machine in ("x86_64", "AMD64"))
                        or (system == "Darwin" and machine == "arm64"))
    tracing_wheel_here = tracing_platform and py[0] == 3 and py[1] in TRACING_PY
    findings = []          # {"level": ok|note|warn|fail, "what": ..., "fix": ...}

    report = {
        "python": f"{py[0]}.{py[1]}.{py[2]}",
        "executable": sys.executable,
        "platform": f"{system} {machine}",
        "packages": packages,
        "engine": None,
        "tracing": None,
        "tracing_wheel_available_for_this_platform": tracing_wheel_here,
        "findings": findings,
    }

    # --- the engine ---------------------------------------------------------------------------------------
    if packages["aadc"] is None:
        findings.append({"level": "fail", "what": "the aadc engine is not installed in this interpreter",
                         "fix": 'pip install "aadc>=2.25.2"'})
    else:
        try:
            import aadc
            licence = aadc.license_status() or {}
            engine = {
                "wheel": getattr(aadc, "__version__", packages["aadc"]),
                "engine": getattr(aadc, "__engine_version__", None),
                "licence_state": licence.get("state"),
                "licence_detail": licence.get("detail"),
                "features_enabled": sorted(k for k, v in (licence.get("features") or {}).items() if v),
            }
            engine["selftest"] = engine_selftest()
            report["engine"] = engine
            if not engine["selftest"]["ok"]:
                findings.append({"level": "fail",
                                 "what": "the engine self-test (record, replay, reverse) did not return dz/dx = 6 at x = 3",
                                 "fix": "reinstall aadc into a clean environment and run check_environment again"})
            if _tuple(str(engine["wheel"])) < MIN_AADC:
                findings.append({"level": "warn",
                                 "what": f"aadc {engine['wheel']} predates the tape-inspection verbs this server uses "
                                         f"(replay verdicts, branches with margins)",
                                 "fix": 'pip install --upgrade "aadc>=2.25.2"'})
            if licence.get("state") != "licensed":
                findings.append({"level": "note",
                                 "what": "Community Edition: non-commercial and academic use only; the features the "
                                         "licence enables are listed under engine.features_enabled",
                                 "fix": "commercial use needs a licence from MatLogica (info@matlogica.com)"})
        except Exception as exc:  # noqa: BLE001 - the report is the place to show it
            findings.append({"level": "fail", "what": f"import aadc failed: {type(exc).__name__}: {exc}",
                             "fix": "check that this interpreter is the one aadc was installed into"})

    # --- the traced QuantLib build -------------------------------------------------------------------------
    if packages["aadc-quantlib-tracing"] is None:
        if tracing_wheel_here:
            findings.append({"level": "note", "what": "QuantLib with source tracing is not installed",
                             "fix": TRACING_INSTALL + "   (QuantLib 1.41; import: from aadc_quantlib_tracing import QuantLib as ql)"})
        else:
            findings.append({"level": "note",
                             "what": f"aadc-quantlib-tracing has no wheel for {system} {machine} / Python {py[0]}.{py[1]} "
                                     f"({TRACING_PLATFORMS}, CPython 3.10-3.14)",
                             "fix": f"trace on a {TRACING_PLATFORMS} machine or container; aadc and aadc-quantlib "
                                    "(exact AAD sensitivities, no tracing) run on this platform"})
    else:
        try:
            tracing = tracing_selftest()
            tracing["quantlib_line"] = _line(packages["aadc-quantlib-tracing"])
            report["tracing"] = tracing
            if not tracing["ok"]:
                findings.append({"level": "fail",
                                 "what": "aadc-quantlib-tracing imported but attributed nothing to QuantLib's C++: "
                                         "an uninstrumented build, or tracing off",
                                 "fix": 'pip install --force-reinstall "aadc-quantlib-tracing==1.41.*"'})
        except Exception as exc:  # noqa: BLE001
            findings.append({"level": "fail", "what": f"the tracing self-test failed: {type(exc).__name__}: {exc}",
                             "fix": "aadc and aadc-quantlib-tracing must come from the same index, and exactly one "
                                    "AADC runtime may be installed in the interpreter"})

    # --- combinations --------------------------------------------------------------------------------------
    if packages["aadc-quantlib"] and packages["aadc-quantlib-tracing"]:
        a, b = _line(packages["aadc-quantlib"]), _line(packages["aadc-quantlib-tracing"])
        if a != b:
            findings.append({"level": "warn",
                             "what": f"aadc-quantlib wraps QuantLib {a} and aadc-quantlib-tracing wraps QuantLib {b}: "
                                     f"the two builds price with different QuantLib versions",
                             "fix": "use one build per question; compare prices across the two only as a check"})
    if packages["QuantLib"] and (packages["aadc-quantlib"] or packages["aadc-quantlib-tracing"]):
        findings.append({"level": "note",
                         "what": f"PyPI QuantLib {packages['QuantLib']} is also installed; it is a separate build and is never traced",
                         "fix": "import the traced build explicitly: from aadc_quantlib_tracing import QuantLib as ql"})

    report["ready"] = bool(report["engine"] and report["engine"]["selftest"]["ok"])
    report["ready_for_tracing"] = bool(report["tracing"] and report["tracing"]["ok"])
    worst = "fail" if any(f["level"] == "fail" for f in findings) else \
            "warn" if any(f["level"] == "warn" for f in findings) else "ok"
    report["summary"] = (
        f"AADC {'runs' if report['ready'] else 'does not run'} in {sys.executable}; "
        f"QuantLib tracing {'ready' if report['ready_for_tracing'] else 'not available'}; "
        f"{len(findings)} finding(s), worst: {worst}."
    )
    return report
