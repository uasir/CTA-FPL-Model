# Dastan 286-Feature Source Inventory

**Purpose:** Reproduce the exact Dastan minutes-model input frame for CTA. This is an engineering inventory, not a claim that the CTA feature builder is complete.

**Pinned contract:** `config/dastan_minutes_feature_schema.json` (286 ordered columns).

## 1. Exact schema composition

Counts below are computed from the pinned `feature_order` in CTA's schema artifact, not copied from the upstream prose summary.

| Feature group | Columns | Count | Primary source / construction |
|---|---|---:|---|
| Player rolling | `player_*` | 115 | FPL player-match statistics plus Understat player attacking metrics; 23 source metrics × 5 windows |
| Own-team rolling | `team_*` | 60 | Understat team-match metrics and pre-match league ranks; 12 metrics × 5 windows |
| Opponent rolling/context | `opp_*` | 61 | 60 rolling opponent metrics (12 × 5 windows) plus `opp_status_league_rank` |
| Availability history | `p_any_*`, `p60_*`, `e_minutes_*` | 9 | Lagged FPL appearances, 60+ minute appearances, and minutes; windows 3, 5, 10 |
| Dastan engineered/context | `ar_*` | 32 | Defensive workload rolling stats, threshold rates, starts, rest/congestion and opponent defensive allowance |
| Pre-deadline FPL projection | `ar_ep_next` | 1 | Provenance-checked pre-deadline FPL `ep_next` snapshot |
| Flat context | `is_home_num`, `status_league_rank`, `value`, `selected`, `transfers_balance` | 5 | Venue, own-team rank, price, ownership, transfer balance |
| Pre-deadline availability | `sig_*` | 3 | FPL bootstrap status risk, chance of playing, news presence |
| **Total** | | **286** | |

The upstream `docs/FEATURES.md` family table does not reconcile arithmetically to 286 as currently written (its published family counts sum to 274). CTA's pinned feature list is the executable schema authority. The reconciled count above separates `ar_ep_next` from the 32 `ar_*` engineered features.

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
- `ar_ep_next`: provenance-checked FPL `ep_next` captured before the target deadline. It is named with the `ar_` prefix but is a separate source snapshot feature, not calculated by `add_dastan_features()`.

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


## 6. Identity coverage: do not mix mapping populations

The upstream repository exposes three different mapping populations, and their coverage figures must not be combined:

- **Frozen training mapping:** the historical identities used to reproduce the released model frame.
- **Corrected historical mapping:** an audited correction of that model-era population.
- **Operational registry/current-roster projection:** a newer mapping release used for new-season ingestion.

The pinned operational manifest dated 2026-09-07 reports 1,738 registry players, 1,686 mapped, 52 unmapped, and one shared Understat ID. That is the global operational registry, not the 2026-27 roster coverage. The current-roster CSV is a separate season-scoped projection. The upstream mapping README and DATA documentation report different current-roster coverage snapshots (518/577 versus 627/654), so CTA must calculate coverage directly from the exact pinned `fpl_understat_current.csv` artifact and its matching roster, not copy either prose figure.

For CTA's active-season build, retain one row per `(season, fpl_code)`, nullable Understat ID, mapping status, confidence, source manifest ID and source hash. Reject duplicate FPL codes; explicitly flag shared Understat IDs; never fill an unmapped ID with a name-based or fuzzy match. Unmapped players may still receive FPL-only features, but Understat-dependent features must retain their missingness state and be handled through Dastan's exact input policy.
