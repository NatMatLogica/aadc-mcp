# Packages, platforms and pins

Read from PyPI on 2026-10-22. `check_environment` reports what is actually installed here.

| package | what it is | import | platforms | current |
|---|---|---|---|---|
| `aadc` | the engine: record once, replay compiled, exact adjoints; `trace_inspect` from 2.25 | `import aadc` | Linux x86-64 and arm64, macOS arm64, Windows x86-64; CPython 3.10-3.14 | 2.25.2 |
| `aadc-quantlib` | QuantLib 1.38 with `Real` = the AADC active double: exact AAD sensitivities from the QuantLib API | `from aadc_quantlib import QuantLib as ql` | the same four platforms | 1.38.10 |
| `aadc-quantlib-tracing` | QuantLib 1.41 compiled through the source-tracing pass: every recorded constant and frozen branch attributed to its C++ line | `from aadc_quantlib_tracing import QuantLib as ql` | **Linux x86-64 and macOS arm64** (macOS from 1.41.4, 22 October 2026), CPython 3.10-3.14; no Windows or Linux arm64 wheel | 1.41.4 (a 1.38 line also exists) |
| `aadc-mcp` | this server | `aadc-mcp` (console script; `--check`, `--version`, `--help`) | wherever `aadc` runs | 0.1.2 |

Each instrumented library is its own distribution with its own import name, so it installs beside the ordinary build
and neither shadows the other. PyPI's own `QuantLib` package is a third, separate build and is never traced.

## Pins

The engine moves often. Pin what you measured:

```sh
pip install "aadc==2.25.2" "aadc-quantlib-tracing==1.41.4"
```

`aadc-quantlib-tracing` declares `aadc>=2.24,<3`; the verbs this server documents (`replay` verdicts, `branches`
margins, `find`, `cone`) need `aadc>=2.25.2`, which is what `aadc-mcp` requires.

## Two QuantLib lines

`aadc-quantlib` on PyPI wraps QuantLib 1.38 and `aadc-quantlib-tracing` wraps 1.41 (a 1.38 tracing line is also
published). The two builds price with different QuantLib versions; `check_environment` warns when both are installed.
Use one build per question.

## Licence

The `aadc` engine installs in Community Edition without a licence file: non-commercial and academic use. Commercial
use, and the features a licence enables, come from MatLogica (info@matlogica.com). `aadc.license_status()` reports the
state; `check_environment` includes it.
