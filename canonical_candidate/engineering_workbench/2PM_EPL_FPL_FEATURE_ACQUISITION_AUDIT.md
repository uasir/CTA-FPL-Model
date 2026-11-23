# 2PM Transformer — EPL/Opta and FPL Feature Acquisition Audit

**Date:** 2026-11-23  
**Branch:** `feat/four-layer-2pm-transformer-evaluation`  
**Status:** Initial source audit; feature schema gate remains blocked  
**Purpose:** Map paper-confirmed 2PM feature concepts to the actual FPL and EPL/Opta data already inspected in this repository.

## 1. Decision summary

The user's acquisition approach is adopted: search each paper feature in FPL and EPL/Opta first, record actual availability and acquisition status, and investigate additional sources only for unresolved gaps.

This audit does **not** claim that the complete 116-feature dictionary is known. The paper confirms 116 player-match inputs but the accessible publication does not enumerate all 116 columns or their exact definitions. The existing `2PM_116_FEATURE_EVIDENCE_REGISTER.md` remains the authority for the paper evidence and feature-family limitations.

**Current result:**
- FPL: verified player-fixture history with a useful subset of player-level match statistics and the FPL target label.
- EPL/Opta/PulseLive integration: verified player-season identity crosswalk and team-match event data; no player-level per-match event rows were present in the inspected source snapshot.
- Therefore, no complete 116-feature dataset can currently be assembled from the audited FPL + Opta integration.
- No schema freeze, model implementation, training, or data promotion is authorized by this audit.

## 2. Audited repository sources

### 2.1 Official FPL adapter

Inspected: `canonical_candidate/engineering_workbench/scripts/fetch_fpl_official_api.py`.

The adapter fetches `bootstrap-static`, `fixtures`, and `element-summary/{id}`, and emits:
- `fpl_players.csv`: current player/season metadata and season aggregates.
- `fpl_fixtures.csv`: fixture metadata and kickoff/gameweek context.
- `fpl_player_fixture.csv`: player-fixture history.

The player-fixture field contract includes:
`minutes`, `total_points`, `goals_scored`, `assists`, `clean_sheets`, `goals_conceded`, `own_goals`, `penalties_saved`, `penalties_missed`, `yellow_cards`, `red_cards`, `saves`, `bonus`, `bps`, `influence`, `creativity`, `threat`, `ict_index`, `starts`, `expected_goals`, `expected_assists`, `expected_goal_involvements`, `expected_goals_conceded`, `selected`, `transfers_balance`, `transfers_in`, `transfers_out`, and `value`, alongside player, fixture, opponent, home/away, kickoff and gameweek identifiers.

Important distinctions:
- `total_points` is the natural FPL prediction target, not an input for predicting the same fixture.
- Match-level `expected_goals` / `expected_assists` may be usable as retrospective match features only for a later target match, subject to strict timestamp/vintage checks.
- The adapter's current capture is not proof that equivalent values were available at historical deadlines. Its metadata explicitly labels historical vintage status as unverified.
- Position in this adapter is derived from the current bootstrap player metadata; it is not a verified historical match-specific position.
- `selected`, transfers and `value` are not automatically player-performance inputs. Their timing and relevance need separate decisions.

### 2.2 EPL/Opta/PulseLive integration

Inspected:
- `canonical_candidate/engineering_workbench/scripts/build_opta_lagged_team_features.py`
- `canonical_candidate/engineering_workbench/reports/OPTA_PULSELIVE_LIVE_INTEGRATION_2026-11-18.md`
- `canonical_candidate/engineering_workbench/reports/OPTA_PULSE_FPL_SOURCE_AUDIT_2026-11-17.md`

The pinned provider snapshot contained:
- Player-season aggregates under `players_stats`.
- Team-match event aggregates under `events_stats`.
- No player-level per-match event files in the inspected tree, despite the provider README describing such files.

The integration verified:
- 511/511 shared numeric player IDs matched FPL player codes, with exact team-code checks.
- 100/100 provider match IDs matched FPL fixture `code` values.
- The source yielded team-match metrics including `expectedGoals`, `expectedAssists`, `accuratePass`, `possessionPercentage`, `finalThirdEntries`, `attemptsIbox`, `ballRecovery`, `interception`, `duelWon`, and `touches`.

