# Opta/PulseLive team-context temporal evaluation — 2026-11-18

## Verified run

- Full official FPL ingestion + Opta evaluation: https://github.com/uasir/CTA-FPL-Model/actions/runs/44353308393
- Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44353308393/artifacts/14449347197
- Artifact digest: `sha256:540aa3d7e0b835a5d55a8a873d9e802a86f4c8a03bc7b6c43380162498b04b6a`
- Code revision: `45ac819064bb601cc2cd57098fffd0eac7e5c78d`; evaluation source commit for Opta/PulseLive: `f0f3d40f803c69bc7fac48d0748b49175e2d08ce`.
- FPL season: 2026/27; target forecast: GW11; source capture 2026-11-18 16:59:30 UTC; next deadline 2026-11-21 11:00 UTC (66.008 hours after capture).

## Integration coverage

- Official FPL ingestion: 672/672 player-summary requests succeeded; 380 fixtures; 6,562 player-fixture rows; zero orphan fixtures, minute mismatches, points mismatches, or missing player summaries.
- Opta identity: 511/511 exact `playerId = FPL code` joins and 511/511 provider `team_id = FPL team code` checks; zero duplicates or mismatches. 161 FPL players have no provider player-season row.
- Provider match reconciliation: 100/100 match IDs matched FPL fixture codes; 200 team-match rows formed 100 two-team matches; zero unknown team codes.
- Historical sidecar: all 6,562 FPL player-fixture rows joined to the correct team-at-fixture context; zero missing rows.
- Team context uses only the previous maximum three same-season provider matches, strictly before target kickoff. Provider naive kickoff times are interpreted as Europe/London; target match IDs are explicitly excluded.
- Historical point-in-time status remains `NOT_VERIFIED` because the provider source is a current cumulative snapshot, not a sequence of archived deadline vintages.

## Paired temporal holdout

Training: GW1–GW6 (3,216 player-fixture rows; GW1 is excluded from model fitting when no prior FPL history exists).  
Validation: GW7–GW10 (2,679 player-gameweek rows).

| Model | MAE | RMSE |
|---|---:|---:|
| Player-form ridge baseline | 1.201603 | 2.015697 |
| Player-form + 11 Opta team-context features | 1.229909 | 2.022270 |
| Naive last-five-GW points baseline | 1.185511 | 2.151323 |

The augmented model was worse than the player-form ridge baseline by **+0.028306 MAE** and **+0.006573 RMSE**. It also did not beat the naive last-five-GW MAE. The result does not support adding these Opta team-context features to the points model.

<badge>DO NOT PROMOTE</badge>

No feature selection or tuning was performed against the holdout. This is one season, one four-gameweek temporal holdout, and provider historical vintage is not verified. Treat it as a negative exploratory result, not proof that team context can never help.

## Recommendation engine status

- General-market Python/JavaScript parity: PASS across all 672 player forecasts.
- Personal-squad Python/JavaScript parity: PASS on the same 672-player pool, with a synthetic legal 15-player squad and 2,914 transfer candidates. This is a scale/parity check, not a manager recommendation.
- Both engines remain `EXPLORATORY_ONLY`; the source snapshot was 66 hours before deadline, EO coverage was zero, and CoVar was not used.
- Opta team-context features are not attached to forecast points, do not change rankings, and are not connected to either recommendation engine.
- FPL ridge model remains `DO_NOT_PROMOTE`; minutes predictions are materially weaker than the naive last-gameweek minutes baseline.

## Decision

Keep the adapter as a validated data-quality and research sidecar, but **do not use the current Opta team-context features in player scoring or squad decisions**. The next useful model step is better player-level, deadline-vintage FPL features and longer rolling-origin validation, not increasing the feature count with these team aggregates.

The Actions artifact contains only the official FPL run outputs and an aggregate Opta evaluation summary with hashes. The raw provider files, verified crosswalk rows, and 6,562-row Opta sidecar were not uploaded or committed.
