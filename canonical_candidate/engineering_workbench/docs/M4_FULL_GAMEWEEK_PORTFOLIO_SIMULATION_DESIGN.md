# M4 Full-Gameweek Portfolio Simulation: Design Contract

## Status

Design gate for the next M4 engineering increment. This document does not claim that full-Gameweek FPL scoring or automatic substitutions are implemented. The existing CoVar scorer remains a synthetic fixture-slice research prototype.

## Objective

Extend the existing sampled manager portfolio bridge so a candidate squad and sampled field portfolios can eventually be evaluated over the same complete Gameweek scenario distribution. The extension must preserve the current separation between regular Gameweek and explicitly activated Free Hit analysis.

## Current input gap

The manager-ID-stripped artifact currently retains the ordered 15 player IDs, captain, captain multiplier, chip, rank stratum, and normalized sample weight. That is not sufficient to reconstruct a legal FPL starting lineup or apply automatic substitutions. The capture rows already retain pick position and vice-captain flag, but the artifact currently discards vice-captain and does not encode player positions.

Do not infer starting XI, bench order, reserve goalkeeper, player position, or vice-captain from the unordered/projected fixture player set.

## Required portfolio lineup fields

For each sampled manager, preserve the following fields in the private manager-ID-stripped artifact:

- `player_ids`: all 15 players in official pick-position order.
- `starting_player_ids`: positions 1–11, in starting lineup order.
- `starting_goalkeeper_id`: the goalkeeper among positions 1–11; require exactly one.
- `reserve_goalkeeper_id`: the goalkeeper in bench position 12; require exactly one reserve goalkeeper.
- `bench_order`: outfield substitutes in positions 13–15, preserving official order.
- `player_positions`: mapping from player ID to one of `GK`, `DEF`, `MID`, `FWD`, sourced from the same FPL bootstrap-static element metadata used by capture.
- `captain_id` and `vice_captain_id`: both must be distinct members of the starting XI.
- `active_chip`: normalized chip or null.
- Existing field weight, rank stratum, and FIELD role.

The public GitHub Actions workflow must continue to publish aggregate EO only. Manager-level artifacts remain explicit local private exports outside the repository and outside the aggregate artifact directory. The artifact must not contain entry IDs, manager names, or exact ranks. Squad combinations may still identify managers and must be treated as sensitive.

## Full-Gameweek scenario contract

A full-Gameweek scenario must include explicit player outcomes for the scenario's modeled player universe. Outcomes must include minutes and enough event data to derive FPL points, or an explicitly supplied validated FPL points total. Missing player outcomes must fail validation; missing outcomes must never silently mean zero minutes or zero points.

The scenario universe must cover all players in each candidate and field squad, not merely players from one fixture. Candidate and field portfolios must be scored against exactly the same scenario IDs and probabilities.

## Deterministic lineup scoring rules

1. Start with the submitted starting XI and its formation.
2. A player who counts as having played is unavailable for autosubstitution. Positive minutes always count as played; a card-only appearance may also count as played even with zero minutes. A player who has played remains in the XI, even if substituted during the match.
3. If the starting goalkeeper has zero minutes, replace only with the reserve goalkeeper if that goalkeeper has positive minutes.
4. For outfield absences, process the three outfield substitutes in their submitted bench order. A substitute may enter only if the resulting XI remains a legal FPL formation: at least 3 DEF, 2 MID, and 1 FWD, with one goalkeeper.
5. The starting captain receives the normal additional captain multiplier only if they play at least one minute. Otherwise the vice-captain receives it only if they play at least one minute. If neither plays, there is no captain bonus.
6. Triple Captain applies the additional captain multiplier to the active captain (captain or vice-captain fallback), making the total player multiplier 3x rather than 2x.
7. Bench Boost scores all 15 players, including the reserve goalkeeper and all outfield substitutes; normal captaincy rules still apply.
8. Ordinary scoring includes only the final legal XI plus captain bonus. Bench players score nothing unless autosubstituted.
9. Free Hit uses the same lineup and scoring rules but is a separately labelled mode. It must never be inferred from the existence of a Free Hit chip in a hypothetical or field portfolio. The default mode remains `REGULAR_GW`.

