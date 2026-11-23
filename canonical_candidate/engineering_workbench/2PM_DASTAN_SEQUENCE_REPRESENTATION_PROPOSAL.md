# 2PM — Dastan 286-Feature Sequence Representation Proposal

**Date:** 2026-11-23  
**Status:** Selected governing adaptation; implementation underway. Post-match state and player-Gameweek grouping builders exist, but data admission and sequence freeze remain open.  
**Governing references:** Wiechno, Duch and Bartosik (2026); `2PM_DASTAN_286_FEATURE_ADAPTATION_DECISION.md`; `2PM_DASTAN_SOURCE_SEMANTICS_AUDIT.md`.

## Implementation note

The original six-token pre-match-row builder remains a reference prototype only. The selected implementation now has a post-match 286-state reconstruction layer and a grouped player-Gameweek sequence tensor builder. The new path has not yet been run against the complete historical artifacts or admitted for training. Do not train on or freeze any candidate tensor until feature-level deadline, source-vintage, identity/coverage and label-grain checks are cleared.

## 1. Problem and paper interpretation

The paper's input is a sequence of five consecutive matches actually played by a player, with a maximum 21-day gap between selected observations. Each observation is a per-match feature vector representing the player's form in that match. The paper describes the features as based on FPL rules and information available to managers before the *forecast target* Gameweek deadline.

Dastan's 286 columns are not raw match statistics. They are engineered rolling/context features in a player-fixture frame, with rolling histories lagged so a target fixture's own outcome is excluded. The released 286-vector is therefore a **pre-match target-fixture snapshot**, not automatically a post-match observation vector for a previous fixture.

A direct substitution of the released row into each historical sequence position would give every token pre-match semantics and would omit the current target fixture context. The 2PM adaptation needs an explicit historical-state construction and a separate target query.

## 2. Recommended adaptation — five historical state tokens plus target query

Use a **six-token encoder input**:

- Tokens 1–5: the five most recent eligible previous player fixtures in which the player actually played (minutes > 0), ordered chronologically. Each is a **Dastan-derived post-match state vector** for that historical fixture: the same 286 feature definitions are reconstructed at the end of that match, with rolling player/team/opponent/availability/defensive features updated to include that completed match. Fixture-specific context fields (opponent, venue, price/selection/transfer context and pre-deadline signals) retain the values available before that historical match.
- Token 6: the current target-fixture query vector, containing the 286 Dastan features reconstructed strictly as of the target Gameweek's official FPL deadline. Its rolling features include only matches completed before that deadline; the target fixture's own outcomes are absent.

Tensor shape:

`[batch, sequence=6, features=286]`

The model reads the final target-query token's encoder representation and predicts the target fixture's player FPL points through the paper's two-component Poisson-mixture head.

This is a documented adaptation: five Dastan-derived historical post-match state vectors plus one pre-deadline target query token. It is not the paper's original five-token/116-feature input and is not a direct use of the released Dastan feature rows.

## 3. Why the historical tokens are post-match states

A previous match's outcome is known by the time a later target Gameweek deadline arrives. The paper's five observations represent previous played matches, not five calendar-week snapshots.

For each historical match token:
- rolling player form features include the completed match's own performance (for example, the one-match FPL-points window reflects that match);
- team/opponent/defensive/availability rolling state is updated only through that match's completion;
- match context fields remain the information associated with that historical fixture, captured before it;
- no match occurring after that historical fixture's completion may enter the token.

This makes each historical token a per-match state observation. It does require a new 2PM feature-state builder; the existing released Dastan row is not simply relabelled or shifted.

## 4. Why use a target-query token

The current target fixture has information not present in the historical match states: its opponent, home/away status, current deadline snapshot, target-date context and current availability/market information.

The target-query token keeps this information aligned with the prediction. Its rolling features must be reconstructed from completed history strictly before the official target Gameweek deadline.

The target query token must never include the target fixture's points, minutes, goals, assists, bonus, cards, defensive actions or any other target outcome.

## 5. Feature timing contract

The 286 feature names remain the candidate column vocabulary, but each feature must have a token-specific temporal definition:

| Feature role | Historical tokens 1–5 | Target token 6 |
|---|---|---|
| Player/team/opponent rolling statistics | Recomputed through the historical match's completion, including that match | Recomputed using only matches completed before target deadline |
| Availability history | Updated through the historical match | Uses only prior appearances before target deadline |
| Defensive contribution/CBIT/recovery/tackle rolling features | Updated through the historical match where the statistic is collected | Uses only completed prior matches before target deadline |
| League rank and opponent rank | Recomputed from standings after the historical match data become available | Reconstructed from standings before target deadline |
| Opponent and home/away context | Historical fixture context | Current target fixture context |
| Price, selected %, transfer balance | Historical fixture's valid pre-match snapshot | Archived target-deadline snapshot only |
| `ep_next` and `sig_*` | Snapshot accepted before the historical fixture's Gameweek deadline | Snapshot accepted before the target Gameweek deadline |
| Rest/congestion | Retain the historical fixture's pre-kickoff rest and known-schedule congestion context | Reconstructed strictly before target deadline |
| Target points and other outcome labels | Historical match result contributes through explicitly rebuilt rolling state after completion; never copied as an unlabelled raw target column | Excluded entirely from inputs |

