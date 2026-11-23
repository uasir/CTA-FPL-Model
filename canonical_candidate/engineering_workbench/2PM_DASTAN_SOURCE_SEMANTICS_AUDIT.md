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

## 5. Additional modelling and data risks

- The 286-feature contract was tuned for a minutes prediction task. It is not evidence that the same feature set is optimal or correctly represented for FPL points.
- `sig_has_news` is documented as 99.97% identical to `sig_status_risk > 0`; this is a redundancy concern, not a leakage finding.
- `ar_rest_days` and `ar_team_matches_14d` omit non-Premier-League matches and therefore understate all-competition load.
- The upstream documentation reports that some candidate feature families were rejected for the minutes model. Those experiments do not establish whether a feature helps or harms a points model.
- Source code MIT licences do not grant rights to FPL or Understat source data. Underlying terms and training/retention permission remain separate gates.

## 6. 2PM implications

1. Retain the exact 286 ordered schema as the audit inventory, not as an approved immutable input list.
2. Prioritise R1–R4 before feature admission or sequence design.
3. Build the new 2PM input adapter independently; do not import Dastan's model/data loader or model preprocessing.
4. Keep target points and minutes labels separate from the 286 input columns.
5. Resolve whether the 2PM sequence tokens can be reconstructed from point-in-time-safe Dastan features. The existing player-fixture snapshots are not themselves five raw match vectors.
6. If a feature is not safe or available, exclude/rebuild it with a versioned schema change and report the new feature count. Do not force all 286 through.

## 7. Current status

- Exact 286 ordered column inventory: **verified against pinned schema**.
- Source construction families: **inspected**.
- Upstream lagging and selected deadline safeguards: **confirmed in code**.
- Opponent/rank double-Gameweek leakage: **potential risk; row-level test not run**.
- Market-field pre-deadline timestamps: **not verified**.
- Historical player identity corrections: **documented; 2PM crosswalk audit not run**.
- Defensive feature season coverage: **source-documented; row-level audit not run**.
- Sequence-token design: **unresolved**.
- 2PM schema admission: **not approved**.
- Training, evaluation and production: **not started / not authorized**.

**Gate:** `DASTAN_286_ADAPTATION_AUDIT_IN_PROGRESS`.
