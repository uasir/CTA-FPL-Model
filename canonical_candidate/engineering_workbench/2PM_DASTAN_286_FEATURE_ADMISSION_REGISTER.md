# 2PM — Dastan 286-Feature Admission Register

**Status:** Initial schema inventory; all feature admissions on hold  
**Schema version:** `1.0.0`  
**Schema component:** `dastan_286_candidate_input` (2PM candidate adaptation; 2PM does not reuse the Dastan predictor)  
**Source schema commit:** `78b06b80a9adfa96b5b7691296b70b10512ee0e3`  
**Schema blob:** `053f499332f7e6eab6e7046bf4f0e847e3b57d1f`  
**Upstream Dastan reconstruction commit:** `758db9247e8b3a9a870c991064f74d8339d61cd0`  
**Feature count verified:** 286 unique ordered columns

## Purpose and interpretation

This is the 2PM-specific feature-by-feature admission register generated from the exact pinned `feature_order`. It records the full candidate column inventory without claiming that the features are already approved for 2PM.

The 286 columns were designed for a minutes model and represent engineered deadline-anchored player-fixture features. A family/source label below is a preliminary classification from the Dastan source inventory, not independent verification of every column's exact formula or historical vintage.

**No feature is admitted by this register.** Every row remains `HOLD` until its exact definition, lineage, rights, historical availability, leakage safety, missingness and sequence-token suitability are evidenced. Do not reduce or inflate the schema count to disguise exclusions.

## Group counts

| Family | Count |
|---|---:|
| Player rolling | 115 |
| Own-team rolling | 60 |
| Opponent rolling/context | 61 |
| Availability history | 9 |
| Dastan engineered/context | 32 |
| Pre-deadline FPL projection | 1 |
| Flat context | 5 |
| Pre-deadline availability | 3 |
| **Total** | **286** |

## Admission rules

- `ADMIT`: exact definition and source lineage verified; point-in-time availability, rights, coverage, leakage and sequence use cleared.
- `EXCLUDE`: feature is inappropriate or cannot be made safe for the approved 2PM representation; preserve rationale.
- `HOLD`: evidence incomplete. This is the initial status for all 286 columns.
- Historical market/snapshot values require deadline-specific archived vintages; current bootstrap data are not historical substitutes. A candidate rebuild adapter now sources `value`, `selected` and `transfers_balance` from accepted FPL cache snapshots with the matching official deadline and a five-minute safety buffer; unit parity and full historical coverage remain to be audited.
- Historical FPL/Understat corrections and identity mappings require pinned source snapshots/manifests.
- Preserve the upstream distinction between missing snapshot sentinel `-1.0`, residual NaN fill `0.0`, and genuine observed zero only where the source contract supports it.
- Target fixture outcomes must never enter that target's input.
- Sequence compatibility is a separate decision from feature availability. A valid rolling feature is not automatically a valid per-match sequence token.

## Related source-semantics audit

See `2PM_DASTAN_SOURCE_SEMANTICS_AUDIT.md` for the pinned source-code findings and mandatory temporal/identity checks. In particular, the upstream deadline-anchor routine does not include `opp_*`, `status_league_rank` or `opp_status_league_rank` in its anchored prefix set; these remain high-priority HOLD items pending row-level double-Gameweek tests.

## Feature-level register

