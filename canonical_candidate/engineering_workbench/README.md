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

The example files are synthetic smoke-test data, not the pilot match or 34-match dataset. A separate CI workflow now stages SHA-pinned StatsBomb inputs and compares both runtimes over 34 matches. Implementation parity does not establish predictive performance.

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

- Recovered original Python archive suites: scaffold 3/3, experimental 4/4, v1.0.1 5/5, v1.0.2 7/7, and original Workbench 17/17.
- Current GitHub main core tests: 7 passing; Workbench Python tests: 20 passing plus 3 subtests; JavaScript core tests: 5 passing.
- Real-data 34-match Python–JavaScript parity run (2026-11-17): 34/34 matches passed; 1,027 player rows, 5,967 sequence rows, and 6,528 xT cells compared.
- The initial run included 23 360 files. Twenty-two had complete frame-to-event joins; match 3837706 had 0/3,548 frame UUIDs matched and is excluded from usable 360 inputs in the reconciliation branch. Eleven matches have no 360 source.
- Reconciliation branch adds SHA/size verification, zero-filled count semantics in both runtimes, match-scoped 360 linkage, JavaScript regression tests, and a separate source-quality audit. Its remote CI rerun is pending.
- No calibrated CTA composite or FPL points predictor has been validated. Current-season FPL integration remains blocked by missing licensed current-season event coverage, trusted player minutes, and verified player-ID mappings.
