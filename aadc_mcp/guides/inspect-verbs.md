# The tape-inspection verbs

`inspect_tape(tape_id, request)` passes one plain-text request to the engine (`Functions.trace_inspect`, aadc 2.25.2)
and returns its plain-text answer. The first line of every answer is a header, `# aadc-tape/2 verb=... key=value ...`,
which the server also returns parsed. A malformed request answers `status=error reason=...` in that header; it is a
normal answer, not an exception.

**Ids.** Every value on a traced tape is an entry `#N`. Ids come from answers (`find`, `leaves`, `branches`). A bare
number in a request is always a value, never an id.

| verb | the question it answers | example request |
|---|---|---|
| `stats` | what am I looking at: entries, attributed share, sites, inputs, constants, frozen branches | `stats` |
| `leaves` | every input and constant with its declaration line and record-time value; `suspicious=on` flags a constant whose line holds no literal | `leaves kind=constant limit=40` · `leaves kind=input by=leaf` |
| `branches` | every decision frozen at record time with its signed margin (how far the comparison was from going the other way), closest first | `branches order=margin limit=10` · `branches at=blackcalculator.cpp:77` |
| `sites` | which source lines did the work, busiest first | `sites limit=20` · `sites file=interestrate.cpp` |
| `find` | where a printed number was computed; exact matches first; the marked OUTPUT named | `find value=7.1280646692617395` · `find value=7.128 rtol=1e-4` |
| `origin` | the formula behind a value, folded over its inputs, with the source | `origin #384` |
| `uses` | everything that reads a value | `uses #150` |
| `cone` | which leaves can move a value through a derivative, and which only by flipping a branch | `cone #384` |
| `at` | the source around a line with the recorded values written in, the FROZEN marker and margin; `hash=ok` when the file shown is the one compiled | `at blackcalculator.cpp:77 context=5` |
| `source` | map compiled paths to a local tree, once per tape (also `set_source_root`) | `source root=/project/work/QLAADC/ql=/opt/QuantLib-1.41/ql` |
| `replay` | re-evaluate the tape at new inputs without re-running the model; withheld when a recorded decision flips (also the `replay` tool, which parses the verdict) | `replay set=#12=101 out=#384` |

## Replay verdicts

| header | meaning | what to say |
|---|---|---|
| `flips=0` and every decision SURVIVES | the recorded path holds; the value is exact, equal to a fresh run to the last digit | quote the value |
| `FLIPPED #N ... file:line (decided true -> false)` | a recorded decision would go the other way at these inputs; outputs past it are SUSPECT | the price at these inputs would follow a different code path, at `file:line`; no value |
| `UNCHECKED ... file:line` | a decision the tape cannot re-evaluate (a counted active-to-passive conversion whose operand is not recorded) | the tape cannot check this move; no value |
| `CROSSED` (a `max`/`min`/`abs` kink) | the value stays valid, the slope regime changed | quote the value; note the kink |
| `path=recorded` | the recorded path's value, labelled RECORDED-PATH | for comparison only, never as the price |

## Replay on a tape read back from a file

This server loads every tape from its file. A tape read back keeps no operand for a counted active-to-passive
conversion (an `ibool` collapsed to a `bool`, a `float()` of an active value), so the engine cannot re-check such a
decision and reports it `UNCHECKED`; every output downstream is withheld. Most QuantLib pricings carry at least one
(the error function chooses a series at `errorfunction.cpp:200`), so on a loaded QuantLib tape a `replay` is usually
withheld even for a small move. The same replay on the tape still in the recording process is exact. Measured on
aadc 2.25.2: the bundled `european_greeks` at spot 101 replays to 7.6404151728880825 in memory and is withheld after
save and load, naming `errorfunction.cpp:200`.

What the server offers in that case: `path_recorded=true` returns the recorded path's value labelled RECORDED-PATH,
which equals a fresh price only when no decision actually flipped. Say that it is the recorded path's value, and
re-run the script at the new inputs for the price.

## Two kinds of tape

**Auto-traced** (`trace_script` on an unmodified script, `AADC_TRACE=1`). Every value the script created is a
constant leaf inside the library (a spot of 100 appears at the QuantLib lines that read it, not at the script), and
every leaf is settable. Replays that move such a value must set every copy, and a constant *derived* from it before
it entered the record does not move at all: on the bundled `european_option`, the volatility 0.2 is one leaf at
`simplequote.hpp:69` and its square, 0.04, is a separate leaf at `blackvoltermstructure.hpp:263`; setting the first
to 0.202 leaves the price at 7.1280646692617395, while a fresh run at 0.202 prices 7.207851149315401 (measured
2026-10-22, in the recording process, so not a loading effect). A counted conversion in the path is UNCHECKED and the
replay is withheld. This tape is a code-flow instrument: use it to find constants, decisions and origins; for a
what-if on a script input, record explicitly with that input marked.

**Explicitly recorded** (`start_recording(trace=True, trace_inputs_as_random=False)`, inputs marked with
`mark_as_input()`, `save_tape()` at the end; see `european_greeks`). Each marked input is one leaf, replays move it in
one assignment, and the recorded workspace gives exact first-order sensitivities. Use it for what-ifs and Greeks.

## Measured on the bundled `european_option` (aadc 2.25.2, aadc-quantlib-tracing 1.41.1, 2026-10-21)

`stats`: 685 entries, 613 attributed (89%), 268 sites in 29 files, 71 constant leaves, 38 frozen-branch sites.
`branches order=margin`: the closest decisions sit in `comparison.hpp:71` (margin 0), `errorfunction.cpp:210` (0.0043)
and `blackcalculator.cpp:77` (0.2). `find value=<NPV>` returns six exact matches, one of them `sink, marked OUTPUT`.
Each verb answered in under a millisecond on this tape.

Re-measured 2026-10-22 on `aadc-quantlib-tracing` 1.41.4 (the first release with macOS arm64 wheels), installed from
PyPI into a fresh environment: the same NPV (7.1280646692617395), the same 685 entries, 613 attributed, 268 sites, 71
constants and 38 frozen sites, the same nearest decisions; the loaded-tape replay above is still withheld at
`errorfunction.cpp:200`.
