# 2PM — Dastan Source Semantics and Temporal-Risk Audit

**Date:** 2026-11-23  
**Status:** Source-code inspection complete for the pinned Dastan revision; historical row-level tests not run  
**Upstream:** `qazybekb/smartplayfpl-dastan@758db9247e8b3a9a870c991064f74d8339d61cd0`  
**Purpose:** Identify which parts of the Dastan 286-feature frame can be considered for 2PM and which must be independently revalidated.

## 1. Executive finding

The pinned Dastan implementation provides a well-documented player-fixture training frame and meaningful temporal safeguards. It also contains several assumptions that must not be inherited blindly by a player-points model using the paper's five-previous-played-match design.

The most important 2PM follow-ups are:

1. **Potential deadline leakage in opponent rolling features and standalone rank fields.** Dastan's deadline-anchor prefix list includes `player_`, `team_`, `ar_`, `p_any_`, `p60_` and `e_minutes_`, but deliberately excludes `opp_` and does not include `status_league_rank` or `opp_status_league_rank`. This requires a row-level double-Gameweek audit before these fields can be admitted.
2. **Timestamp proof for flat market fields.** `value`, `selected` and `transfers_balance` are direct model features. The inspected feature builder carries them from FPL player-match rows; their precise pre-deadline capture semantics must be verified independently.
3. **Identity integrity.** Player rolling features group by an Understat-based `player_uid` where available, with a season-specific element fallback. The upstream documentation records historical identity corrections. Rebuild/audit the crosswalk before trusting cross-season player histories.
4. **Season coverage for defensive statistics.** Defensive contribution, CBIT, recoveries and tackles are available from 2025/26 onward in the documented source frame; do not imply those observations exist in earlier seasons.
5. **Congestion scope.** `ar_rest_days` and `ar_team_matches_14d` use Premier League fixtures only, not all competitions.

These are audit requirements, not a declaration that the Dastan data are unusable. All 286 features remain `HOLD` pending evidence.

## 2. Pinned source evidence

Inspected at the pinned upstream commit:

- `dastan/data.py` — blob `36adead7d07190a9cfd743baf8714fb0f10bc251`.
- `dastan/rebuild/features.py` — blob `0707caab6bfecc610acb4c1b303e976cd5f1b909`.
- `docs/DATA.md` — source data, target and pre-deadline snapshot documentation.
- `docs/FEATURES.md` — feature family, leakage exclusions and rejected-feature notes.
- `models/feature_cols.json` — exact 286 ordered model columns, blob `a314c2724b182c0af7b4e3fa1a8fecd7afe32788`.

Upstream documents describe `features.parquet` as 163,072 player-fixture rows across EPL seasons 2020/21–2025/26. Each row has player-fixture identity, target fields and 286 ordered features. This does not mean every player has an appearance in every row; actual appearance eligibility must be established from minutes and fixture history.

## 3. Confirmed construction semantics

### 3.1 Player rolling features

The feature builder sorts by `player_uid` and kickoff, then computes each player metric as:

`shift(1).rolling(window, min_periods=1).mean()`

Windows are 1, 3, 5, 10 and 38. The player feature family combines FPL match statistics and Understat player attacking metrics. The five `player_relevant_fpl_points_*` columns are venue-conditioned prior-points averages.

This is a lagged rolling representation, not a raw match-action vector. A 286-feature token therefore contains overlapping historical summaries.

### 3.2 Team and opponent rolling features

Own-team metrics are built from Understat team-match history and shifted rolling windows. League ranks are calculated from standings accumulated before each match date.

Opponent rolling features are created by joining the opponent team's rolling history to the player-fixture row. The source code comment in `data.py` deliberately excludes the `opp_` prefix from `HISTORY_PREFIXES`, explaining that opponent form differs across the two fixtures of a double Gameweek and should not be flattened.

That choice requires independent review for 2PM's deadline-based forecasting: the FPL deadline precedes both fixtures in a Gameweek. If an opponent has an earlier fixture in the same Gameweek, its result was not known at the deadline for a later fixture. The fact that opponent context differs by fixture does not make post-deadline information admissible.