The implementation must encode the official rules as explicit deterministic functions and unit tests. It must not rely on undocumented assumptions about ordering or formation legality.

## Required validation and tests

- Valid lineup reconstruction from positions 1–15 and bootstrap player types.
- Reject missing/duplicate vice-captain, invalid starting goalkeeper, or invalid reserve goalkeeper.
- Goalkeeper autosubstitution only when the starting goalkeeper does not play.
- First eligible outfield substitute enters in bench order.
- A substitute is skipped when they would create an illegal formation; later eligible substitutes are considered.
- No autosubstitution for players who appear for at least one minute.
- Captain fallback to vice-captain only when the captain does not play.
- No captain bonus when neither captain nor vice-captain plays.
- Triple Captain multiplier on captain and vice-captain fallback.
- Bench Boost includes all 15 players and does not double-count players.
- Regular Gameweek default; Free Hit requires explicit mode.
- Candidate and field scores use identical scenario distributions.
- Existing fixture-slice tests remain unchanged and passing.
- Privacy tests confirm manager IDs, names, and exact ranks are absent from the exported artifact.

## Non-goals and safeguards

- No production recommendation or decision-weight changes: `decision_weight=0`, `production_eligible=false`.
- No changes to M3 EV, legality, transfer logic, frozen decisions, decision hashes, or conventional M5 recommendations.
- No inference of joint manager portfolios from marginal EO.
- No upload, commit, or workflow artifact of manager-level portfolios.
- No real-world scoring validation until synthetic rules tests pass and an independently sourced FPL rules audit is complete.
- No PR merge without explicit approval.

## Delivery sequence

1. Extend the private portfolio artifact with lineup semantics and bootstrap-derived player positions.
2. Add a standalone, pure automatic-substitution/lineup-resolution module with exhaustive edge-case tests.
3. Extend the synthetic scenario contract to carry full-Gameweek outcomes and validate player coverage.
4. Add full-Gameweek scoring that reuses the same scenario distribution for candidate and field portfolios.
5. Add integration fixtures, privacy checks, documentation, and CI validation.
6. Keep the full-Gameweek engine synthetic-only until the implementation and rule audit are complete.

## Standalone lineup resolver implementation

The deterministic resolver is implemented in `scripts/m4_covar_lineup_resolver.py`
and tested independently in `tests/test_m4_covar_lineup_resolver.py`.

Its input is one explicit 15-player squad, lineup/bench order, position map,
captain and vice-captain, plus complete per-player minutes, explicit Gameweek played-status booleans, and
FPL-points maps for one scenario. Missing outcomes fail closed; minutes must
be finite and between 0 and 120; points may be negative. A player with positive
minutes must be marked as played, while a zero-minute player may still be
marked as played for a card-only appearance, consistent with current FPL guidance.

Resolution behavior:

- The starting goalkeeper is replaced only when they did not count as having
  played and the reserve goalkeeper did count as having played.
- Outfield substitutes are considered in submitted bench order. For each
  playing substitute, the resolver replaces the earliest still-unreplaced
  absent starting outfielder for which the resulting formation meets the
  minimum 3 DEF / 2 MID / 1 FWD constraints. An ineligible substitute is
  skipped and later bench players are still considered.
- Any starter who counts as having played remains in the XI, including a player
  substituted off during the match or a card-only appearance. Explicit played
  status, not minutes alone, governs autosubs and captain fallback.
- Captaincy falls back to the vice-captain only when the captain did not count
  as having played. No bonus is awarded if neither plays. The 3xc chip applies a 3x
  total multiplier; otherwise the active captain receives 2x.
- The bboost chip scores all 15 players exactly once, while retaining the
  normal captain/vice-captain bonus. Other recognized chips do not alter this
  resolver's scoring behavior.
- `mode` defaults to `REGULAR_GW`; `FREE_HIT` must be explicitly supplied.
  Mode is a label here, not an inferred chip effect.

The resolver returns the resolved XI, substitutions, active captain, player
contributions and total points. It remains synthetic research code with
`decision_weight=0` and `production_eligible=false`; it is not yet connected
to full-Gameweek scenario scoring.