| # | Exact schema column | Family | Preliminary source | Initial audit concern | 2PM admission |
|---:|---|---|---|---|---|
| 1 | `player_assists_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 2 | `player_assists_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 3 | `player_assists_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 4 | `player_assists_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 5 | `player_assists_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 6 | `player_bps_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 7 | `player_bps_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 8 | `player_bps_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 9 | `player_bps_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 10 | `player_bps_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 11 | `player_creativity_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 12 | `player_creativity_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 13 | `player_creativity_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 14 | `player_creativity_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 15 | `player_creativity_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 16 | `player_fpl_bonus_points_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 17 | `player_fpl_bonus_points_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 18 | `player_fpl_bonus_points_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 19 | `player_fpl_bonus_points_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 20 | `player_fpl_bonus_points_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 21 | `player_fpl_points_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 22 | `player_fpl_points_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 23 | `player_fpl_points_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 24 | `player_fpl_points_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 25 | `player_fpl_points_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 26 | `player_goals_conceded_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 27 | `player_goals_conceded_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 28 | `player_goals_conceded_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 29 | `player_goals_conceded_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 30 | `player_goals_conceded_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 31 | `player_goals_scored_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 32 | `player_goals_scored_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 33 | `player_goals_scored_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 34 | `player_goals_scored_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 35 | `player_goals_scored_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 36 | `player_influence_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 37 | `player_influence_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 38 | `player_influence_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 39 | `player_influence_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 40 | `player_influence_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 41 | `player_key_passes_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 42 | `player_key_passes_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 43 | `player_key_passes_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 44 | `player_key_passes_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 45 | `player_key_passes_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 46 | `player_minutes_played_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 47 | `player_minutes_played_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 48 | `player_minutes_played_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 49 | `player_minutes_played_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 50 | `player_minutes_played_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 51 | `player_own_goals_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 52 | `player_own_goals_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 53 | `player_own_goals_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 54 | `player_own_goals_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 55 | `player_own_goals_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 56 | `player_penalties_missed_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 57 | `player_penalties_missed_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 58 | `player_penalties_missed_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 59 | `player_penalties_missed_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 60 | `player_penalties_missed_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 61 | `player_penalties_saved_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 62 | `player_penalties_saved_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 63 | `player_penalties_saved_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 64 | `player_penalties_saved_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 65 | `player_penalties_saved_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 66 | `player_red_cards_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 67 | `player_red_cards_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 68 | `player_red_cards_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 69 | `player_red_cards_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 70 | `player_red_cards_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 71 | `player_relevant_fpl_points_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 72 | `player_relevant_fpl_points_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 73 | `player_relevant_fpl_points_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 74 | `player_relevant_fpl_points_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 75 | `player_relevant_fpl_points_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 76 | `player_saves_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 77 | `player_saves_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 78 | `player_saves_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 79 | `player_saves_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 80 | `player_saves_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 81 | `player_shots_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 82 | `player_shots_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 83 | `player_shots_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 84 | `player_shots_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 85 | `player_shots_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 86 | `player_threat_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 87 | `player_threat_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 88 | `player_threat_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 89 | `player_threat_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 90 | `player_threat_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 91 | `player_xa_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 92 | `player_xa_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 93 | `player_xa_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 94 | `player_xa_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 95 | `player_xa_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 96 | `player_xg_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 97 | `player_xg_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 98 | `player_xg_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 99 | `player_xg_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 100 | `player_xg_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 101 | `player_xgbuildup_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 102 | `player_xgbuildup_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 103 | `player_xgbuildup_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 104 | `player_xgbuildup_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 105 | `player_xgbuildup_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 106 | `player_xgchain_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 107 | `player_xgchain_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 108 | `player_xgchain_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 109 | `player_xgchain_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 110 | `player_xgchain_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 111 | `player_yellow_cards_1` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 112 | `player_yellow_cards_10` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 113 | `player_yellow_cards_3` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 114 | `player_yellow_cards_38` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 115 | `player_yellow_cards_5` | Player rolling | FPL player-match / Understat player-match | Player history; each rolling window must be reconstructed strictly before the relevant cutoff. | HOLD |
| 116 | `team_deep_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 117 | `team_deep_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 118 | `team_deep_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 119 | `team_deep_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 120 | `team_deep_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 121 | `team_deep_allowed_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 122 | `team_deep_allowed_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 123 | `team_deep_allowed_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 124 | `team_deep_allowed_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 125 | `team_deep_allowed_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 126 | `team_goals_conceded_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 127 | `team_goals_conceded_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 128 | `team_goals_conceded_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 129 | `team_goals_conceded_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 130 | `team_goals_conceded_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 131 | `team_goals_scored_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 132 | `team_goals_scored_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 133 | `team_goals_scored_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 134 | `team_goals_scored_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 135 | `team_goals_scored_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 136 | `team_league_rank_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 137 | `team_league_rank_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 138 | `team_league_rank_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 139 | `team_league_rank_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 140 | `team_league_rank_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 141 | `team_opponent_league_rank_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 142 | `team_opponent_league_rank_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 143 | `team_opponent_league_rank_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 144 | `team_opponent_league_rank_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 145 | `team_opponent_league_rank_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 146 | `team_ppda_allowed_att_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 147 | `team_ppda_allowed_att_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 148 | `team_ppda_allowed_att_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 149 | `team_ppda_allowed_att_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 150 | `team_ppda_allowed_att_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 151 | `team_ppda_allowed_def_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 152 | `team_ppda_allowed_def_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 153 | `team_ppda_allowed_def_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 154 | `team_ppda_allowed_def_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 155 | `team_ppda_allowed_def_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 156 | `team_ppda_att_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 157 | `team_ppda_att_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 158 | `team_ppda_att_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 159 | `team_ppda_att_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 160 | `team_ppda_att_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 161 | `team_ppda_def_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 162 | `team_ppda_def_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 163 | `team_ppda_def_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 164 | `team_ppda_def_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 165 | `team_ppda_def_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 166 | `team_xg_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 167 | `team_xg_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 168 | `team_xg_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 169 | `team_xg_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 170 | `team_xg_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 171 | `team_xga_1` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 172 | `team_xga_10` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 173 | `team_xga_3` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 174 | `team_xga_38` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 175 | `team_xga_5` | Own-team rolling | Understat team-match | Team-level context; not a player action. Verify historical rank and match cutoffs. | HOLD |
| 176 | `opp_deep_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 177 | `opp_deep_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 178 | `opp_deep_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 179 | `opp_deep_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 180 | `opp_deep_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 181 | `opp_deep_allowed_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 182 | `opp_deep_allowed_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 183 | `opp_deep_allowed_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 184 | `opp_deep_allowed_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 185 | `opp_deep_allowed_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 186 | `opp_goals_conceded_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 187 | `opp_goals_conceded_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 188 | `opp_goals_conceded_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 189 | `opp_goals_conceded_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 190 | `opp_goals_conceded_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 191 | `opp_goals_scored_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 192 | `opp_goals_scored_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 193 | `opp_goals_scored_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 194 | `opp_goals_scored_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 195 | `opp_goals_scored_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 196 | `opp_league_rank_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 197 | `opp_league_rank_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 198 | `opp_league_rank_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 199 | `opp_league_rank_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 200 | `opp_league_rank_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 201 | `opp_opponent_league_rank_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 202 | `opp_opponent_league_rank_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 203 | `opp_opponent_league_rank_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 204 | `opp_opponent_league_rank_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 205 | `opp_opponent_league_rank_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 206 | `opp_ppda_allowed_att_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 207 | `opp_ppda_allowed_att_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 208 | `opp_ppda_allowed_att_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 209 | `opp_ppda_allowed_att_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 210 | `opp_ppda_allowed_att_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 211 | `opp_ppda_allowed_def_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 212 | `opp_ppda_allowed_def_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 213 | `opp_ppda_allowed_def_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 214 | `opp_ppda_allowed_def_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 215 | `opp_ppda_allowed_def_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 216 | `opp_ppda_att_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 217 | `opp_ppda_att_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 218 | `opp_ppda_att_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 219 | `opp_ppda_att_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 220 | `opp_ppda_att_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 221 | `opp_ppda_def_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 222 | `opp_ppda_def_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 223 | `opp_ppda_def_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 224 | `opp_ppda_def_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 225 | `opp_ppda_def_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 226 | `opp_xg_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 227 | `opp_xg_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 228 | `opp_xg_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 229 | `opp_xg_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 230 | `opp_xg_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 231 | `opp_xga_1` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 232 | `opp_xga_10` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 233 | `opp_xga_3` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 234 | `opp_xga_38` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 235 | `opp_xga_5` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 236 | `is_home_num` | Flat context | FPL fixture + pre-match standings | Target-specific context; reconstruct from information available before target fixture. | HOLD |
| 237 | `status_league_rank` | Flat context | FPL fixture + pre-match standings | Target-specific context; reconstruct from information available before target fixture. | HOLD |
| 238 | `opp_status_league_rank` | Opponent rolling/context | Understat team-match | Opponent team-level context; verify fixture pairing and cutoff. | HOLD |
| 239 | `value` | Flat context | FPL deadline snapshot / schedule context | Price, ownership and transfer balance require archived pre-deadline vintages. | HOLD |
| 240 | `selected` | Flat context | FPL deadline snapshot / schedule context | Price, ownership and transfer balance require archived pre-deadline vintages. | HOLD |
| 241 | `transfers_balance` | Flat context | FPL deadline snapshot / schedule context | Price, ownership and transfer balance require archived pre-deadline vintages. | HOLD |
| 242 | `p_any_3` | Availability history | Lagged FPL player-fixture history | Derived from prior appearances/minutes; verify exact historical availability and no target-fixture leakage. | HOLD |
| 243 | `p_any_5` | Availability history | Lagged FPL player-fixture history | Derived from prior appearances/minutes; verify exact historical availability and no target-fixture leakage. | HOLD |
| 244 | `p_any_10` | Availability history | Lagged FPL player-fixture history | Derived from prior appearances/minutes; verify exact historical availability and no target-fixture leakage. | HOLD |
| 245 | `p60_3` | Availability history | Lagged FPL player-fixture history | Derived from prior appearances/minutes; verify exact historical availability and no target-fixture leakage. | HOLD |
| 246 | `p60_5` | Availability history | Lagged FPL player-fixture history | Derived from prior appearances/minutes; verify exact historical availability and no target-fixture leakage. | HOLD |
| 247 | `p60_10` | Availability history | Lagged FPL player-fixture history | Derived from prior appearances/minutes; verify exact historical availability and no target-fixture leakage. | HOLD |
| 248 | `e_minutes_3` | Availability history | Lagged FPL player-fixture history | Derived from prior appearances/minutes; verify exact historical availability and no target-fixture leakage. | HOLD |
| 249 | `e_minutes_5` | Availability history | Lagged FPL player-fixture history | Derived from prior appearances/minutes; verify exact historical availability and no target-fixture leakage. | HOLD |
| 250 | `e_minutes_10` | Availability history | Lagged FPL player-fixture history | Derived from prior appearances/minutes; verify exact historical availability and no target-fixture leakage. | HOLD |
| 251 | `ar_defensive_contribution_3` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 252 | `ar_defensive_contribution_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 253 | `ar_defensive_contribution_10` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 254 | `ar_defensive_contribution_38` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 255 | `ar_cbit_3` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 256 | `ar_cbit_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 257 | `ar_cbit_10` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 258 | `ar_cbit_38` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 259 | `ar_recoveries_3` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 260 | `ar_recoveries_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 261 | `ar_recoveries_10` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 262 | `ar_recoveries_38` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 263 | `ar_tackles_3` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 264 | `ar_tackles_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 265 | `ar_tackles_10` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 266 | `ar_tackles_38` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 267 | `ar_dc_hit_rate_3` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 268 | `ar_dc_hit_rate_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 269 | `ar_dc_hit_rate_10` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 270 | `ar_dc_near_rate_3` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 271 | `ar_dc_near_rate_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 272 | `ar_dc_near_rate_10` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 273 | `ar_dc_ppg_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 274 | `ar_starts_3` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 275 | `ar_starts_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 276 | `ar_starts_10` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 277 | `ar_rest_days` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 278 | `ar_team_matches_14d` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 279 | `ar_opp_dc_allowed_3` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 280 | `ar_opp_dc_allowed_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 281 | `ar_opp_dc_allowed_10` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 282 | `ar_opp_tackles_allowed_5` | Dastan engineered/context | Lagged FPL history + fixture/team context | Audit exact formula, source season coverage, temporal cutoff and whether it belongs in a historical sequence token. | HOLD |
| 283 | `ar_ep_next` | Pre-deadline FPL projection | Archived FPL bootstrap snapshot | Requires a target-GW-matched snapshot captured before deadline; historical vintages not yet verified. | HOLD |
| 284 | `sig_status_risk` | Pre-deadline availability | Archived FPL bootstrap snapshot | Requires historical target-GW snapshot and pre-deadline capture timestamp. | HOLD |
| 285 | `sig_chance_playing` | Pre-deadline availability | Archived FPL bootstrap snapshot | Requires historical target-GW snapshot and pre-deadline capture timestamp. | HOLD |
| 286 | `sig_has_news` | Pre-deadline availability | Archived FPL bootstrap snapshot | Requires historical target-GW snapshot and pre-deadline capture timestamp. | HOLD |

## Required evidence to close each row

For each feature, append or link evidence for:
1. canonical definition/formula and units;
2. source table/provider, source version, file/snapshot hash;
3. grain, entity key and match/fixture alignment;
4. rolling window and exact shift/lag semantics;
5. timestamp at which the value becomes available;
6. availability across historical target deadlines and seasons;
7. target leakage and same-GW/double-fixture controls;
8. data rights, retention and model-training permission;
9. missingness and imputation semantics;
10. sequence-token suitability and rationale;
11. final `ADMIT`, `EXCLUDE` or `HOLD` decision, reviewer and date.

## Current gate

`DASTAN_286_ADAPTATION_AUDIT_IN_PROGRESS`

This register is an inventory, not a frozen 2PM model schema. No sequence builder, training, model artifact, M3 integration or production use is authorized by its creation.