### 3.3 Availability history

`p_any_*`, `p60_*` and `e_minutes_*` are computed from prior appearances/minutes, with windows 3, 5 and 10. The inspected implementation groups these by `(fpl_code, season)`, shifts one row, and applies position-specific base-rate fallbacks to cold-start values.

### 3.4 Dastan engineered features

The 32 `ar_*` features include:
- lagged rolling defensive contribution, CBIT, recoveries and tackles;
- lagged defensive-contribution hit and near-threshold rates;
- lagged starts rates and a defensive-contribution points proxy;
- rest days and team matches in the prior 14 days;
- lagged opponent defensive-contribution/tackle allowance.

The raw target-gameweek columns `starts`, `defensive_contribution`, `cbit`, `recoveries` and `tackles` are documented as target outcomes and are deliberately not in the 286 feature list. Their lagged rolling forms are features. The 2PM adapter must preserve this exclusion.

The congestion calculations use Premier League fixture schedules only. They do not capture European or domestic-cup workload.

### 3.5 Pre-deadline snapshot fields

The `ar_ep_next` and `sig_*` features originate from separate archived FPL bootstrap snapshot artefacts. Upstream acceptance requires all of:
1. the snapshot marks the target Gameweek as `is_next`;
2. the snapshot deadline matches the official deadline;
3. the capture timestamp is strictly before that deadline.

Upstream documentation reports that accepted `ep_next` and signal snapshots have zero post-deadline rows. It reports partial 2020/21 `ep_next` coverage (approximately 99.4% in later seasons) and that the availability-signal artifact begins in 2021/22. These claims must be rechecked against the exact pinned artifacts/manifests before 2PM admission.

Missing snapshot values use `-1.0`, distinct from genuine zero. Residual NaNs are subsequently filled with `0.0` in the upstream model pipeline. 2PM must not blindly copy that imputation pipeline; it must preserve missingness states and fit any transformations using training data only.

## 4. High-priority temporal risks requiring row-level tests

### R1 — `opp_*` rolling features are not deadline-anchored by the upstream prefix routine

**Evidence:** `dastan/data.py` defines `HISTORY_PREFIXES = ("player_", "team_", "ar_", "cx_", "p_any_", "p60_", "e_minutes_")`. The code comment explicitly says `opp_` is excluded.

**Risk:** opponent rolling values for a later fixture may incorporate an earlier fixture played by that opponent in the same target Gameweek, even though that result occurred after the common FPL deadline.

**Required test:**
- enumerate every player-Gameweek with multiple target fixtures;
- for each target fixture, inspect its opponent's fixture schedule between the Gameweek deadline and target kickoff;
- recompute opponent rolling features using only matches completed before the target Gameweek deadline;
- compare with the released `opp_*` values;
- report affected rows, features, seasons and magnitude of differences.

Until passed, all 60 `opp_*` columns remain `HOLD`.

### R2 — standalone rank fields are outside the anchor prefix

**Evidence:** `status_league_rank` and `opp_status_league_rank` are generated as direct rank values. Neither prefix is in `HISTORY_PREFIXES`.

**Risk:** a later fixture's rank may reflect an earlier same-Gameweek result. The rolling `team_*` block being anchored does not prove these two direct fields are deadline-safe.

**Required test:** perform the same deadline-only reconstruction and comparison for both rank fields, including simultaneous kickoffs, postponed fixtures and double Gameweeks. Until passed, both remain `HOLD`.

### R3 — direct FPL market fields

**Evidence:** `value`, `selected` and `transfers_balance` are present as direct columns in the 286 schema and are carried through the player-match frame. They are not rolling features and are not part of the separate `ep_next`/signals snapshot acceptance path described in `data.py`.

**Risk:** the precise timestamp represented by each historical row may not equal the FPL deadline snapshot. Post-deadline price/selection/transfer changes would leak.

**Required test:** establish exact upstream source columns and their capture semantics; compare each row to archived pre-deadline bootstrap values; report coverage and mismatches. Exclude or rebuild from verified pre-deadline snapshots if equivalence is not established.

