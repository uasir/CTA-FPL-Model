# Opta/PulseLive to FPL live integration — 2026-11-18

## Verified execution

- Workflow run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44352173248
- Aggregate-only artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44352173248/artifacts/14448343224
- Artifact digest: `sha256:427e9ab6fb523cf7d899c9e251d0fdd13b9fad877deea5bdd81e822033792f8e`
- CTA commit under test: `40f5a8510b056319154e0c677f89b70690d7d732`
- Provider source commit: `f0f3d40f803c69bc7fac48d0748b49175e2d08ce`
- Captured at: 2026-11-18 16:52:13 UTC.

The workflow fetched official FPL `bootstrap-static` and `fixtures`, plus the pinned Opta/PulseLive player-season and team-match files. It generated the crosswalk and feature files inside the runner, validated them, and uploaded only a 1.5 KB aggregate summary. Raw provider data, the 511-row crosswalk, and player-fixture rows were not uploaded or committed.

## Identity reconciliation

| Check | Result |
|---|---:|
| Official FPL unique player codes | 672 |
| Opta/PulseLive unique player IDs | 511 |
| Exact shared numeric IDs | 511/511 |
| Exact team-code matches among shared IDs | 511/511 |
| Team mismatches / duplicate IDs | 0 |
| FPL players without provider player-season row | 161 |
| Provider player IDs without FPL code | 0 |
| Crosswalk validator | PASS — 511 verified rows |

The join key is exact `Opta/PulseLive playerId = FPL code`. Team validation compares provider `team_id` with the FPL team's `code`; it does **not** compare it with FPL's separate internal team `id`. The crosswalk stores both FPL team ID and FPL team code. No names or fuzzy matching are used to create the join.

## Fixture and team reconciliation

| Check | Result |
|---|---:|
| FPL fixtures | 380 |
| Team-fixture rows generated | 760 |
| Provider team-match rows | 200 |
| Provider match IDs | 100 |
| Provider match IDs found in FPL fixture `code` values | 100/100 |
| Provider matches with exactly two team rows | 100/100 |
| Unknown provider team codes | 0 |
| Fixtures without kickoff | 0 |

Provider `matchId` joins to FPL fixture `code`, not FPL fixture `id`. The provider's naive kickoff strings are interpreted as Europe/London and converted to UTC; FPL kickoff timestamps are UTC. This is necessary for a correct chronological join and is regression-tested.

## Prospective lagged team features

- 18,816 player-fixture rows were generated for unfinished fixtures strictly after the run's `as_of_time` (2026-11-18 16:52:13 UTC).
- Current FPL roster assignments are never projected backwards onto completed historical fixtures.
- Team features use the previous maximum three same-season provider team matches with kickoff strictly before the target fixture. The target provider match ID is explicitly excluded.
- Ten available team metrics were included: `expectedGoals`, `expectedAssists`, `accuratePass`, `possessionPercentage`, `finalThirdEntries`, `attemptsIbox`, `ballRecovery`, `interception`, `duelWon`, and `touches`.
- The output is structurally reconciled and leakage-guarded by event time, but `point_in_time_status = NOT_VERIFIED`. The provider file is a current-season cumulative snapshot, not a sequence of archived deadline vintages. It must not be used for strict historical backtests until vintage capture is established.
- These are team-context features, not player-level Opta match event features. The inspected repository snapshot does not contain player-level per-match event rows.

## Source provenance

| Source | SHA-256 |
|---|---|
| Official FPL bootstrap-static | `e8798ae1cf615ca5214e589ca1bed95bab753c01f9bd44954796016b3620fef4` |
| Official FPL fixtures | `ce30fce58d110a21c446420455f37f8b67c1c82c03ee2d8366cb990e0d78d0b5` |
| Opta/PulseLive player-season CSV | `00624b2ed48d0b0e43a4048e6605fd71128dec5107a430df3d0b559e456e8e36` |
| Opta/PulseLive team-match CSV | `4679d1b7839fc757ba84e14269f9d9caff2ef54666e79ef406f686869fbd5129` |

The source manifest is included in the aggregate Actions artifact.

## Validation and next steps

- Engineering CI run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44352156201
- JavaScript tests: 38 passed, 0 failed.
- Canonical Python unittest suite: 10 passed.
- Engineering pytest suite: 180 passed, 3 subtests passed.
- StatsBomb, Wyscout, and Opta/PulseLive crosswalk validators all passed.

This is a successful technical integration, not predictive validation. The Opta data repository advertises a MIT repository license, but the underlying Premier League/PulseLive data rights remain unverified. The source is not redistributed by this workflow. Team features remain disconnected from model scoring until point-in-time provenance and out-of-sample predictive value are established.

## Historical player-fixture evaluation follow-up

The adapter was integrated into the daily FPL ingestion pipeline and joined all 6,562 FPL lagged player-fixture rows to Opta team context. The paired GW1–6 / GW7–10 holdout is documented in `reports/OPTA_TEAM_CONTEXT_TEMPORAL_EVALUATION_2026-11-18.md` and full run 44353308393.

Adding 11 team-context features worsened the player-form ridge model (MAE 1.201603 → 1.229909; RMSE 2.015697 → 2.022270). The model remains `DO_NOT_PROMOTE`; the Opta sidecar is not connected to recommendation scoring. This negative result is retained rather than selecting features on the holdout.