These are team-level match observations, not player-level match observations. The integration's generated player-fixture sidecar attaches lagged team context to players; it does not turn team statistics into player statistics.

The provider snapshot was a current-season cumulative snapshot, not archived deadline vintages. Its point-in-time status is explicitly `NOT_VERIFIED`. Underlying Premier League/PulseLive data rights are also unverified; a repository-level MIT license is not proof of rights to the underlying data.

## 3. Paper-confirmed concept mapping

Status vocabulary:
- **Present (candidate):** a corresponding field exists at the relevant player-fixture grain, but exact equivalence to the paper's undefined field remains unconfirmed.
- **Partial / proxy:** related data exists, but does not establish the paper's exact definition.
- **Not in inspected feed:** absent from the actual inspected adapter/snapshot; this does not prove no provider product could supply it.
- **Wrong grain:** a related field exists only at team-match or player-season grain.
- **Unresolved:** access, definition, historical coverage, timestamp, rights, or mapping is not cleared.

| Paper-confirmed concept | FPL player-fixture history | Current EPL/Opta integration | Acquisition conclusion |
|---|---|---|---|
| Minutes | Present (candidate) | Not present as player-match field | FPL candidate; validate definition and vintage |
| Player position | Current player metadata only; no verified historical match position | Player-season/current metadata only in inspected feed | Historical match-specific position unresolved |
| Goals | Present (candidate) | Team-match expected-goals is wrong grain; no player-match goals feed inspected | FPL candidate; target-match goal value must not leak |
| Assists | Present (candidate) | Team-match expected-assists is wrong grain | FPL candidate; definition/vintage checks required |
| Penalty kicks made/scored | Penalties missed/saved exist; scored penalty not separately established in match field list | Not present as player-match event field | Incomplete; obtain event-level penalty outcome |
| Yellow cards | Present (candidate) | No player-match card field in inspected feed | FPL candidate |
| Red cards | Present (candidate) | No player-match card field in inspected feed | FPL candidate |
| Own goals | Present (candidate) | No player-match field in inspected feed | FPL candidate |
| Shot saves / goalkeeper saves | Present (candidate) | No player-match goalkeeper save field in inspected feed | FPL candidate |
| Tackles | Not in inspected FPL match history | Not in inspected Opta player-match feed | Gap; team duelWon is not player tackles |
| Blocks | Not in inspected FPL match history | Not in inspected Opta player-match feed | Gap |
| Clearances | Not in inspected FPL match history | Not in inspected Opta player-match feed | Gap |
| Interceptions | Not in inspected FPL match history | Team-match interception exists (wrong grain) | Player-match gap; team context is not equivalent |
| Passing types | Not in inspected FPL match history | Team-match accuratePass exists (wrong grain and too aggregated) | Player-match gap |
| Shot-creating actions | Not in inspected FPL match history | Team expected-assists is not an SCA count; wrong grain | Gap; do not substitute xA |
| Goal-creating actions | Not in inspected FPL match history | Team expected-goals/assists are not GCA counts; wrong grain | Gap |
| Save percentage | Not in inspected FPL match history | Not in inspected team-match metrics | Gap; potentially derive only if both numerator and denominator exist with compatible definitions |

This table maps only concepts explicitly identified in the accessible paper text. It is not a reconstruction of all 116 columns.

## 4. Other FPL fields: useful but not paper-equivalent by default

The adapter also exposes FPL-specific fields:
- `total_points`: target label for the target player-fixture; never same-fixture input.
- `bonus`, `bps`: FPL scoring/bonus outcomes; may be useful only as prior-match features where available before the next target deadline.
- `influence`, `creativity`, `threat`, `ict_index`: FPL-derived match/season indicators; potentially useful candidate predictors, but they are not interchangeable with event-level passing, SCA, GCA or defensive-action fields.
- `clean_sheets`, `goals_conceded`: FPL match outcomes and potential lagged features; define goalkeeper/defender/appearance semantics before use.
- `selected`, `transfers_balance`, `transfers_in`, `transfers_out`, `value`: FPL market/price context, not football action measures. Require point-in-time capture and an explicit inclusion rationale.
- `expected_goal_involvements`, `expected_goals_conceded`: FPL-derived indicators; retain as their own fields, not substitutes for paper-defined event metrics.

