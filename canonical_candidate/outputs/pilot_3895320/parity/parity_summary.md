# Real pilot Python–JavaScript parity: match 3895320

**Status: PASS** — 40/40 supported features passed under the explicit contract.

## Entity-grain results

| Grain | Python rows | JavaScript rows | Shared keys | Unmatched keys | Features | Result |
|---|---:|---:|---:|---:|---:|---|
| sequences (possession) | 176 | 176 | 176 | 0 | 19/19 | PASS |
| players (player) | 32 | 32 | 32 | 0 | 20/20 | PASS |
| xt_grid (xT grid cell) | 192 | 192 | 192 | 0 | 1/1 | PASS |

## Feature-by-feature results

Absolute error metrics use non-null numeric pairs. `—` indicates exact comparison of an identifier, category, boolean, or integer.

| Grain | Feature | Compared | Exact | Within tolerance | Null mismatches | Max abs. error | Mean abs. error | Result |
|---|---|---:|---:|---:|---:|---:|---:|---|
| sequences | sequence_id | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | event_count | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | duration_seconds | 176 | 176 | 176 | 0 | 0 | 0 | PASS |
| sequences | players | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | passes | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | completed_passes | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | carries | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | receipts | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | pressured_events | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | pressured_receipts | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | box_entries | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | final_third_entries | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | progressive_actions | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | shot_count | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | shot_xg_reference_only | 176 | 176 | 176 | 0 | 0 | 0 | PASS |
| sequences | mean_action_xt_gain | 176 | 176 | 176 | 0 | 0 | 0 | PASS |
| sequences | positive_action_xt_gain_sum | 176 | 176 | 176 | 0 | 0 | 0 | PASS |
| sequences | direction_available | 176 | 176 | 176 | 0 | — | — | PASS |
| sequences | sequence_class | 176 | 176 | 176 | 0 | — | — | PASS |
| players | event_involvements | 32 | 32 | 32 | 0 | — | — | PASS |
| players | passes | 32 | 32 | 32 | 0 | — | — | PASS |
| players | completed_passes | 32 | 32 | 32 | 0 | — | — | PASS |
| players | pressured_events | 32 | 32 | 32 | 0 | — | — | PASS |
| players | box_entries | 32 | 32 | 32 | 0 | — | — | PASS |
| players | final_third_entries | 32 | 32 | 32 | 0 | — | — | PASS |
| players | progressive_actions | 32 | 32 | 32 | 0 | — | — | PASS |
| players | action_xt_gain_sum | 32 | 3 | 32 | 0 | 4.99600361081e-16 | 1.17961196366e-16 | PASS |
| players | action_xt_gain_n | 32 | 32 | 32 | 0 | — | — | PASS |
| players | passes_received | 32 | 32 | 32 | 0 | — | — | PASS |
| players | pressured_passes_received | 32 | 32 | 32 | 0 | — | — | PASS |
| players | receipts | 32 | 32 | 32 | 0 | — | — | PASS |
| players | carries | 32 | 32 | 32 | 0 | — | — | PASS |
| players | sequences_involved | 32 | 32 | 32 | 0 | — | — | PASS |
| players | shot_linked_sequences | 32 | 32 | 32 | 0 | — | — | PASS |
| players | non_shot_candidate_sequences | 32 | 32 | 32 | 0 | — | — | PASS |
| players | shots | 32 | 32 | 32 | 0 | — | — | PASS |
| players | shot_xg_reference_only | 32 | 32 | 32 | 0 | 0 | 0 | PASS |
| players | mean_action_xt_gain | 32 | 32 | 32 | 0 | 0 | 0 | PASS |
| players | pressured_receipts | 32 | 32 | 32 | 0 | — | — | PASS |
| xt_grid | xT | 192 | 192 | 192 | 0 | 0 | 0 | PASS |

## Numeric error summary

- Non-null numeric feature pairs: 962
- Maximum absolute error: `4.99600361081e-16`
- Mean absolute error: `3.9238651598e-18`
- Unmatched keys: 0 across all three entity grains.
- Failures: none.

## Input and validation notes

- Events Git blob SHA-1: `2f4cc3c3f8173e923485db7e0c814980080ecdb4`.
- 360 Git blob SHA-1: `80cd519d37fcea4681e38a3806b69ae9f9af9fa0`.
- Frame linkage: 3185/3185 frames matched; zero duplicate or unmatched frame UUIDs.
- Out-of-bounds 360 coordinates: 600 of 57482 visible-player locations; values preserved without clipping.
- No explicit direction rows; both implementations generated four true StatsBomb direction keys.
- Original Python core source and original pilot output files were not modified; the reference run is separate.
- Excluded: unverified FPL aliases, trusted minutes/per-90, calibration, prediction, EV, EO, and CoVar.

## Artifact locations

- Python reference: `outputs/pilot_3895320/parity/python_reference/`
- JavaScript reference and diagnostics: `outputs/pilot_3895320/parity/javascript/`
- Per-grain reports: `outputs/pilot_3895320/parity/audit_sequences/`, `audit_players/`, `audit_xt_grid/`
- Combined report: `outputs/pilot_3895320/parity/parity_summary.md` and `.json`
- Real-data fixture: `engineering_workbench/tests/fixtures/3895320/`

## Exact run commands

```bash
cd canonical_candidate && PYTHONDONTWRITEBYTECODE=1 python -B src/cta_engine.py --events-dir outputs/pilot_3895320/input_snapshot/events --three-sixty-dir outputs/pilot_3895320/input_snapshot/three-sixty --direction-map data/direction_map.csv --player-map data/player_id_map.csv --minutes data/player_minutes.csv --output-dir outputs/pilot_3895320/parity/python_reference
cd canonical_candidate/engineering_workbench && node src/js/run_pilot_parity.mjs --events ../data/events/3895320.json --three-sixty ../data/three-sixty/3895320.json --direction-map ../data/direction_map.csv --out ../outputs/pilot_3895320/parity/javascript
cd canonical_candidate/engineering_workbench && PYTHONPATH=src python -B -m cta_audit.audit --python ../outputs/pilot_3895320/parity/python_reference/sequences.csv --javascript ../outputs/pilot_3895320/parity/javascript/sequences.json --registry config/cta_core_parity_contract.json --table sequences --out ../outputs/pilot_3895320/parity/audit_sequences
cd canonical_candidate/engineering_workbench && PYTHONPATH=src python -B -m cta_audit.audit --python ../outputs/pilot_3895320/parity/python_reference/player_features.csv --javascript ../outputs/pilot_3895320/parity/javascript/players.json --registry config/cta_core_parity_contract.json --table players --out ../outputs/pilot_3895320/parity/audit_players
cd canonical_candidate/engineering_workbench && PYTHONPATH=src python -B -m cta_audit.audit --python ../outputs/pilot_3895320/parity/python_reference/xt_grid.csv --javascript ../outputs/pilot_3895320/parity/javascript/xt_grid.json --registry config/cta_core_parity_contract.json --table xt_grid --out ../outputs/pilot_3895320/parity/audit_xt_grid
```
