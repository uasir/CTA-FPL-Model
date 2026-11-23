# 2PM — Dastan Deadline Audit: Scope Correction

**Date:** 2026-11-23  
**Status:** Source-level finding; row-level leakage not quantified  
**Pinned upstream:** `qazybekb/smartplayfpl-dastan@758db9247e8b3a9a870c991064f74d8339d61cd0`

## 1. Why this note exists

The upstream `docs/DATA.md` says every fixture in a Gameweek carries the history available at the common FPL deadline and says `data.assert_deadline_anchored` enforces that property. Direct inspection of the pinned implementation shows that the assertion enforces a narrower condition: equality of a selected set of feature columns within each player-Gameweek. It is not a reconstruction against the official deadline timestamp and does not validate all 286 model inputs.

The same `dastan/data.py` and `dastan/rebuild/features.py` blob SHAs were observed on the pinned commit and current upstream `main` during this audit. The source-level limitation is therefore not explained by an old pin alone.

## 2. Exact implementation evidence

### 2.1 The checked column selector is incomplete

In `dastan/data.py`, `HISTORY_PREFIXES` is:

- `player_`
- `team_`
- `ar_`
- `cx_`
- `p_any_`
- `p60_`
- `e_minutes_`

The default `anchor_to_deadline` and `assert_deadline_anchored` both select columns using that same prefix tuple. The source comment explicitly says `opp_` is deliberately excluded. The 286-feature schema also contains the direct columns `status_league_rank` and `opp_status_league_rank`, neither of which matches the selected prefixes.

Consequently, the assertion can establish that selected columns have one value per player-Gameweek. It cannot establish deadline safety for all 286 features, and it does not establish that a selected value was calculated using only events completed before the official deadline.

### 2.2 Opponent and rank features are built at fixture-date granularity

In `dastan/rebuild/features.py`:

- `compute_league_ranks` calculates a table before each kickoff-date group, then applies that rank to fixtures at that date and updates standings after the group.
- `compute_team_rolling` calculates rolling team features in date order and creates direct `status_league_rank` / `status_opp_league_rank` fields.
- The feature-frame builder joins own-team and opponent-team feature rows using the calendar date of each target fixture.
- Opponent rolling features are renamed to the `opp_*` namespace and joined separately by opponent and fixture date.

This preserves fixture-specific opponent context, but it also means a later fixture date can see matches completed earlier in the same Gameweek unless the values are independently rebuilt at the common FPL deadline. The current anchor assertion does not inspect those `opp_*` or direct rank fields.

### 2.3 Some `ar_*` fields need a semantic audit, not just a leakage test

The `ar_*` prefix is included in the anchor selector. This includes `ar_opp_dc_allowed_3/5/10` and `ar_opp_tackles_allowed_5`. These are opponent-conditioned features created by aggregating defensive contributions by fixture and conceding team, then rolling in kickoff order.

Broadcasting the earliest row's `ar_*` value across a player's Gameweek may prevent later same-Gameweek results from entering the value, but it can also copy the first fixture opponent's allowance context onto another fixture with a different opponent. This is a distinct semantic/fixture-alignment risk. Do not label it a confirmed leak or assume the broadcast is correct without checking both the deadline and opponent identity.

Other kickoff-derived fields such as `ar_rest_days` and `ar_team_matches_14d` are also subject to the question of whether their source events precede the official deadline. Equality within a player-Gameweek is not a substitute for that test.

## 3. What is confirmed and what is not

| Finding | Status |
|---|---|
| The anchor/assertion use the same selected prefix set | Confirmed in source |
| All `opp_*` columns are outside the assertion | Confirmed in source |
| Direct `status_league_rank` and `opp_status_league_rank` are outside the assertion | Confirmed in source |
| Opponent and rank construction is fixture-date/kickoff ordered | Confirmed in source |
| `ar_opp_*` values are anchored but may be misaligned to a different DGW opponent after broadcasting | Structural semantic risk; row-level impact unmeasured |
| Any specific released feature value contains a post-deadline result | Not yet established |
| Number or percentage of affected rows/features | Not quantified |

The documented 6,958 multi-fixture player-Gameweeks and 40.6% pre-fix difference refer to differences in the selected rolling columns before the anchoring correction. They are not a measurement of residual leakage after the correction and do not quantify the omitted opponent/rank fields.

## 4. Required independent audit

For every target season/Gameweek, use the archived official FPL deadline timestamp. Reconstruct the candidate feature vector from canonical source events whose completion timestamps are strictly before that deadline.

The audit must:

1. Keep each target fixture's opponent identity and home/away context.
2. Recompute opponent form and opponent defensive allowance using only events completed before the common deadline.
3. Recompute league ranks from standings at the deadline, before any same-Gameweek fixture result.
4. Recompute own-team rolling form and congestion/rest features from eligible pre-deadline events.
5. Check the `ar_opp_*` features for both deadline correctness and alignment to the correct opponent for each fixture.
6. Compare all 286 columns row-by-row against the release, with missingness and numeric differences reported by season, Gameweek, feature and fixture.
7. Include double Gameweeks, postponed/rescheduled fixtures, same-day and simultaneous kickoffs, blanks, transfers, and season boundaries.

Do not apply a blanket first-row broadcast to every feature family. Opponent-conditioned features require fixture-specific identity plus deadline-safe historical form.

## 5. 2PM decision

- Keep all 286 columns on HOLD.
- Treat the upstream release as a useful historical candidate frame, not yet as a fully independently certified deadline-safe 2PM dataset.
- Do not claim a quantified leakage rate.
- Do not admit `opp_*`, direct rank, or `ar_opp_*` features until their deadline and fixture-alignment semantics are independently verified.
- Preserve the corrected historical identity mapping requirement and current-season build requirement in the existing readiness and source-semantics records.
- No 2PM model code, sequence builder, training, or evaluation is authorized by this audit note.

**Gate:** `DASTAN_286_ADAPTATION_AUDIT_IN_PROGRESS`.
