# Workbench parity assessment — match 3895320

**Status: PASS for supported Python core features under the canonical contract.**

The audit compares the original Python v1.0.2 core with the JavaScript reproduction on the same verified raw events and 360 files, keeping possession, one-match player aggregate, and xT grid-cell outputs separate.

- Events Git blob SHA-1: `2f4cc3c3f8173e923485db7e0c814980080ecdb4`
- 360 Git blob SHA-1: `80cd519d37fcea4681e38a3806b69ae9f9af9fa0`
- Results: 176/176 possession keys, 32/32 player keys, and 192/192 xT-cell keys matched.
- Supported features: 40/40 passed; zero unmatched keys, duplicates, null mismatches, or failures.
- Maximum absolute numeric error: `4.99600361081e-16`; mean absolute error across 962 non-null numeric pairs: `3.9238651598e-18`.

## Reports

- Feature results: `outputs/pilot_3895320/parity/parity_summary.md` and `.json`
- Per-grain reports: `outputs/pilot_3895320/parity/audit_sequences/`, `audit_players/`, `audit_xt_grid/`
- Contract: `engineering_workbench/docs/engineering/CTA_CORE_PARITY_CONTRACT.md`

## Scope limits

- FPL aliases, trusted player minutes/per-90, and 360 player-identity joins remain unsupported because validated inputs are unavailable.
- No multi-match validation, calibration, predictive performance, FPL points, EV, EO, or CoVar result is claimed.
- Original Python core source and original pilot output files were not changed; the Python reference run is separate.
