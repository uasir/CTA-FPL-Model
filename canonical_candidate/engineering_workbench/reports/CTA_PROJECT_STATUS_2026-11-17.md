# CTA-FPL-Model engineering status — 2026-11-17

Repository: `uasir/CTA-FPL-Model`
Branch: `main`
Current operating mode: GitHub Actions + recovered source files; no Replit dependency.

## Verified Python–JavaScript parity

Latest successful run: [GitHub Actions run 44087292634](https://github.com/uasir/CTA-FPL-Model/actions/runs/44087292634)

- Registered parity contract: `1.0.0`
- Matches: **34/34 PASS**
- Registered feature comparisons: **140,441/140,441 within tolerance**
  - Sequences: 113,373
  - Players: 20,540
  - xT grid: 6,528
- Exact matches: 140,439; two six-decimal xG comparisons are within the contract tolerance.
- The tolerance-boundary fix adds only a 1e-12 comparison slack for non-zero absolute tolerances. It does not change feature values or the contract's substantive tolerance.
- The output artifact is named `cta-independent-multimatch-44087292634`.

## Data-quality findings

Latest successful data-quality report from run 44087292634:

- 125,719 events
- 5,967 possession sequences
- 1,027 player rows
- 6,528 xT grid cells; all finite and within [0, 1]
- FPL names populated: **0/1,027**
- Positive trusted minutes: **0/1,027**
- Per-90 rows populated: **0**
- Model validation status: **not validated for FPL prediction** in all 34 matches
- FPL readiness: **BLOCKED**

360 linkage:
- 22 matches have usable event-UUID joins.
- 11 matches have no 360 source.
- Match `3837706` has a zero-join anomaly.
- Its raw event and 360 files are preserved in the workflow artifact under `diagnostics/3837706/`.
- Direct inspection: 4,026 event IDs, 3,548 frame UUIDs, zero shared UUIDs. Do not normalize or fuzzy-match these IDs; exclude this match's 360 data until source provenance is explained.

## Sample scope limitation for FPL modelling

The 34-match parity sample is intentionally cross-competition, not an FPL training set.

The six Premier League matches are all from 2015/16:
- 3754075 — Aston Villa vs Chelsea
- 3754078 — Chelsea vs Swansea City
- 3754159 — Manchester United vs Bournemouth
- 3754162 — Bournemouth vs Manchester United
- 3754335 — Norwich City vs Leicester City
- 3754348 — Norwich City vs Liverpool

The other 28 matches are from non-Premier-League competitions. The commonly used public FPL gameweek archive begins at 2016/17, so it does not directly supply gameweek-level FPL targets for these 2015/16 matches. Do not join current-season FPL players or targets to this historical sample.

## Official FPL ingestion

Added:
- `canonical_candidate/engineering_workbench/scripts/fetch_fpl_official_api.py`
- `canonical_candidate/engineering_workbench/tests/test_fpl_ingestion.py`
- `.github/workflows/cta-fpl-ingestion.yml`

The ingestion design fetches official `bootstrap-static`, `fixtures`, and per-player `element-summary` histories. It writes season-scoped player identities, fixtures, player-fixture minutes/points, source hashes, and an integrity report to a workflow artifact. It intentionally does not fuzzy-join StatsBomb identities.

The first complete official API snapshot is available from [run 44087962763](https://github.com/uasir/CTA-FPL-Model/actions/runs/44087962763):
- Season: **2026-27**
- Players: 672; players with positive minutes: 459
- Fixtures: 380
- Player-fixture history rows: 4,517 across 100 played fixtures (GW1–GW10)
- Per-player summary fetches: 459/459; zero fetch errors
- Missing summaries for players with minutes: none
- Orphan fixture references: none
- Unknown player references: none
- Independent reconciliation against the same `bootstrap-static` snapshot: **0 minute mismatches and 0 total-points mismatches** across all 459 players with minutes.

The ingestion tests passed in runs 44087933369 and 44087962763. A follow-up commit `a77952fae20d4f3f97ff2f9b20e479a7e242693c` adds automated season-total reconciliation (fixture-history minutes and points versus bootstrap totals), with regression tests. Its verification run is 44088405003 and was in progress when this document was updated. The run 44087962763 artifact is the verified source snapshot; its automated reconciliation fields are not present because it predates that follow-up commit.

## Next actions

1. Confirm one official FPL ingestion run completes and inspect its artifact, row counts, errors, and source hashes.
2. Verify run 44088405003 passes the newly automated per-fixture history minutes/points reconciliation.
3. Build a season-scoped identity crosswalk. Keep FPL element IDs, FPL player codes, StatsBomb player IDs, and names as distinct identifiers; require verified aliases plus team/season context.
4. Choose a training sample whose competition and season align with the FPL targets. The current 34-match sample remains a parity/engineering test only.
5. Only after trusted player minutes and aligned FPL outcomes exist, calculate per-90 features and run out-of-sample FPL points backtests.
6. Keep xT marked exploratory until calibrated and independently validated.

## Engineering guardrails

- Preserve the recovered original Python and JavaScript sources.
- Never invent FPL player aliases or minutes.
- Never treat Python–JavaScript parity as proof of predictive validity.
- Never treat missing 360 source as zero defensive activity.
- Preserve all workflow artifacts and input hashes needed to reproduce a result.
