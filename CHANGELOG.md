# Changelog

## 0.1.2 (2026-10-23)

- MatLogica named in the PyPI summary, the server title a client shows, the README's first line, `--help` and the
  instructions the agent reads.

## 0.1.1 (2026-10-23)

- Console script answers a person: `aadc-mcp --help`, `--version`, `--check`; the bare command on a terminal prints
  the help and exits instead of waiting silently.
- The empty `test` extra removed (tests are not shipped); author, homepage, keywords and classifiers on PyPI.
- README and get-started: Intel Macs are not supported (the engine has no wheel for them); run `aadc-mcp --check`
  first.

## 0.1.0 (2026-10-23)

- First release. Tools: check_environment, trace_script, inspect_tape, replay, set_source_root, load_tape,
  list_tapes, list_examples, get_example, run_example. Resources: the AADC how-to and the Tracer how-to (every
  snippet executed by the tests), the agent guide and release notes from the installed engine, the verbs reference,
  get-started, the package and platform matrix, the tracing documentation. Prompts: get_started, validate_pricer,
  add_sensitivities. Six bundled examples. Requires aadc 2.25.2 or later; the `quantlib` extra installs
  aadc-quantlib-tracing 1.41.4 or later on Linux x86-64 and macOS arm64.
