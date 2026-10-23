"""Drives the server over stdio the way a client does. Needs aadc; the QuantLib tests need aadc-quantlib-tracing."""
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
import re
import sys

import pytest
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HAVE_TRACING = importlib.util.find_spec("aadc_quantlib_tracing") is not None
needs_tracing = pytest.mark.skipif(not HAVE_TRACING, reason="aadc-quantlib-tracing is not installed here")


def _env(home):
    env = dict(os.environ)
    env.update({"OMP_NUM_THREADS": "1", "AADC_MCP_HOME": str(home), "PYTHONPATH": ROOT})
    return env


def run(home, fn):
    async def main():
        params = StdioServerParameters(command=sys.executable, args=["-m", "aadc_mcp.server"], env=_env(home))
        async with stdio_client(params) as (r, w):
            async with ClientSession(r, w) as s:
                await s.initialize()
                return await fn(s)
    return asyncio.run(main())


async def call(s, tool, **args):
    out = await s.call_tool(tool, args)
    assert not getattr(out, "is_error", getattr(out, "isError", False)), out.content
    return json.loads(out.content[0].text)


def test_catalogue(tmp_path):
    async def body(s):
        tools = {t.name for t in (await s.list_tools()).tools}
        resources = {str(r.uri) for r in (await s.list_resources()).resources}
        prompts = {p.name for p in (await s.list_prompts()).prompts}
        return tools, resources, prompts
    tools, resources, prompts = run(tmp_path, body)
    assert {"check_environment", "trace_script", "inspect_tape", "replay", "set_source_root", "load_tape",
            "list_tapes", "list_examples", "get_example", "run_example"} <= tools
    assert {"aadc://guide/agent", "aadc://guide/get-started", "aadc://guide/inspect-verbs", "aadc://guide/versions",
            "aadc://guide/tracing-for-agents", "aadc://guide/model-validation", "aadc://guide/aadc-howto",
            "aadc://guide/tracer-howto", "aadc://guide/release-notes"} <= resources
    assert {"get_started", "validate_pricer", "add_sensitivities"} <= prompts


def test_environment_and_guides(tmp_path):
    async def body(s):
        env = await call(s, "check_environment")
        guide = await s.read_resource("aadc://guide/agent")
        examples = await call(s, "list_examples")
        return env, guide.contents[0].text, examples
    env, guide, examples = run(tmp_path, body)
    assert env["ready"] is True, env
    assert env["engine"]["selftest"]["derivative_at_3"] == 6.0
    assert "aadc" in guide.lower()
    names = {e["name"] for e in examples["examples"]}
    assert {"hello_aadc", "european_option", "european_greeks", "barrier_option", "bond", "swaption"} <= names


def test_hello_aadc_any_platform(tmp_path):
    async def body(s):
        r = await call(s, "run_example", name="hello_aadc")
        st = await call(s, "inspect_tape", tape_id=r["tape_id"], request="stats")
        return r, st
    r, st = run(tmp_path, body)
    assert r["tape_id"] and r["exit_code"] == 0, r
    assert "dz/dx=" in r["stdout"]
    assert st["header"].get("verb") == "stats"


@needs_tracing
def test_trace_inspect_find_branches(tmp_path):
    async def body(s):
        r = await call(s, "run_example", name="european_option")
        tid = r["tape_id"]
        npv = float(re.search(r"NPV (\S+)", r["stdout"]).group(1))
        found = await call(s, "inspect_tape", tape_id=tid, request=f"find value={npv!r}")
        br = await call(s, "inspect_tape", tape_id=tid, request="branches order=margin limit=5")
        leaves = await call(s, "inspect_tape", tape_id=tid, request="leaves kind=constant limit=5")
        listed = await call(s, "list_tapes")
        return r, npv, found, br, leaves, listed
    r, npv, found, br, leaves, listed = run(tmp_path, body)
    assert r["mode"] == "auto" and r["exit_code"] == 0
    assert r["stats"]["attributed_pct"] > 50, r["stats"]
    assert r["autotrace"]["frozen_sites"] > 0
    assert int(found["header"]["exact"]) >= 1 and "marked OUTPUT" in found["text"]
    assert "FROZEN" in br["text"] and "blackcalculator.cpp" in br["text"]
    assert "constant" in leaves["text"]
    assert listed["tapes"][0]["id"] == r["tape_id"]


