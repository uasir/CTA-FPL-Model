# Workbench parity readiness — match 3895320

**Status: NOT RUN.** No parity result is claimed.

## Entry point and input contract

From `canonical_candidate/engineering_workbench`: `PYTHONPATH=src python -m cta_audit.audit --python <python_rows.csv> --javascript <javascript_rows.csv> --registry config/feature_registry.json --out reports/parity`. The auditor accepts CSV, JSON, or JSONL/NDJSON. Both runtimes must provide comparable feature rows keyed by the registry's `match_id,event_id`; feature types, nullability, and tolerances must match the registry.

The current registry is version 0.1.0 and registers `possession_id`, `pressure_count`, `support_distance_m`, and `has_360_frame`.

## Why the real pilot cannot be audited yet

- There is no JavaScript or TypeScript implementation in the imported candidate/workbench. The JavaScript CSV in `examples/` is synthetic smoke-test output only.
- No real pilot JavaScript output exists. The audit requires both real Python and JavaScript output tables from the same immutable inputs.
- The core CLI emits possession-level `sequences.csv` and player-level `player_features.csv`, not a matching event-keyed `match_id,event_id` feature table.
- The event and 360 contract files are marked `provider: UNCONFIRMED` and are templates for normalized flat fields, not validated mappings of the nested StatsBomb payloads.

These blockers must be resolved before parity can be meaningfully run. The synthetic examples were not used.