The exact 286-column definitions, units, source lineage and missingness rules remain governed by the feature admission register. If a feature has no defensible historical-state and target-query semantics, it must be excluded or separately redesigned; do not force the same number of columns by fabricating values.

## 6. Played-match selection

- Select actual previous player fixtures using fixture-level FPL history and `minutes > 0`; calendar Gameweeks are not observations.
- A double Gameweek can contribute two previous played fixtures if the player played in both.
- A blank Gameweek contributes no played-match token.
- Order by actual kickoff/completion timestamp, with fixture ID as a deterministic tie-break.
- Preserve the paper's maximum 21-day gap between selected observations. The paper's exact interpretation of the interval boundary must be pinned before the sequence builder is frozen.
- Default to requiring five eligible previous played fixtures; do not silently pad or replace missing observations with calendar-week rows. Any cold-start/padding adaptation requires a separate decision and evaluation.
- Do not cross player identities when constructing sequences. Use corrected, versioned player mapping and explicit transfer/alias handling.

## 7. Double Gameweeks

For two historical fixtures in the same Gameweek:
- create two separate historical tokens if the player played in both;
- token 1's post-match state includes the first fixture only;
- token 2's post-match state may include the first fixture and then the second fixture as it completes;
- neither token may include any result from a fixture that had not completed at that token's state timestamp;
- the current target token includes both historical results only if both completed before the current target deadline.

This is different from Dastan's existing per-player/Gameweek deadline anchoring. The new builder must preserve event-time ordering for historical match states while separately constructing the current target vector at the common target deadline.

## 8. Leakage and label separation

- The target fixture's `total_points`, minutes, goals, assists, bonus, cards and other outcome fields are labels/evaluation metadata only.
- A historical match's result can enter only that historical token's post-match rolling state and later tokens after the result is complete.
- No result after the target deadline can enter the target query token.
- Do not let an earlier same-Gameweek result enter a historical token whose state timestamp precedes that result's completion.
- Fit all imputers, scalers, encoders and transformations on chronological training data only.
- Historical state time is the later of the player match-availability timestamp and kickoff + 24 hours, plus 1 ns, so the current player and team match records are eligible under the current conservative source bounds. This is not a claim of immediate full-time availability.
- Post-match player/team/opponent rolling features and ranks are reconstructed season by season; previous-season rolling history is excluded unless a separate identity/continuity decision admits it.
- Preserve missingness and unavailable-source semantics; do not collapse missing into genuine zero.

## 9. Trade-offs and required checks

This design is more faithful to the paper's per-match sequence concept than five calendar-week snapshots, but it is a substantial data adaptation: the released Dastan rows are pre-match, while the five historical tokens are reconstructed post-match states.

Before accepting the design:
1. Verify the paper's precise 21-day eligibility interpretation.
2. Define historical state timestamps and the exact rolling-window inclusion rule for every feature family.
3. Rebuild all historical feature states under corrected player identity mappings.
4. Rebuild target-query vectors strictly at each official FPL deadline.
5. Complete the independent event-level deadline reconstruction in `2PM_DASTAN_SOURCE_SEMANTICS_AUDIT.md`.
6. Verify that each previous played fixture has one and only one historical token.
7. Quantify missing-feature and identity coverage by season.
8. Test double Gameweeks, simultaneous kickoffs, postponed fixtures, transfers, blank periods and season boundaries.
9. After implementation, compare against a 286-feature target-snapshot baseline and a sequence ablation using the same chronological splits. This is later model evaluation, not permission to tune before the data gates pass.

## 10. Alternatives not selected as the default

- **One 286-feature target snapshot only:** simplest and directly matches Dastan's released player-fixture grain, but discards the paper's five-match temporal sequence.
- **Five pre-match snapshots only:** uses Dastan's released row semantics directly, but does not represent the completed match outcomes as clearly as the paper's per-match sequence and omits a dedicated current target query.
- **Five historical tokens with no target query:** omits current target fixture context such as opponent, home/away and deadline-specific availability.
- **Six calendar Gameweek rows:** invalid because blank Gameweeks are not played matches and double Gameweeks can contain two actual matches.

## 11. Decision status

The user selected post-match historical states as the governing sequence semantics. The current implementation path is:

1. reconstruct one 286-feature post-match state for each actually played historical fixture;
2. retain the completed fixture's pre-kickoff context and archived pre-kickoff snapshots while refreshing player/team/opponent/availability/defensive rolling state and post-match ranks;
3. use the five most recent same-season played-match states, with the 21-day gap rule;
4. append one strictly pre-deadline target query per target fixture;
5. group all target fixtures into one player-Gameweek sample and train/evaluate against one correctly grained Gameweek label;
6. use a signed shifted two-component Poisson mixture candidate so negative points are not clipped.

The two new builders and associated contract tests are present in the feature branch. The focused CI workflow includes them, but its latest run has not yet been independently verified. The pre-match sequence prototype remains a reference control only.

The design is selected but **not frozen or admitted**. The remaining gates are:
- verify target-label grain and fixture-level versus Gameweek-level target_points semantics from the pinned source;
- run the complete post-match reconstruction against historical source artifacts;
- complete the independent feature-by-feature point-in-time and source-vintage audit;
- verify exact historical match availability and the 21-day rule;
- quantify season coverage, identity continuity and missingness;
- validate the shifted-Poisson support floor and compare signed-distribution alternatives.

No model training, feature admission, production promotion or M3/M4 integration is authorized by this design update.
