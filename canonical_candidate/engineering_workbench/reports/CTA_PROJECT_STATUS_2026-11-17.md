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

The ingestion tests and live API fetch both passed in run [44088405003](https://github.com/uasir/CTA-FPL-Model/actions/runs/44088405003). Its artifact contains the automated reconciliation fields: zero minute mismatches and zero total-points mismatches. The source snapshot is also retained in the artifact.

## Player identity crosswalk safeguards

Added:
- `canonical_candidate/data/player_identity_crosswalk.csv` — empty, season-scoped template.
- `canonical_candidate/engineering_workbench/scripts/validate_player_identity_crosswalk.py` — validator/exporter.
- `canonical_candidate/engineering_workbench/tests/test_player_identity_crosswalk.py` — regression tests.

Only rows marked `verified` with complete provider IDs, team/season context, a supported verification method, evidence URL/source, verifier, and verification date can be exported for joining. Pending, ambiguous, and rejected rows are excluded. Fuzzy-name matching is explicitly rejected. Duplicate/conflicting one-to-many identity mappings block the export.

The tests and empty-template validation passed in runs 44088979396 and 44088999247. The workflow's artifact path was subsequently corrected; run 44089097790 is the verification run for the final workflow YAML and combined artifact upload. It was in progress at the time of this update. No player identities have been populated or guessed yet.

## Next actions

1. Verify run 44089097790 completes with the corrected combined artifact upload.
2. Populate the crosswalk only from verified source evidence, never fuzzy-name guesses.
3. Acquire a StatsBomb Premier League sample whose season aligns with FPL player-fixture targets; the existing 34-match sample remains a parity/engineering test only.
4. Join match-level StatsBomb features to FPL player-fixture outcomes through the verified season-scoped crosswalk.
5. Only then calculate per-90 features and run time-ordered, out-of-sample FPL points backtests.
6. Keep xT exploratory until calibrated and independently validated.

## Engineering guardrails

- Preserve the recovered original Python and JavaScript sources.
- Never invent FPL player aliases or minutes.
- Never treat Python–JavaScript parity as proof of predictive validity.
- Never treat missing 360 source as zero defensive activity.
- Preserve all workflow artifacts and input hashes needed to reproduce a result.