### R4 — player identity and cross-season rolling history

**Evidence:** player rolling features group by `player_uid`, constructed from Understat ID when available and a season-specific `element` fallback otherwise. Upstream `DATA.md` says FPL `element` IDs change between seasons and documents a training identity snapshot with two later-confirmed incorrect assignments.

**Risk:** incorrect/shared Understat IDs can merge player histories; season-specific fallback IDs reset a player's history at season boundaries.

**Required test:** reproduce the exact historical training assignments, compare against the corrected mapping with match-level evidence, quantify affected player-fixture rows and feature changes, and define a consistent stable-player policy for 2PM. Do not silently replace the historical mapping or fuzzy-match names.

### R5 — defensive feature availability

**Evidence:** upstream source documentation says defensive contribution, CBIT, recoveries and tackles are available from 2025/26 onward.

**Risk:** earlier seasons may have structural missingness, zeros or reconstructed placeholders. Treating these as observed zero would change the meaning of rolling features.

**Required test:** publish per-feature/per-season coverage and missingness tables; confirm exact introduction dates and source semantics; preserve unavailable/not-collected states.

## 4A. Critical refinement — the released frame's deadline invariant is narrower than the prose suggests

A deeper inspection of the pinned implementation reveals a structural gap in the deadline guarantee.

The Dastan documentation says every fixture in a Gameweek should carry information available at the common deadline. However, the actual implementation:

- computes player, team, opponent and rank statistics in kickoff order;
- shifts rolling histories by one kickoff;
- then calls `anchor_to_deadline`;
- but `HISTORY_PREFIXES` includes only `player_`, `team_`, `ar_`, `cx_`, `p_any_`, `p60_` and `e_minutes_`;
- deliberately excludes every `opp_*` feature;
- does not include the direct `status_league_rank` or `opp_status_league_rank` columns.

The assertion `assert_deadline_anchored` uses the same prefix list. It therefore proves equality only for those selected prefixes within each player's Gameweek; it does not prove that all 286 inputs are deadline-safe.

More importantly, even a prefixed history can be too late for the FPL deadline when a player's first row/fixture in a Gameweek occurs after another relevant match in that same Gameweek. The anchor selects the earliest row for that player, not a globally reconstructed history at the official Gameweek deadline.

### Consequence

This is a **confirmed structural weakness in the deadline guarantee**, but the number of affected player-fixture rows and the actual feature-value contamination have not been measured from the parquet release. Do not describe it as a quantified leak until the row-level reconstruction is run.

The affected candidate scope is broader than the original R1/R2 list:

| Feature scope | Why it needs a deadline reconstruction |
|---|---|
| All 60 `opp_*` rolling columns | Explicitly excluded from the anchor routine; later opponent kickoffs can include earlier same-Gameweek results. |
| `status_league_rank`, `opp_status_league_rank` | Direct ranks are outside the anchor prefix and are calculated from standings before each kickoff date. |
| `team_*` rolling columns | Anchor is per player/Gameweek, not a direct team/deadline snapshot; players whose first row occurs after an earlier same-Gameweek team fixture require testing. |
| `ar_opp_dc_allowed_*`, `ar_opp_tackles_allowed_*` | Computed from opponent defensive results in kickoff order; the per-player anchor is not proof that all contributing opponent matches predate the deadline. |
| `ar_team_matches_14d` and `ar_rest_days` | Built from fixture kickoffs; test whether any contributing fixture occurred after the target Gameweek deadline. |
| Other `ar_*`, `player_*`, `p_any_*`, `p60_*`, `e_minutes_*` | The per-player earliest-row anchor is useful but must be checked against official deadline and actual source event times, especially for incomplete player histories, transfers and fixture edge cases. |

### Existing test coverage observed

The pinned `tests/test_rebuild.py` covers mapping corrections, league-rank tie ordering, pre-deadline snapshot acceptance and a source-download path. It does not contain a test that independently reconstructs all 286 feature values as of each target Gameweek deadline. The runtime assertion in `dastan/data.py` is not a substitute for that test because its column selector excludes `opp_*` and direct rank fields.

