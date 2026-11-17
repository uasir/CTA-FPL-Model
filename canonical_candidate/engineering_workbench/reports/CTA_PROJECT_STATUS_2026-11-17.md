# CTA-FPL-Model engineering status — 2026-11-17

Repository: `uasir/CTA-FPL-Model`
Branch: `main`
Current operating mode: GitHub Actions + recovered source files; no Replit dependency.

## Verified Python–JavaScript parity

Latest successful run: [GitHub Actions run 44091783751](https://github.com/uasir/CTA-FPL-Model/actions/runs/44091783751)

- Registered parity contract: `1.1.0`
- Matches: **34/34 PASS**
- Registered feature comparisons: **141,468/141,468 within tolerance**
  - Sequences: 113,373
  - Players: 21,567 (includes StatsBomb player-name metadata)
  - xT grid: 6,528
- The output artifact is named `cta-independent-multimatch-44091783751`.

## StatsBomb player identity corrected to provider ID

The core previously aggregated player counters by display name. That was unsafe because two distinct StatsBomb players can share a name, and the output discarded the provider's numeric ID needed by the FPL crosswalk.

Updated both Python and JavaScript cores to:
- Key player feature rows by `statsbomb_player_id`.
- Retain `statsbomb_player_name` as display metadata, not identity.
- Attribute pass recipients by recipient ID.
- Reject named player objects that lack a StatsBomb ID, and reject conflicting names for one ID.
- Keep FPL names and minutes blank until a verified ID crosswalk and temporally aligned minutes source are supplied.

Parity contract is now **1.1.0** and the core version is **1.0.3-experimental**. The latest 34-match run [44091783751](https://github.com/uasir/CTA-FPL-Model/actions/runs/44091783751) passed:
- 34/34 matches.
- 113,373 sequence comparisons.
- 21,567 player comparisons (including the player-name metadata field).
- 6,528 xT-grid comparisons.
- **141,468/141,468 total comparisons within tolerance.**

The new ID-based enrichment adapter `scripts/enrich_player_features.py` and synthetic tests are added. It requires a verified crosswalk, matching season and competition, and an official FPL element/code match. It does not use names as join keys and explicitly refuses to use season-total FPL minutes as the denominator for a single-match StatsBomb per-90 calculation. The adapter tests passed in the current FPL workflow test stage; the real join remains not ready because the crosswalk is empty.

## Latest multi-match parity and 360 anomaly diagnosis

The registry-backed parity workflow completed successfully in [latest run 44091783751](https://github.com/uasir/CTA-FPL-Model/actions/runs/44091783751):
- Contract version 1.1.0; **34/34 matches PASS**.
- Registered comparisons: **141,468/141,468 within tolerance** (113,373 sequence, 21,567 player, 6,528 xT-grid feature comparisons).
- Python core tests, workbench tests, both engines, parity audit, data-quality audit, and the cross-match 360 UUID diagnostic all completed successfully.

The new cross-match UUID diagnostic scanned the anomalous 360 file against all 34 sampled event files:
- 3,548 unique frame UUIDs.
- 4,026 event UUIDs in target match 3837706.
- Zero UUID overlap with target match and zero overlap with any other match in this 34-match sample.
- Status: `UNRESOLVED_NO_MATCH_IN_SAMPLE`.

This narrows the diagnosis but does not identify the frame file's true source. GitHub file history also shows the event JSON was last committed on 2023-12-13, while the 360 JSON was last committed on 2026-05-26. Those different publication histories are consistent with a source-version mismatch, but do not prove the 360 file's origin. Match 3837706's 360 file remains quarantined. Do not normalize IDs, relabel the match, or use those frames as valid coverage.

## Data-quality findings

Latest successful data-quality report from run 44091783751:

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

## FPL-only point-in-time feature dataset

The official API ingestion now feeds `scripts/build_fpl_lagged_features.py`. Successful builds: [run 44090651377](https://github.com/uasir/CTA-FPL-Model/actions/runs/44090651377), [run 44091776980](https://github.com/uasir/CTA-FPL-Model/actions/runs/44091776980), [run 44092340162](https://github.com/uasir/CTA-FPL-Model/actions/runs/44092340162), and [run 44092523819](https://github.com/uasir/CTA-FPL-Model/actions/runs/44092523819). The latest artifact records a UTC source snapshot time and SHA-256 hashes for the official bootstrap and fixtures feeds.

- 4,517 player-fixture rows.
- 459 players with positive season minutes.
- 100 completed fixtures across GW1–GW10.
- Every target row uses only earlier-gameweek history whose actual kickoff is strictly before that gameweek's FPL deadline.
- Postponed fixtures from an earlier gameweek are excluded if they were played after the target deadline.
- All fixtures in a double gameweek share one pre-deadline feature snapshot.
- Current/future gameweek outcomes are never used as predictors.

The builder now labels its result `PASS_STRUCTURAL_ONLY`. The latest run uses bootstrap `deadline_time` and actual fixture `kickoff_time` as a cutoff, excluding postponed prior-GW fixtures that occur after the target deadline. However, the current API snapshot may include retrospective revisions to prior gameweek statistics; fixture difficulty is labelled current-snapshot-only until its historical vintage is verified. The report therefore sets `point_in_time_status: NOT_VERIFIED`. Strict historical backtesting requires archived pre-deadline snapshots. This is a structurally lagged dataset, not a fully point-in-time-validated dataset, trained model, or predictive validation. It covers only active player history requested from the API; the full 672-player roster is retained separately in `fpl_players.csv`.

## FPL player-gameweek targets and exploratory baselines

The new `scripts/aggregate_fpl_gameweek_rows.py` aggregates fixture-level targets into the actual FPL prediction grain: one player-gameweek row, with points and minutes summed across all fixtures in that gameweek. Successful build: [run 44092741441](https://github.com/uasir/CTA-FPL-Model/actions/runs/44092741441).

- 4,517 player-gameweek rows.
- 459 players.
- GW1–GW10.
- All features are identical across fixtures for a player in the same GW; double-gameweek aggregation is covered by synthetic tests.
- The current 2026/27 snapshot has no double-gameweek target rows yet, so the aggregation test is the verification for that case.

An exploratory rolling-history baseline evaluation completed successfully in [run 44092943676](https://github.com/uasir/CTA-FPL-Model/actions/runs/44092943676). Results on the 2026/27 snapshot:

| Baseline | Rows evaluated | MAE | RMSE |
|---|---:|---:|---:|
| Previous GW points | 4,058 | 1.930 | 3.283 |
| Previous 3-GW average | 3,140 | 1.791 | 2.774 |
| Previous 5-GW average | 2,223 | **1.761** | **2.644** |

The 5-GW average is the strongest of these three simple references on this small sample. Gameweek Spearman correlations vary by week (roughly 0.42–0.57); top-decile overlap is variable. These figures are **exploratory only**, not a validated model benchmark: one season, ten gameweeks, current API snapshot, and no archived pre-deadline vintages. The artifact includes per-gameweek rank and top-decile metrics.

## Player identity crosswalk safeguards

Added:
- `canonical_candidate/data/player_identity_crosswalk.csv` — empty, season-scoped template.
- `canonical_candidate/engineering_workbench/scripts/validate_player_identity_crosswalk.py` — validator/exporter.
- `canonical_candidate/engineering_workbench/tests/test_player_identity_crosswalk.py` — regression tests.

Only rows marked `verified` with complete provider IDs, team/season context, a supported verification method, evidence URL/source, verifier, and verification date can be exported for joining. Pending, ambiguous, and rejected rows are excluded. Fuzzy-name matching is explicitly rejected. Duplicate/conflicting one-to-many identity mappings block the export.

The tests and empty-template validation passed in [run 44089706370](https://github.com/uasir/CTA-FPL-Model/actions/runs/44089706370). The latest cross-competition identity guardrail also passed in [run 44089832073](https://github.com/uasir/CTA-FPL-Model/actions/runs/44089832073). Its combined artifact confirms the crosswalk state is `EMPTY_NOT_READY` with `join_ready: false`, while the 2026/27 FPL ingestion remains PASS with zero minute/points reconciliation mismatches. The latest FPL artifact [run 44092741441](https://github.com/uasir/CTA-FPL-Model/actions/runs/44092741441) also confirms `EMPTY_NOT_READY` and `join_ready: false`. No player identities have been populated or guessed.

## Training-data season compatibility (verified source inventory)

The open-source provider inventory shows a hard temporal coverage gap:
- StatsBomb Open Data lists the English Premier League only for **2003/04 (season ID 44)** and **2015/16 (season ID 27)** in its current `competitions.json`.
- The Vaastav FPL historical archive's season folders begin at **2016/17**; it has no 2015/16 folder.
- The Vaastav repository's MIT license explicitly says the underlying FPL/Understat data belongs to those providers and is not owned by the repository author; the code license is not a data-use grant.
- The official FPL API snapshot now ingested by this project is **2026/27**, but StatsBomb Open Data has no 2026/27 Premier League event season.

Therefore there is **no overlapping Premier League season** between the public StatsBomb event data and the FPL historical archive. The existing 34-match sample contains six Premier League matches from 2015/16, but cannot be given gameweek FPL targets from that archive. The 2003/04 StatsBomb season is even further outside FPL archive coverage. A verified player-name crosswalk alone cannot solve this missing season overlap.

Sources:
- Vaastav FPL archive license/data ownership notice: https://github.com/vaastav/Fantasy-Premier-League/blob/master/LICENSE
- StatsBomb Open Data competitions index: https://github.com/statsbomb/open-data/blob/master/data/competitions.json
- StatsBomb Open Data repository and data structure: https://github.com/hudl/open-data
- FPL historical archive and season structure: https://github.com/vaastav/Fantasy-Premier-League

**Decision:** keep the current parity sample as an engineering benchmark only. Do not assume the Vaastav repository's code MIT license grants rights to its FPL/Understat data. For actual event-derived FPL prediction, obtain a licensed/authorized event feed and FPL targets for an overlapping season, or obtain a historically aligned StatsBomb+FPL dataset with documented provenance and permitted use. Do not fabricate labels, extrapolate current FPL IDs backwards, or join by name alone.

## Historical event-source alternative: Wyscout 2017/18

A new source audit is recorded in [WYSCOUNT_FPL_SOURCE_AUDIT_2026-11-17.md](WYSCOUNT_FPL_SOURCE_AUDIT_2026-11-17.md).

The official Pappalardo–Massucco Wyscout Figshare collection publishes a 2017/18 English Premier League event season: 380 matches, 643,150 events, and 603 players. The Events, Matches, Players, Teams, and Competitions items display CC BY 4.0 licenses. The schema includes provider player/team/match IDs, event times and positions, and match lineups. This is a real season overlap with the 2017/18 FPL archive, unlike the current StatsBomb Open Data sample.

A candidate-only name screen found 303 exact normalized full-name matches among 442 Wyscout player records whose currentTeamId maps to an EPL club. These are not verified identities. The Wyscout mirror's player metadata count (3,603) also differs from the paper's 4,299 total-player count, and the 442 current-team filter is not the published 603-player EPL season count; reconcile the official Figshare files and match-level appearances before ingestion.

The 2017/18 Vaastav FPL archive contains 647 players and all 38 gameweek folders, but its LICENSE says the data belongs to Fantasy Premier League and Understat; the MIT license is for the repository software, not a data-use grant. The historical target-data rights and pre-deadline snapshot vintage remain unresolved. No Wyscout data has been fully ingested and no identity has been promoted to the verified crosswalk.

**Decision:** Wyscout is the strongest historical event-side candidate found so far, but do not integrate it into production until an authorized historical FPL target source is supplied and the Wyscout player/match counts are reconciled. Keep its IDs and features in a separate provider namespace from StatsBomb.

## Alternative current-season provider candidate: Opta/PulseLive

A separate structural audit is recorded in [OPTA_PULSE_FPL_SOURCE_AUDIT_2026-11-17.md](OPTA_PULSE_FPL_SOURCE_AUDIT_2026-11-17.md).

At pinned source commit `f0f3d40f803c69bc7fac48d0748b49175e2d08ce`, the third-party `imadeddine-belkat/Premier-League-Stats` repository's 2026/27 snapshot has:
- 511/511 PL/PulseLive player IDs numerically shared with FPL `player_code`.
- 511/511 shared player IDs with matching team IDs.
- 100/100 PL/PulseLive team-match IDs shared with FPL fixture codes; exactly two team rows per match.
- Player-season aggregates and team-match event aggregates, but no actual player-match output files in the inspected tree despite the README describing them.

This could support a separate Opta/PulseLive provider adapter and leakage-safe lagged team features, but it does not replace StatsBomb. The repository has no visible LICENSE file and GitHub metadata reports no recognized license despite an MIT badge; underlying PL/PulseLive data rights remain unresolved. Do not make it a production dependency or redistribute it until rights are confirmed.

## Next actions

1. Inspect the completed exploratory baseline report from run 44092943676; treat its metrics as provisional because source vintages are not point-in-time verified.
2. Resolve the Opta/PulseLive data-rights question before integrating that source.
3. If cleared, build an isolated Opta/PulseLive adapter using verified numeric player/fixture IDs and leakage-safe lagged team features; do not merge it into the StatsBomb provider.
4. Otherwise obtain an authorized event feed for an FPL-covered season or another aligned historical dataset.
5. Populate the StatsBomb↔FPL crosswalk only from verified source evidence, never fuzzy-name guesses.
6. Run time-ordered, out-of-sample FPL points backtests only after point-in-time features and aligned outcomes exist.
7. Keep xT exploratory until calibrated and independently validated.

## Engineering guardrails

- Preserve the recovered original Python and JavaScript sources.
- Never invent FPL player aliases or minutes.
- Never treat Python–JavaScript parity as proof of predictive validity.
- Never treat missing 360 source as zero defensive activity.
- Preserve all workflow artifacts and input hashes needed to reproduce a result.
