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


---

## Evening continuation update — 2026-11-17

This section supersedes the earlier "Next actions" where newer evidence is available.

### Original source recovery and regression checks

All five requested original archives were recovered from the Library, ZIP integrity-checked, extracted, and inspected. Their SHA-256 hashes are recorded here so the exact source inputs can be identified:

| Archive | SHA-256 | Original tests |
|---|---|---:|
| `CTA_FPL_reconstruction_scaffold_v0_1.zip` | `b96b6e3c3ef04b4e12d5d153f4f381843f4ecc2e48f0ae54d41d4ec14c1d6dc1` | 3 passed |
| `CTA-FPL-Engineering-Workbench.zip` | `b7e62bec4299a63fb06d72e7bc38f54f2726ea68f366a29b4e3f64607f6e4630` | 17 passed |
| `CTA_FPL_Model_v1_0_2_Engineering_Build.zip` | `7c8960ef250472eb2bb57b3d82f4ebec8dec00096482307470aedecb40cf5a73` | 7 passed |
| `CTA_FPL_Model_v1_0_1_Engineering_Fix.zip` | `2c000b3c3f84bf1197303013d0d21e402b01d8ebfbddef3aa6558cfc50ab7553` | 5 passed |
| `CTA_FPL_Model_v1_0_Experimental.zip` | `2d8278b593165b2bad7d55ee50969d166070e8872288a7fc59d07976ae17d749` | 4 passed |

All five ZIPs passed `ZipFile.testzip()`. The archived core lineage is Experimental → v1.0.1 fix → v1.0.2 engineering build; v1.0.2 is the latest complete original core archive. The reconstruction scaffold and engineering workbench are separate supporting projects, not replacements for that core. The workbench's 17 tests pass when its `src` directory is placed on `PYTHONPATH`; its initial default invocation failed collection because the package is not installed, not because the tests failed. The five archives therefore contribute 36 passing regression tests in total.

The current GitHub `canonical_candidate` is newer than those archives: it contains the ID-based Python/JavaScript 1.0.3-experimental implementation and parity contract 1.1.0. The latest multi-match CI run validates that newer implementation; the archived originals remain preserved as the recovery baseline. The supplemental `CTA_FPL_INDEPENDENT_WORKSPACE_2026-11-17.zip` was inspected separately and was not promoted over the recovered source lineage.

### Latest 34-match Python–JavaScript validation