## 4B. Required full-frame deadline reconstruction

The correct 2PM admission test must be independent of Dastan's existing `anchor_to_deadline` function.

For each target season/Gameweek:

1. Resolve the official FPL deadline timestamp from the archived FPL event calendar, not from the target fixture kickoff.
2. For every feature row, reconstruct all historical source events using only records whose event completion timestamp is strictly before that deadline.
3. Recompute player, own-team and opponent rolling features from those eligible events. Preserve each target fixture's opponent/home-away context, but compute the opponent's form using only pre-deadline matches.
4. Recompute league ranks from standings accumulated strictly before the deadline, not before each target fixture kickoff.
5. Recompute opponent defensive allowance and congestion/rest context using only events completed before the deadline.
6. Recompute historical availability and player histories with stable identity assignments and explicit transfer/season boundaries.
7. Compare the independently reconstructed vector to the released 286-vector, feature by feature and row by row.
8. Report, by season/Gameweek/feature: affected rows, total rows, affected percentage, maximum/mean absolute difference, missingness changes and exact source events responsible.
9. Test all 6,958 multi-fixture player-Gameweeks plus single-fixture player rows whose team/opponent has another fixture earlier in the same Gameweek. Do not limit the audit to players with two target fixtures.
10. Include postponed/rescheduled fixtures, simultaneous kickoffs, double Gameweeks, blanks, player transfers, season boundaries and source timestamp timezone handling.

The canonical raw inputs can be reconstructed using the pinned Dastan source pipeline (Vaastav FPL histories and Understat player/team matches). The release manifest pins `features.parquet` at 38,697,486 bytes with SHA-256 `dcf8411d458e7b99b15472975280cf855e15de22070022fad6fce0f76f3f299c`; the pinned release reports 163,072 player-fixture rows and 304 total columns. The raw source rebuild is needed to identify contributing event rows; comparing only values within a player's Gameweek cannot establish deadline safety.

**Do not implement a blanket “take first row per player/Gameweek” repair for all feature families.** Recompute the feature families from event-level sources at the official deadline. This retains fixture-specific opponent identity while preventing post-deadline form from entering the feature vector.

## 5. Additional modelling and data risks

- The 286-feature contract was tuned for a minutes prediction task. It is not evidence that the same feature set is optimal or correctly represented for FPL points.
- `sig_has_news` is documented as 99.97% identical to `sig_status_risk > 0`; this is a redundancy concern, not a leakage finding.
- `ar_rest_days` and `ar_team_matches_14d` omit non-Premier-League matches and therefore understate all-competition load.
- The upstream documentation reports that some candidate feature families were rejected for the minutes model. Those experiments do not establish whether a feature helps or harms a points model.
- Source code MIT licences do not grant rights to FPL or Understat source data. Underlying terms and training/retention permission remain separate gates.

## 5A. Historical identity policy and source-release freshness

The pinned upstream `data/mappings/README.md` makes an important distinction: its immutable training assignment table retains two incorrect historical Understat identities for exact Dastan reproduction. The evidence-backed corrected map replaces FPL code 437688 (Lewis Richardson → Lewis Richards; Understat 9082 → 9216) and FPL code 515501 (Álvaro Fernández goalkeeper → Álvaro Fernández Carreras defender; Understat 5191 → 10576).

The upstream `assignments_for_seasons()` function uses the immutable training assignments for already released seasons. Therefore, using the upstream canonical rebuild unchanged would preserve these identity errors. For 2PM, rebuild historical player/Understat joins using a new versioned assignment table derived from the corrected mapping and the documented historical intervals. Do not patch only the two final feature rows: the corrected identity changes the player's grouped rolling history and potentially every subsequent feature row.

The corrected map has 1,563 unique Understat IDs across 1,564 FPL codes; one shared ID is documented as two FPL spellings of Kaine Kesler-Hayden. Treat that documented alias/shared-ID case explicitly.