These fields can be evaluated for a clearly labelled adaptation, but must not be presented as recovered paper features.

## 5. Acquisition ledger

| Data requirement | Current status | Next evidence needed |
|---|---|---|
| Exact 116-column paper dictionary | **Not acquired** | Author supplement/code or direct author clarification |
| FPL player-fixture history | **Acquired by adapter; current capture** | Snapshot archive, historical vintage proof, lawful use/retention review |
| FPL target labels (`total_points`) | **Acquired by adapter; current capture** | Historical season coverage, rights/retention review, target reconciliation |
| EPL/Opta player-season aggregates | **Acquired in inspected provider snapshot** | Raw field dictionary, season coverage, rights; do not treat as match-level |
| EPL/Opta team-match event aggregates | **Acquired in inspected provider snapshot** | Field definitions, historical coverage, point-in-time snapshots, underlying data rights |
| EPL/Opta player-match event statistics | **Not present in inspected snapshot** | Verify whether an actual downloadable/API feed exists and whether access is granted |
| Player identity crosswalk | **Current-season technical check passed for 511 IDs** | Historical cross-season mapping, transfers/club changes, persistent identity and coverage |
| Fixture crosswalk | **Current-season technical check passed for 100 provider matches** | Historical season coverage and postponed/rescheduled fixture handling |
| Historical pre-deadline vintages | **Not established** | Archived timestamped source snapshots or vendor guarantees/data extracts |
| Underlying Opta/PulseLive data rights | **Unresolved** | Contract/license confirmation covering research, retention, derivative features and model training |

## 6. Data-grain and leakage rules

1. The 2PM input sequence is player-match based. Player-season and team-match fields must remain explicitly labelled at their own grain.
2. Team-match metrics may be joined as contextual features only through the player's team and target fixture, and must not be represented as player actions.
3. Every historical feature must be proven available by the target FPL deadline, not merely have a kickoff timestamp before the target match.
4. For an FPL Gameweek with multiple fixtures, preserve each actual match as a distinct observation for the five-match sequence. Do not collapse a Double Gameweek into one artificial match.
5. The target fixture's outcomes, including FPL points, goals, assists, saves, BPS and post-match xG/xA, must never appear as inputs for that same target.
6. Blank Gameweeks are not player-match observations.
7. Historical current-roster metadata must not be projected backwards to prior matches.
8. Missing, true zero, not collected, not applicable and unknown must remain distinct states.

## 7. Next acquisition actions

1. Request the exact 116-field dictionary, data-provider details, feature definitions and preprocessing rules from the paper authors.
2. Confirm whether the Opta/PulseLive provider has a separately accessible player-match event feed, and inspect the actual files/API response before claiming coverage.
3. Obtain the full raw field dictionaries and season coverage for the existing Opta player-season and team-match files.
4. Establish FPL historical snapshot/vintage availability and the rights to retain and use historical FPL labels/features for model training.
5. Only after those checks, extend the matrix to every exact paper column or create a separately versioned adaptation schema with explicit gaps and substitutions.

## 8. Readiness

- Exact paper 116-feature dictionary: **NOT LOCATED**.
- FPL player-fixture source: **PARTIAL INPUT COVERAGE; HISTORICAL VINTAGE UNVERIFIED**.
- EPL/Opta player-match source: **NOT VERIFIED / NOT PRESENT IN INSPECTED SNAPSHOT**.
- EPL/Opta team-match context: **STRUCTURALLY AVAILABLE; POINT-IN-TIME AND RIGHTS UNRESOLVED**.
- Full lawful point-in-time 116-feature dataset: **NOT ESTABLISHED**.
- 2PM model implementation: **NOT STARTED**.

**Gate: `FEATURE_ACQUISITION_INVENTORY_INCOMPLETE`.** This is a source audit and acquisition plan only; it does not authorize schema freeze, model implementation, training, data promotion or production use.