@needs_tracing
def test_replay_equals_fresh_reprice(tmp_path):
    """The explicit example marks spot as one input leaf: replay at spot 101 must equal QuantLib priced at 101."""
    async def body(s):
        r = await call(s, "run_example", name="european_greeks")
        tid = r["tape_id"]
        npv = float(re.search(r"NPV (\S+)", r["stdout"]).group(1))
        leaves = await call(s, "inspect_tape", tape_id=tid, request="leaves kind=input by=leaf limit=20", max_lines=60)
        found = await call(s, "inspect_tape", tape_id=tid, request=f"find value={npv!r}")
        return r, tid, npv, leaves, found, s
    # run the first half, collect ids, then replay in the same session
    async def whole(s):
        r, tid, npv, leaves, found, _ = await body(s)
        spot_id = None
        for line in leaves["text"].splitlines():
            m = re.match(r"^\s+(#\d+)\s+\S+\s+(\S+)\s+", line)
            if m and m.group(2) in ("100", "100.0"):
                spot_id = m.group(1)
                break
        out_id = None
        for line in found["text"].splitlines():
            if "marked OUTPUT" in line:
                out_id = line.split()[0]
                break
        assert spot_id and out_id, (leaves["text"], found["text"])
        near = await call(s, "replay", tape_id=tid, assignments=f"{spot_id}=101", out=out_id)
        recorded = await call(s, "replay", tape_id=tid, assignments=f"{spot_id}=101", out=out_id, path_recorded=True)
        return r, npv, near, recorded
    r, npv, near, recorded = run(tmp_path, whole)
    assert "dNPV/dspot" in r["stdout"]
    # A tape read back from a file keeps no operand for a counted ibool->bool conversion (QuantLib's error function
    # chooses a series at errorfunction.cpp:200), so the engine cannot re-check that decision and WITHHOLDS the value.
    # The server must say so, never estimate. Measured on aadc 2.25.2; in memory the same replay is exact.
    assert near["survives"] is False and near["value"] is None, near["text"]
    assert near["unchecked"] and near["unchecked"][0]["file"].endswith("errorfunction.cpp"), near["unchecked"]
    assert near["verdict"].startswith("WITHHELD")
    # path=recorded returns the recorded path's value, labelled, for comparison only; at spot 101 no decision actually
    # flips, so it equals a fresh QuantLib price to the last digit
    fresh = _fresh_european(spot=101.0)
    assert recorded["value_if_path_recorded"] is not None, recorded["text"]
    assert abs(recorded["value_if_path_recorded"] - fresh) <= 1e-12 * max(1.0, abs(fresh)), (recorded["value_if_path_recorded"], fresh)
    assert recorded["value"] is None


def _fresh_european(spot):
    from aadc_quantlib_tracing import QuantLib as ql
    today = ql.Date(15, 6, 2026)
    ql.Settings.instance().evaluationDate = today
    dc = ql.Actual365Fixed()
    process = ql.BlackScholesMertonProcess(
        ql.QuoteHandle(ql.SimpleQuote(spot)),
        ql.YieldTermStructureHandle(ql.FlatForward(today, 0.0, dc)),
        ql.YieldTermStructureHandle(ql.FlatForward(today, 0.03, dc)),
        ql.BlackVolTermStructureHandle(ql.BlackConstantVol(today, ql.TARGET(), 0.20, dc)))
    o = ql.VanillaOption(ql.PlainVanillaPayoff(ql.Option.Call, 105.0), ql.EuropeanExercise(ql.Date(15, 6, 2027)))
    o.setPricingEngine(ql.AnalyticEuropeanEngine(process))
    return float(o.NPV())


@needs_tracing
@pytest.mark.skipif(not os.environ.get("AADC_MCP_TEST_QLSRC"), reason="set AADC_MCP_TEST_QLSRC to the ql/ tree the wheel was built from")
def test_source_root_hash_ok(tmp_path):
    async def body(s):
        r = await call(s, "run_example", name="european_option")
        root = await call(s, "set_source_root", tape_id=r["tape_id"], compiled_prefix="/project/work/QLAADC/ql",
                          local_dir=os.environ["AADC_MCP_TEST_QLSRC"])
        at = await call(s, "inspect_tape", tape_id=r["tape_id"], request="at blackcalculator.cpp:77 context=3")
        return root, at
    root, at = run(tmp_path, body)
    assert root["header"].get("status") == "ok"
    assert at["header"].get("hash") == "ok", at["header"]
    assert "QL_REQUIRE" in at["text"] or "stdDev_" in at["text"]


def test_refusals(tmp_path):
    async def body(s):
        a = await call(s, "inspect_tape", tape_id="nope", request="stats")
        b = await call(s, "trace_script", path="/definitely/not/here.py")
        c = await call(s, "get_example", name="../server")
        return a, b, c
    a, b, c = run(tmp_path, body)
    assert "unknown tape_id" in a["error"]
    assert "no such file" in b["error"]
    assert "no example named" in c["error"]