The pinned release manifest records a six-season frame ending in 2025/26 (163,072 rows; 304 total columns). The pinned 2026/27 roster mapping is a separate snapshot and does not provide 2026/27 player-fixture features. The upstream mapping README reports 518/577 mapped in that particular captured roster; this is not current coverage as of 2026-11-23. A refreshed, hashed current roster/mapping and a separate 2026/27 feature build are required for current-season inference.

## 6. 2PM implications

1. Retain the exact 286 ordered schema as the audit inventory, not as an approved immutable input list.
2. Prioritise R1–R4 before feature admission or sequence design.
3. Build the new 2PM input adapter independently; do not import Dastan's model/data loader or model preprocessing.
4. Keep target points and minutes labels separate from the 286 input columns.
5. Execute and audit the selected post-match 2PM state reconstruction. The existing player-fixture snapshots are not themselves five raw match vectors; the new builder reconstructs historical post-match states but still requires full-data temporal and source-vintage validation.
6. If a feature is not safe or available, exclude/rebuild it with a versioned schema change and report the new feature count. Do not force all 286 through.

## 7. Current status

- Exact 286 ordered column inventory: **verified against pinned schema**.
- Source construction families: **inspected**.
- Upstream lagging and selected deadline safeguards: **confirmed in code**.
- Opponent/rank and kickoff-relative context deadline safety: **structural guarantee gap confirmed in source; affected rows/values not quantified**.
- Market-field pre-deadline timestamps: **not verified**.
- Historical player identity corrections: **two errors confirmed in immutable release mapping; corrected-map rebuild not run**.
- Current 2026/27 feature rows: **absent from pinned six-season release; current-season build required**.
- Defensive feature season coverage: **source-documented; row-level audit not run**.
- Sequence-token design: **selected — five same-season post-match played-fixture states plus a strictly pre-deadline target query; candidate implementation added, full-data validation pending**.
- 2PM schema admission: **not approved**.
- Training, evaluation and production: **not started / not authorized**.

**Gate:** `DASTAN_286_ADAPTATION_AUDIT_IN_PROGRESS`.


## 2026-11-23 verification — target label grain

The pinned upstream Dastan documentation at `758db9247e8b3a9a870c991064f74d8339d61cd0` confirms:

- the training frame is one row per player per fixture;
- `target_points` is the FPL points scored in that individual fixture;
- the modelling/evaluation decision grain is player-Gameweek, with Double Gameweek fixture scores summed before scoring.

Accordingly, the 2PM candidate rebuild now stamps `target_label_grain=player_fixture` and `target_points_semantics=FPL_POINTS_SCORED_IN_THIS_FIXTURE`. The grouped sequence builder uses this verified declaration to sum fixture outcomes once into one player-Gameweek target. It rejects a conflicting explicit grain. This resolves the pinned Dastan label-grain question; it does not remove the need to verify row-level target coverage, non-appearance zero labels and fixture completeness in the actual rebuilt parquet.


## 7. Additional source-vintage finding (2026-11-27)

The pinned Vaastav source tree contains no `data/2025-26/understat/` directory. The pinned Dastan acquisition code therefore cannot obtain that season's Understat player/team histories from Vaastav at this release. Its documented fallback calls the live Understat API for missing player histories and team-season histories; the live player response supersedes a partial pinned CSV for that player.

For 2020/21–2024/25, per-season Understat player/team files exist and their Git histories can support a deadline-vintage reconstruction. However, the current pinned file is a final/current file version, not a deadline-specific snapshot. For 2025/26, the live API fallback is current-response data rather than a historical deadline archive. The source manifest hashes the downloaded bytes but does not establish historical publication time.

The 2PM adapter's `kickoff_time + 24 hours` availability value is a conservative FPL-fixture bound, not an observed Understat publication timestamp. Therefore:
- FPL match-stat vintages and Understat player/team metric vintages must be audited independently.
- Understat metrics remain HOLD until historical file versions and actual/defensible publication lag are evidenced.
- A live fallback may be retained for reproducibility of the current data package, but it cannot be represented as proof of what was knowable at a historical deadline.
- No XGBoost feature mask or other forecaster's preprocessing decision is relevant to this admission decision.
