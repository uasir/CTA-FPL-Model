# CTA-FPL Engineering Workbench

This local workbench is the GitHub-independent continuation of the CTA-FPL engineering project. It includes a reproducible Python–JavaScript feature-output parity harness, raw-data contract preflight, and an independent empirical xT baseline prototype.

## Requirements

- Python 3.10+
- Standard library only; no Data Analysis plugin or third-party package required.

## Run the tests

```bash
PYTHONPATH=src python -m unittest discover -s tests -v
```

## Run an audit

Export both runtimes' feature tables as CSV, JSON (`[{...}]` or `{"rows": [...]}`), or JSONL. Both files must use the same canonical key columns defined in `config/feature_registry.json`.

```bash
PYTHONPATH=src python -m cta_audit.audit \
  --python path/to/python_features.csv \
  --javascript path/to/javascript_features.csv \
  --registry config/feature_registry.json \
  --out reports/parity
```

Exit code 0 means parity passed; exit code 2 means the audit failed. Reports include JSON, Markdown, and input SHA-256 hashes.

## v1.0.2 core parity

Use `config/cta_core_parity_contract.json` for parity with the existing Python
core. It compares possession rows, one-match player aggregates, and xT grid
cells separately; it does not remap them to event keys. The contract marks
unmapped aliases, minutes/per-90 fields, and 360 player identities unsupported.

Run the JavaScript reproduction on the same raw files:

```bash
node src/js/run_pilot_parity.mjs \
  --events ../data/events/3895320.json \
  --three-sixty ../data/three-sixty/3895320.json \
  --direction-map ../data/direction_map.csv \
  --out ../outputs/pilot_3895320/parity/javascript
```

Then run `cta_audit.audit` once for each `--table sequences`, `--table players`,
and `--table xt_grid`, using the corresponding Python CSV, JavaScript JSON, and
`config/cta_core_parity_contract.json`. See
`docs/engineering/CTA_CORE_PARITY_CONTRACT.md` for exact commands and semantics.

Run JavaScript unit tests with:

```bash
node --test tests/js/*.test.mjs
```

## Important boundary

The example files are synthetic smoke-test data, not the pilot match or 34-match dataset. No project-level parity or predictive-performance claim can be made until the actual immutable match inputs and both runtime outputs are supplied.

## Raw-data preflight

The workbench now includes a configurable raw-data contract validator. The event and 360 JSON files under `config/` are **templates**, not confirmed provider schemas. Confirm field names, identifier semantics, timestamp format, coordinate system, and join cardinality against the actual source before treating a preflight pass as meaningful.

```bash
PYTHONPATH=src python -m cta_audit.contracts \
  --input path/to/events.jsonl \
  --contract config/event_contract.template.json \
  --dataset events \
  --out reports/preflight
```

Use `config/360_contract.template.json` for a separate 360 payload preflight after adapting it to the source payload. Event-to-frame association and orphan-frame accounting remain a distinct join-validation step; a basic row-schema pass does not establish join integrity.

## Independent xT baseline (engineering prototype)

A transparent empirical grid xT trainer is available as `cta_audit.xt`. It estimates cell value from empirical shot frequency/goal rate and successful pass/carry transitions. It intentionally has no smoothing or priors, so sparse cells remain zero. The supplied config is a template: coordinate scale/origin/orientation, action taxonomy, and outcome labels must be confirmed and mapped from the actual provider before real data is used.

```bash
PYTHONPATH=src python -m cta_audit.xt \
  --input path/to/canonical_actions.csv \
  --config config/xt_baseline.template.json \
  --out reports/xt
```

Fit the grid on training matches only and score held-out matches with that frozen grid. Do not train on the held-out match before evaluating it.


## Current validation status

- Original Python core tests: 7 passing.
- Workbench Python tests: 20 passing (17 original plus 3 parity regression tests).
- JavaScript core parity tests: 5 passing.
- Python–JavaScript synthetic parity smoke test: PASS (2 rows; 4 registered features).
- Synthetic event-contract preflight: PASS (2 rows).
- Synthetic xT prototype: converged (4 actions; 3 iterations).
- Real-data core parity: PASS on StatsBomb match 3895320 (40/40 supported features; 176 possession rows, 32 player rows, 192 xT cells; no unmatched keys).
- 34-match validation: NOT RUN.
