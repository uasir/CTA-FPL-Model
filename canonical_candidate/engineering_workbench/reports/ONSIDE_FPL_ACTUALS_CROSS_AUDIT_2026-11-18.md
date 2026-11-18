# Onside actual-points cross-audit against official FPL — 2026-11-18

## Verified run

- Full FPL ingestion and cross-audit: https://github.com/uasir/CTA-FPL-Model/actions/runs/44357104115
- Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44357104115/artifacts/14452257166
- Onside source SHA-256: `dd51366a5f71d5f0bf26b4265b17188f04774d584c4444172be3f307aaf02a81`
- Retrieved: 2026-11-18 17:19:24 UTC.
- FPL season: 2026/27; gameweeks 1–10.

## Result

**PASS_EXACT_MATCH** for every overlapping player-gameweek row.

| Measure | Result |
|---|---:|
| Official FPL player-gameweek rows | 6,562 |
| Onside player-gameweek rows | 4,954 |
| Matched player-gameweek rows | 4,954 |
| Exact point matches | 4,954 |
| Mismatches | **0** |
| Exact match rate | **100%** |
| Mean absolute points difference | **0.000** |
| Maximum absolute points difference | **0.000** |
| FPL rows with no Onside counterpart | 1,608 |
| Onside rows with no FPL counterpart | **0** |
| Unique FPL players | 672 |
| Unique Onside players | 605 |
| Unique matched players | 605 |

All 10 gameweeks (GW1–GW10) had exact matches for every overlapping player-gameweek row. Double-gameweek FPL fixture rows were summed before comparison. Missing rows were counted separately and never filled with zero.

## Interpretation

This validates the Onside `actual_points` values against official FPL history for all 4,954 overlapping player-gameweek rows. It materially strengthens the provenance/accuracy case for using the Onside points panel as an exploratory CoVar input.

It does **not** mean Onside covers the entire FPL population: 1,608 official FPL player-gameweek rows have no Onside counterpart, and 605 of 672 players overlap. The existing covariance pipeline still uses complete-case panels and excludes zero-variance players.

It also does **not** resolve the CoVar stability problem. The earlier 10-GW split-window screen remains very weak (correlation-of-correlations 0.0078; median absolute correlation change 0.5004). The new rolling window uses up to 20 fully graded gameweeks, but more observations are needed before reassessment.

Historical source-vintage remains `NOT_VERIFIED`; exact retrospective points equality is not proof that every historical input was captured as it was known at the original deadline.

## Data handling

- The audit uses only numeric `(FPL element ID, gameweek)` joins.
- Duplicate official player-fixture rows and duplicate Onside player-gameweek rows are rejected.
- Non-finite points are rejected; missing rows are reported, not zero-filled.
- The Onside provider states CC BY 4.0; attribution to Onside Arena and its source page is recorded.
- Raw Onside rows and mismatch examples are not uploaded. The workflow publishes aggregate metrics, source hash and attribution only.
- The cross-audit does not feed expected points, CoVar, market rankings, transfer recommendations or personal-squad scoring.

## Decision

Retain the Onside source for exploratory covariance research with exact-point validation on the overlapping subset. Keep CoVar disabled in `personal_squad` until longer-window stability and out-of-sample evidence improve.

## Final integrated pipeline verification

A second full pipeline run included the audit in the published aggregate summary:

- Run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44357649202
- Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44357649202/artifacts/14451857683
- Artifact digest: `sha256:45b7d36cb2ea6806d1a10f9d18828bbfefcbb220102c32aa9f3733ae10b5f1e2`.

The aggregate artifact confirms `PASS_EXACT_MATCH`, 4,954/4,954 exact rows, zero mismatches, and includes the Onside source SHA and attribution. The same run also passed official FPL ingestion, Opta team/fixture reconciliation, the 6,562-row historical sidecar, general-market parity across 672 players, and personal-squad parity across the same pool using a synthetic 15-player roster (2,914 legal transfer candidates). CoVar was not used.
