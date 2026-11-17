# CTA-FPL v1.0.2 Core Parity Contract

This contract compares equivalent outputs from the existing Python core and a
JavaScript reproduction. It does not change the Python calculations or turn
every output into an event-level row.

## Entity grains

The core emits three distinct entities, and each is compared separately:

| Table | Grain | Key |
| --- | --- | --- |
| `sequences` | One possession for one match, period, possession ID, and team | `match_id, period, possession_id, team` |
| `players` | One player across the exact one-match run | `statsbomb_player_name` |
| `xt_grid` | One cell in the match-fitted 16×12 xT grid | `x_cell, y_cell` |

The player key is valid only for a single-match run because the existing Python
player table aggregates over the full input set and has no `match_id` column.
Do not compare it against per-match JS rows or pool multiple matches under this
contract. Event-level keys are not substituted for possession or player keys.

The machine-readable source of truth is
`config/cta_core_parity_contract.json`. The Workbench auditor selects one table
from that contract with `--table sequences`, `--table players`, or
`--table xt_grid`.

## Input contract and directions

Inputs are the verified StatsBomb Open Data JSON arrays for match `3895320`.
Event IDs are unique; event type is read from `type.name`; possession grouping
uses `possession`, `period`, and `possession_team.name` (falling back to
`team.name`). Missing event locations remain missing and are not synthesized.

The 360 file joins through `event_uuid`. The core only audits these links; it
does not use visible-player coordinates in the CTA feature calculations. The
JavaScript side preserves 360 coordinates as received, including values outside
the nominal pitch rectangle. It does not clip them or use them as event
locations.

The direction CSV may contain explicit overrides. If a key is absent, both
implementations follow the Python core's documented StatsBomb convention and
use `attacks_right=true`, because coordinates are already possession-oriented
toward x=120. Any false override is rejected. Each run reports explicit and
generated key counts so the fallback is visible.

## Feature equivalence, nulls, and tolerances

Every supported field has the same canonical feature name in both outputs.
Definitions, units, nullability, source columns, and aggregation semantics are
recorded per feature in the JSON contract.

- Integer counts, identifiers, booleans, and categories compare exactly.
- Counter-backed player counts and reference-only shot xG are emitted as numeric zero in both implementations when no observations exist.
- Mean action xT and per-90 metrics remain null/blank when their denominators are unavailable.
- Null is distinct from zero. The audit must fail if one side emits null and
  the other emits zero.
- Numeric tolerances are explicit: exact, 1e-7 relative / 1e-9 absolute for
  unrounded float accumulation, 1e-6 absolute for six-decimal fields, and
  1e-8 absolute for eight-decimal grid cells.
- Rule-based `sequence_class` is compared as code output, not claimed as a
  human-validated danger label.

FPL aliases, minutes, per-90 values, and 360 player-identity joins are marked
unsupported because their source mappings are empty or absent. They are not
imputed into parity outputs. The Python CLI's `0.0` minutes fallback is
explicitly excluded.

## Running the comparison

From `canonical_candidate/engineering_workbench`:

```bash
PYTHONPATH=src python -m cta_audit.audit \
  --python ../outputs/pilot_3895320/parity/python_reference/sequences.csv \
  --javascript ../outputs/pilot_3895320/parity/javascript/sequences.json \
  --registry config/cta_core_parity_contract.json \
  --table sequences \
  --out ../outputs/pilot_3895320/parity/audit_sequences
```

Repeat with the `players` and `xt_grid` tables and their matching outputs.
Parity passes only when each table has identical key sets, no duplicate or null
keys, no missing or extra registered fields, no nullability mismatch, and all
numeric values meet their declared tolerances.

Passing this contract establishes implementation parity only. It does not
establish calibration, prediction, FPL usefulness, or causal validity.
