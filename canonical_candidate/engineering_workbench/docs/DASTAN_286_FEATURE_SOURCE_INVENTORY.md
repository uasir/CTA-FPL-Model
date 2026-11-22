# Dastan 286-Feature Source Inventory

**Purpose:** Reproduce the exact Dastan minutes-model input frame for CTA. This is an engineering inventory, not a claim that the CTA feature builder is complete.

**Pinned contract:** `config/dastan_minutes_feature_schema.json` (286 ordered columns).

## 1. Exact schema composition

Counts below are computed from the pinned `feature_order` in CTA's schema artifact, not copied from the upstream prose summary.

| Feature group | Columns | Count | Primary source / construction |
|---|---|---:|---|
| Player rolling | `player_*` | 115 | FPL player-match statistics plus Understat player attacking metrics; 23 source metrics × 5 windows |
| Own-team rolling | `team_*` | 60 | Understat team-match metrics and pre-match league ranks; 12 metrics × 5 windows |
| Opponent rolling/context | `opp_*` | 61 | Opponent Understat team-match rolling metrics plus opponent rank context |
| Availability history | `p_any_*`, `p60_*`, `e_minutes_*` | 9 | Lagged FPL appearances, 60+ minute appearances, and minutes; windows 3, 5, 10 |
| Dastan engineered/context | `ar_*` | 33 | Lagged defensive contribution, CBIT, recoveries, tackles, threshold rates, starts, rest/congestion, opponent defensive allowance, and `ar_ep_next` |
| Flat context | Remaining non-signal scalar fields | 5 | Venue, league-rank/context, price, ownership, transfer balance |
| Pre-deadline availability | `sig_*` | 3 | FPL bootstrap status risk, chance of playing, news presence |
| **Total** | | **286** | |

The upstream `docs/FEATURES.md` family table does not reconcile arithmetically to 286 as currently written. CTA's pinned feature list is the executable schema authority; the source-family table above is grouped from that list and should be refined against the exact upstream build code.

## 2. Source and transformation inventory

### A. FPL player-match history

Used by player rolling features and availability history:

- FPL points, minutes, influence, creativity, threat, goals, assists, cards, own goals, saves, penalty events, BPS and bonus.
- FPL defensive contribution, CBIT, recoveries and tackles where available (introduced in 2025-26).
- Start indicators derived from minutes / source match records.
- Lagged rolling means use windows 1, 3, 5, 10 and 38 for player metrics; availability uses 3, 5 and 10.
- Player identity across seasons must use stable `fpl_code`; season-specific `element` IDs are not cross-season identities.

### B. Understat player-match history

Used for player rolling attacking metrics:

- Shots, xG, xA, xGChain, xGBuildup and key passes.
- Join requires audited FPL-to-Understat player identity plus match/date alignment.
- Missing or ambiguous mappings must be surfaced; do not guess by display name alone.

### C. Understat team-match history

Used for own-team and opponent rolling blocks:

- Goals scored/conceded, xG/xGA, deep/deep allowed, PPDA attack/defence and allowed variants.
- Opponent pairing is reconstructed from same-slot home/away team rows using score and xG consistency.
- League rank is calculated from standings accumulated before each match.
- Rolling means use windows 1, 3, 5, 10 and 38.
- Team names require a controlled FPL-to-Understat normalization map.

### D. Dastan engineered features

- Availability history: prior match played, prior match 60+, and prior minutes, grouped by player and season. Position-specific base rates fill the cold-start rows.
- Defensive contribution family: prior rolling averages for defensive contribution, CBIT, recoveries and tackles; defensive-contribution hit/near rates use position-specific thresholds; prior starts rates; defensive contribution points proxy.
- Rest/congestion: days since prior Premier League fixture and team matches in the preceding 14 days.
- Opponent defensive allowance: prior opponent defensive-contribution and tackle totals allowed.
- `ar_ep_next`: provenance-checked FPL `ep_next` captured before the target deadline.

### E. Pre-deadline FPL bootstrap signals

- `sig_status_risk`, `sig_chance_playing`, `sig_has_news`.
- A snapshot is eligible only when it identifies the target GW as next, its deadline matches the official deadline, and capture time is strictly before that deadline.
- These values are snapshot fields, not retrospective current-bootstrap values.

## 3. Temporal and missing-value rules

- Every rolling feature is shifted so the target fixture's result cannot enter its own input.
- All fixtures for the same player in one Gameweek share the same deadline-anchored historical player/team state. Opponent/venue context may differ by fixture.
- Do not let an earlier fixture in a double Gameweek update the features for a later fixture from the same deadline.
- Dastan's loader fills absent pre-deadline snapshot artifact values with `-1.0`.
- Dastan's training matrix fills remaining NaNs with `0.0`; the released inference path applies the same residual NaN-to-zero fill.
- CTA must reproduce the source-specific `-1.0` sentinel stage and then the residual NaN `0.0` fill. Never globally replace all missing values with one constant.
- A genuine zero must remain distinguishable from an unavailable snapshot sentinel.

## 4. Deadline-safety classification for CTA

| Source family | Deadline-safe construction | Main failure mode to guard against |
|---|---|---|
| FPL historical match stats | Use only matches completed before target deadline | Same-GW/double-GW leakage; revised or incomplete history |
| Understat player/team stats | Use only matches completed before deadline; pin/retrieve historical snapshots where possible | Mutable historical corrections; wrong identity or match join |
| Availability history | Derive only from prior completed FPL matches | Same-GW fixture ordering leakage |
| Price / ownership / transfer balance | Use an archived pre-deadline FPL bootstrap vintage | Current values substituted for historical values |
| `ep_next` and `sig_*` | Require target-GW marker, matching deadline, pre-deadline capture timestamp | Post-deadline snapshot or wrong GW association |
| Rest/congestion | Calculate from prior PL fixture schedule only, matching upstream semantics | Omitting cup/European fixtures; do not silently change definition |

## 5. Implementation sequence

1. Reproduce the canonical raw player-match and team-match tables with stable identities and explicit source timestamps.
2. Implement player rolling and availability features.
3. Implement team/opponent rolling features and rank calculations.
4. Implement Dastan engineered defensive/context features.
5. Add pre-deadline snapshot features with strict provenance checks.
6. Apply deadline anchoring across all same-GW fixtures.
7. Apply source-specific missing-value rules, exact 286-column ordering, and row-level coverage diagnostics.
8. Compare reconstructed rows and values against the released feature frame where available; document expected drift from mutable source histories.

**Current status:** Source families and major transformations are identified. Full source-table reconstruction, current-season mapping coverage, and row-level parity are not yet implemented or verified.