Run [44091783751](https://github.com/uasir/CTA-FPL-Model/actions/runs/44091783751) completed successfully. Its artifact is `cta-independent-multimatch-44091783751` (ZIP SHA-256 `7d4c7d4a327fdcbb929f3e761981186f0ceb33aa54c7fb099ff24a202fb0748a`).

- 34/34 matches passed contract 1.1.0.
- 141,468/141,468 registered comparisons were within tolerance: 113,373 sequence, 21,567 player, and 6,528 xT-grid comparisons.
- Independent artifact re-check found no missing/extra keys or duplicate keys in any table. Player features and xT values matched exactly. Two sequence `shot_xg_reference_only` values differed by 1e-6, within the registered tolerance.
- Data-quality totals: 125,719 events, 5,967 sequences, 1,027 player rows, and 6,528 xT cells.
- The 360 audit remains 22 usable joins, 11 matches with no source, and one quarantined zero-join anomaly (3837706). Parity passing does not make that match's 360 frames valid.

### Official FPL ingestion and CoVar baseline

The next FPL workflow run, [44095250164](https://github.com/uasir/CTA-FPL-Model/actions/runs/44095250164), completed successfully on the commit that introduced the CoVar estimator. The FPL workflow's test stage reported **35 passed**. Its artifact is `cta-fpl-official-44095250164`, artifact ID `14333587219`, ZIP SHA-256 `4a6773d489f02441915661f79c470d06753c8f0a2622d5d99ff3b49bccbec73e`.

Official 2026/27 FPL ingestion:
- 672 player records, 380 fixtures, 4,517 player-fixture history rows, and 459 player-summary fetches.
- Zero summary-fetch errors, orphan fixtures, unknown player references, minute reconciliation mismatches, or total-points reconciliation mismatches.
- The lagged dataset contains 4,517 player-gameweek rows for 459 players across GW1–GW10 and is structurally valid.
- It remains `PASS_STRUCTURAL_ONLY` with `point_in_time_status: NOT_VERIFIED`: the current API snapshot can contain retrospective revisions. The verified StatsBomb–FPL crosswalk remains `EMPTY_NOT_READY`.

The new `estimate_fpl_covariance.py` creates an exploratory historical-points CoVar matrix using the latest ten completed gameweeks, complete-case players, and 50% diagonal shrinkage:
- 459 players appeared in the window; 421 had a complete ten-GW panel.
- One complete-panel player had zero variance and was excluded from the matrix; 38 players with incomplete windows were excluded rather than zero-filled.
- The matrix contains 420 players and 88,410 upper-triangle estimates (420 diagonal plus 87,990 off-diagonal pairs).
- Independent reconstruction from the archived player-GW data matched the exported matrix to 8 decimal places (maximum absolute difference 4.45e-9). The 420×420 matrix is exactly symmetric in the exported values, full rank, and positive definite; its minimum eigenvalue is 0.05.
- The report is correctly labelled `EXPLORATORY_ONLY`, `model_trained: false`, and `point_in_time_status: NOT_VERIFIED`. This is a descriptive covariance layer, not an EV model, EO model, or squad optimizer.

**Important CoVar stability result:** splitting the same ten-GW complete panel into GW1–GW5 and GW6–GW10 produced a covariance-pair Pearson correlation of 0.0017 and Spearman correlation of 0.0113 across 88,410 off-diagonal pairs. Covariance signs agreed only 34.2% of the time; overlap of the top 10% positive and negative pairs between halves was 16.6% and 17.9%. This shows that the matrix is mathematically well-conditioned after shrinkage but its player-pair estimates are not yet statistically stable. Do not use individual pair rankings or this matrix as a production squad-selection signal.

### EV and EO status

The rolling FPL baselines remain exploratory, not trained predictions. On the current ten-GW snapshot, the previous-five-GW average has MAE 1.761 and RMSE 2.644 over 2,223 rows; previous-three-GW average has MAE 1.791 and RMSE 2.774 over 3,140 rows; previous-GW points has MAE 1.930 and RMSE 3.283 over 4,058 rows. These are reference baselines only, with no point-in-time validation.

The current bootstrap includes `selected_by_percent` for the 672-player roster, but this is a current global ownership snapshot, not historical effective ownership (EO) among top-ranked managers. Historical EO still requires deadline-aligned manager-pick snapshots or another authorized source. No EV/EO/CoVar portfolio optimizer is complete.

### Durable-state and source blockers

- The official FPL workflow currently uploads artifacts with `retention-days: 30`. This is not a durable full-season point-in-time archive. A longer-lived, authorized snapshot store is still needed before strict historical backtests can be claimed.
- Wyscout 2017/18 is the strongest event-side historical candidate found: its official Figshare items display CC BY 4.0 and the EPL season overlaps 2017/18 FPL. However, the historical FPL target archive's data rights and point-in-time vintage remain unresolved; no Wyscout data or candidate name match has been promoted into production.
- The Replit workspace was not exported in this run. The verified source and execution path is the current GitHub `main` repository and its successful Actions runs; do not assume this proves byte-for-byte identity with the latest Replit workspace.

### Next engineering actions

1. Keep the ten-GW CoVar output exploratory. Add more completed gameweeks and run expanding/rolling-window stability checks before using player-pair covariance.
2. Develop a forecast-residual covariance layer or a regularized team/fixture factor model, then validate portfolio variance calibration out of sample. Do not mistake positive definiteness from diagonal shrinkage for statistical stability.
3. Build a time-ordered EV model only after point-in-time FPL snapshots are durably archived. Compare it against the existing rolling baselines.
4. Design EO from deadline-aligned top-manager picks; do not substitute current `selected_by_percent` for historical EO.
5. Resolve an authorized FPL target-data source for an overlapping Wyscout season, or another licensed event/target source. Keep provider IDs separate and verify all player/fixture mappings before joining CTA features.
6. Once EV, EO, and stable CoVar are available, implement the squad-level objective and evaluate against the user's aggressive top-100k strategy. Keep CoVar the primary risk-control dimension, but measure it against realized out-of-sample rank/points outcomes.


CI provenance cross-check: the current `main` tree has identical Git blob SHAs to multi-match commit `2ff12724060a9a411b8fe6aa01b416e1e031e56c` for the Python CTA core, JavaScript core, audit module, parity contract, ID-based enrichment adapter, and core tests. The later CoVar estimator and its tests are additional files and were exercised by FPL workflow run [44095250164](https://github.com/uasir/CTA-FPL-Model/actions/runs/44095250164). Thus the successful multi-match parity result applies to the current main core, while the CoVar tests/results apply to the added FPL risk layer.

## Minutes-baseline evaluation extension — evening continuation

The exploratory evaluator now reports a separate minutes-target baseline suite alongside the existing points baselines. It compares:
- Previous gameweek minutes (`prior_gw_minutes`) against `target_minutes`.
- Previous-three-gameweek average minutes against `target_minutes`.
- Previous-five-gameweek average minutes against `target_minutes`.

Each minutes baseline reports sample size, MAE, RMSE, mean error, per-gameweek Spearman rank correlation, and top-decile overlap. The minutes target is evaluated independently from points; minutes predictions are not converted into points or treated as a trained appearance-probability model.

Regression coverage verifies the minutes target is used, checks exact synthetic MAE values, and respects the required history length. The latest workflow run is [44145697223](https://github.com/uasir/CTA-FPL-Model/actions/runs/44145697223): its test step has passed; the live official FPL fetch and downstream artifact build were still running at the time of this report update.

Code commits:
- Evaluator and JSON report: `dce53e8f459a81443f3f677d249fedc53e846cbe`.
- Minutes regression tests: `2b35cbc7aa54029dc282f353a48965dbff89fdfc`.
- Markdown minutes report output: `5ba0acd5868f6753533cb65d67a7298561a815f9`.

An initial synthetic test correctly exposed a fixture setup issue: five-GW baseline rows had only three prior gameweeks and were therefore excluded. The test fixture was corrected to five prior gameweeks; the current workflow test stage passes. No production forecast claim is made.
## Blocker-resolution continuation — expanded ownership and EO layer

### Full-roster official FPL history

Successful expanded ingestion: [run 44147222576](https://github.com/uasir/CTA-FPL-Model/actions/runs/44147222576), artifact `cta-fpl-official-44147222576`.

- All 672 rostered players were fetched through `element-summary`, not only the 459 with positive minutes.
- 672/672 summary requests succeeded; 672 players had history records.
- 6,562 player-fixture rows across 100 completed fixtures and GW1–GW10.
- Zero summary errors, orphan fixtures, unknown player IDs, minute mismatches, or total-points mismatches.
- 6,562 player-gameweek rows and 672 player IDs were retained in the expanded dataset.
- Historical `selected` counts are now preserved with transfers balance/in/out and value.
- `bootstrap-static.events[].ranked_count` is used as the denominator to calculate historical global ownership percentage.
- 5,890 player-gameweek rows have a prior-gameweek global ownership percentage. GW1 correctly has no prior-GW ownership feature; later missing rows are players without that history.

These ownership features are not rank-tier effective ownership. The latest current-snapshot dataset remains `point_in_time_status: NOT_VERIFIED`, because the official API may revise past history after the fact.

### Updated exploratory baselines on the full player universe

Adding the previously missing 213 players changed the baseline sample and error metrics. The new figures supersede the earlier 459-player-only baselines:

| Points baseline | Rows | MAE | RMSE |
|---|---:|---:|---:|
| Previous GW | 5,890 | 1.330 | 2.725 |
| Previous 3 GWs | 4,551 | 1.236 | 2.304 |
| Previous 5 GWs | 3,216 | **1.218** | **2.199** |

| Minutes baseline | Rows | MAE (minutes) | RMSE (minutes) |
|---|---:|---:|---:|
| Previous GW | 5,890 | **10.645** | 23.701 |
| Previous 3 GWs | 4,551 | 12.540 | 24.175 |
| Previous 5 GWs | 3,216 | 14.082 | 25.414 |

The previous-five-GW average remains the best of these simple points references, while previous-GW minutes is the strongest of the three simple minutes references. These are still exploratory current-snapshot metrics, not validated forecasts.

### Effective ownership adapter

Added `scripts/estimate_fpl_effective_ownership.py` and `tests/test_fpl_effective_ownership.py`. The estimator accepts deadline-locked manager picks and sample weights, then calculates ownership, captaincy, Triple Captain, and EO. It handles normal starting XIs, Bench Boost (all 15 count), and Triple Captain (three exposure units). It requires exactly 15 picks and one captain per sampled manager, and explicitly labels its result `SAMPLE_ESTIMATE_NOT_GLOBAL_CENSUS`.

The estimator's tests passed in run [44147222576](https://github.com/uasir/CTA-FPL-Model/actions/runs/44147222576). No live manager-pick source has yet been wired into the project. Current `selected_by_percent` and historical `selected` counts must not be described as EO.

Source research and remaining gates are recorded in [FPL_DATA_SOURCE_BLOCKER_REGISTER_2026-11-17.md](FPL_DATA_SOURCE_BLOCKER_REGISTER_2026-11-17.md). The review found a public EO method page (Fantasy Football Pundit) and historical top-10k EO tables (LiveFPL), but neither has yet been verified as a licensed bulk API. A public FPL snapshot mirror has daily ownership CSVs, but no recognized licence; do not ingest it without permission.

### Point-in-time storage and source-rights decision

The official ingestion workflow's artifact retention has been changed from 30 to 90 days. This is a temporary retention improvement, not a durable season archive. The CTA repository is public, so raw FPL snapshots and manager picks must not be committed there as a storage workaround. A private Dropbox connection was suggested for long-term snapshot storage; it is not connected yet.

The event/target source blocker remains: StatsBomb Open Data's PL seasons do not overlap FPL archive coverage; Wyscout 2017/18 is a licensed event-side candidate but FPL target-data rights remain unresolved; the Opta/PulseLive candidate still has no confirmed licence and no player-match outputs in the inspected tree. No player identity or source has been promoted to production.

### New reproducibility metadata

The ingestion script now classifies each snapshot against the next upcoming FPL deadline (`PRE_DEADLINE_WITHIN_24H`, `PRE_DEADLINE_OVER_24H`, or `NO_FUTURE_DEADLINE`) and records the next deadline ID/time and hours remaining. The lagged-feature report now correctly states that all rostered players are requested and labels the selected-share feature as global ownership, not EO. These metadata corrections are included in the next pipeline run.

### Next steps

1. Verify the next scheduled artifact has 90-day retention and records the snapshot/deadline classification.
2. Connect private durable storage before claiming a full-season point-in-time archive.
3. Verify whether the Onside Arena CC BY 4.0 graded-prediction Zenodo record is downloadable with complete player IDs and historical coverage; use it as an external forecast benchmark only after schema and provenance checks.
4. Wire a deadline-safe rank-tier manager-pick sample into the EO adapter, or obtain a licensed provider feed. Do not use post-GW ranks to define the cohort.
5. Resolve historical FPL target rights before combining Wyscout or another event provider with FPL labels.

## Verified deadline metadata and ingestion workflow isolation

Run [44147764850](https://github.com/uasir/CTA-FPL-Model/actions/runs/44147764850) completed successfully on the updated ingestion code. Its artifact is `cta-fpl-official-44147764850` (artifact ID `14356903141`), with verified expiry **2027-02-15 18:25:57 UTC**—90-day retention.

Snapshot metadata confirms:
- Captured `2026-11-17T18:27:22.715472Z`.
- Next deadline: GW11, `2026-11-21T11:00:00Z`.
- Snapshot was `PRE_DEADLINE_OVER_24H`, 88.544 hours before the deadline.
- Bootstrap and fixtures SHA-256 hashes were recorded; all 672 element-summary requests succeeded.

This is now an explicit, machine-readable way to distinguish snapshots captured before or after the next deadline. It does not yet guarantee a snapshot within 24 hours for every deadline; the daily 05:30 UTC schedule will capture that nearer window for the next Saturday deadline.

The FPL workflow has been separated from ordinary code-push CI. Full API ingestion now runs on schedule or manual dispatch, while the new `cta-fpl-ci.yml` runs the engineering test suite on code changes. This prevents every small code commit from launching another 672-player API fetch. The first all-tests CI attempt exposed the workbench package path requirement (`src`); the `PYTHONPATH` was corrected to `scripts:src`, and the follow-up CI run is pending.

Artifact retention is now 90 days, but the repository is public and the artifact window still does not preserve a full season. Private Dropbox storage remains the next storage gate; the connection suggestion has not been accepted/connected yet.

## Deadline-aware top-10k EO capture implementation

Added a separate hourly workflow: [`.github/workflows/cta-fpl-eo-capture.yml`](../.github/workflows/cta-fpl-eo-capture.yml). It runs at minute 15 each hour, but only proceeds when the next FPL deadline is within 70 minutes. It samples 100 managers from stratified rank bands in the overall top 10,000, captures each manager's public target-GW picks and active chip, weights each manager as 100 entries, and feeds the sample into the tested EO estimator.

Privacy/reproducibility choice: the collector calculates EO in memory and stores only aggregated per-player EO percentages plus sample metadata and a hash of sampled entry IDs. It does **not** publish raw manager IDs or individual manager picks in the public repository artifact.

The capture is not yet live-validated. It depends on the public FPL picks endpoint returning each manager's saved picks for the upcoming event before lock. If it does not, the workflow will fail visibly; the fallback will be a predeadline rank-cohort snapshot followed by a separate post-lock picks retrieval. The next real validation point is GW11, whose deadline is 2026-11-21 11:00 UTC. The collector currently covers top 10k only, not top 100k or the whole field.

Engineering CI run [44148615692](https://github.com/uasir/CTA-FPL-Model/actions/runs/44148615692) passed **70 tests plus 3 subtests** after adding the manager sampler and EO aggregation tests. The earlier full FPL workflow run [44147764850](https://github.com/uasir/CTA-FPL-Model/actions/runs/44147764850) remains the latest verified official-data ingestion, with 672/672 summary requests successful and 90-day artifact retention.

Updated source/rights and acquisition decisions: [FPL data-source blocker register](FPL_DATA_SOURCE_BLOCKER_REGISTER_2026-11-17.md).
## EO capture CI confirmation

After the hourly top-10k EO collector and its workflow were added, the lightweight CI run [44148843292](https://github.com/uasir/CTA-FPL-Model/actions/runs/44148843292) completed successfully. The all-tests suite and crosswalk validation both passed. The latest test count remains 70 tests plus 3 subtests from [44148615692](https://github.com/uasir/CTA-FPL-Model/actions/runs/44148615692).

The hourly collector is scheduled but has not yet produced a near-deadline sample. It will first be eligible for GW11 near the 2026-11-21 11:00 UTC deadline. The live picks-endpoint response is the remaining technical validation for EO capture.

## Dual recommendation architecture decision — 2026-11-17

The user approved the proposed dual recommendation architecture. This is an accepted product/engineering requirement, recorded in GitHub issue [#2](https://github.com/uasir/CTA-FPL-Model/issues/2).

### Product modes

1. **Personal Squad Recommendations** (`personal_squad`): uses an explicit manager squad snapshot and constraints (15 players/IDs, bank, squad value and purchase prices where available, free transfers, chips, formation, XI/bench rules, risk preferences and rank target). It recommends transfers and alternatives, hold/roll decisions, XI, formation, bench order, captain/vice-captain, and whole-squad portfolio decisions. Every recommendation must explain its assumptions and show relevant EV, EO, minutes, fixtures, uncertainty and downside/upside. It must evaluate the effect of a move on the whole squad rather than rank incoming players in isolation.

2. **General FPL Recommendations** (`general_market`): independent of any user's squad. It ranks players and opportunities across positions and categories: overall/value picks, expected points, differentials, captaincy, short/long-term fixture targets, improving/declining prospects, high-upside/high-risk picks, and sell/avoid watchlists. It must not read, infer, or require the personal squad.

### Shared foundation and separation

Both modes consume the same versioned, leakage-safe player/fixture forecast and validated data services. Recommendation logic remains separate. General recommendations must be invariant to personal squad changes; personal recommendations must be sensitive to the supplied squad and constraints. Outputs must disclose forecast horizon, data coverage, model version/confidence and unvalidated inputs. Preserve deterministic Python/JavaScript parity for shared calculations and test both modes independently.

### CoVar policy

CoVar is a portfolio-risk analysis layer, not a squad component and not a mandatory input to general player rankings. It may inform personal portfolio decisions only after stability and out-of-sample validation. The current ten-gameweek historical-points covariance matrix remains exploratory and is not approved for production recommendation decisions. General mode may expose validated covariance context as optional supplementary information, but must remain useful without it.

### Acceptance tests

- General recommendations work without any squad input.
- General rankings remain identical when the personal squad changes, for the same data snapshot/model version/filters.
- Personal recommendations use the explicit squad snapshot and change appropriately when relevant squad constraints change.
- General output is reproducible for identical inputs.
- Personal output records the squad state and constraints used.
- EV, EO, minutes, price and fixture inputs are traceable; missing data is surfaced rather than invented.
- CoVar remains disabled as a decision signal until statistical stability and out-of-sample gates pass.
- Tests cover squad invariance, squad sensitivity, constraints, reproducibility and Python/JavaScript parity.

### Implementation sequence

Inspect the existing contracts and current repository before coding. Keep the recovered original Python source and current Python/JavaScript engines intact. First define shared forecast interfaces and recommendation input/output contracts; then implement and test `general_market` and `personal_squad` independently. Do not duplicate the forecasting engine or let general rankings inherit the user's squad context.


## Dual recommendation architecture — implementation continuation, 2026-11-18

The accepted dual-system architecture now has machine-readable and executable input-boundary contracts.

Added:
- `config/recommendation_system_contracts.json`: versioned definitions for the shared forecast metadata, independent `general_market` and `personal_squad` inputs, output categories, covariance policy and acceptance tests.
- `scripts/recommendation_contracts.py`: strict Python request validators for both systems.
- `tests/test_recommendation_contracts.py`: tests for squad-independent general requests, rejection of personal context (including nested fields), 15-player squad integrity, required personal constraints and duplicate forecast IDs.

Important boundary behavior:
- `general_market` accepts a shared forecast snapshot and public filters, but rejects squad, bank, transfer, chip, formation, rank-target, manager-identity and personal-preference fields at any nesting level.
- `personal_squad` requires an explicit 15-player snapshot with unique FPL element IDs and purchase prices, plus bank, free transfers and a risk profile.
- Both require a forecast snapshot ID, model version, horizon and a non-empty, duplicate-free player forecast list.
- This is a request-contract layer, not yet either recommendation/scoring engine. It deliberately makes no player rankings or transfer claims while forecast validity is unresolved.

Commits:
- Contract definition: `eff1129fd9d0a485e138a4cabdd2ecfd4eea2504`.
- Initial validators: `359957c522e632c17aefcc5522b94fb8457238bc`.
- Contract tests: `9beb594176b0390cedc13e3a77ba05776fc2df06`.
- Nested personal-context isolation hardening: `0cf8bd54a21dd54deb1bd553adf741435ed4ace2`.
- Nested-boundary regression tests: `e9ee98b07b5d389a5c5d7c8ffa4827c8e6c0ac98`.

The CI workflow is configured to run on pushes affecting the engineering scripts/tests. The connector did not expose a check-run result for the final commit at report time; therefore these new tests are **committed but CI-unverified**. Do not mark the implementation gate passed until the workflow run is inspected.

Next engineering steps:
1. Verify the CI run for the final contract commit and repair any failures.
2. Define the shared forecast record schema and data-quality status envelope without implying that exploratory baselines are validated forecasts.
3. Add the equivalent JavaScript boundary validators and cross-language contract fixtures.
4. Implement general-market ranking independently of personal context; test ranking invariance.
5. Implement personal squad optimisation as a separate engine; test sensitivity to squad, bank, transfers and risk constraints.
6. Keep production CoVar disabled until its stability and out-of-sample gates pass.
