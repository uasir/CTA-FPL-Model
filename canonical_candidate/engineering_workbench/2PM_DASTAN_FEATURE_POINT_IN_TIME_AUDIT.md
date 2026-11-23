# 2PM — Dastan Feature Point-in-Time and Semantics Audit

**Date:** 2026-11-23  
**Status:** Source inspection; no row-level feature comparison or admission  
**Pinned upstream:** `qazybekb/smartplayfpl-dastan@758db9247e8b3a9a870c991064f74d8339d61cd0`

## 1. Purpose

This note extends the deadline-scope correction with exact source semantics for feature families whose timing or meaning is not established by the existing player-Gameweek anchoring assertion. It does not claim measured contamination. All 286 columns remain HOLD for 2PM until the independent deadline rebuild and feature admission review are complete.

## 2. Feature-family point-in-time assessment

| Family / columns | Upstream construction | 2PM point-in-time decision |
|---|---|---|
| `player_*` (115) | Player rolling means over five windows, shifted one player-fixture row in kickoff order | Candidate. Rebuild at official deadline using corrected player identity and actual completed prior matches. |
| `team_*` (60) | Team rolling means over five windows, shifted by team kickoff order; joined to player rows by team/date | Candidate. Existing anchor includes this prefix but is not a global official-deadline reconstruction. |
| `opp_*` (60) | Opponent team's rolling means joined by opponent/date | HOLD. Explicitly excluded from anchor; a preceding same-GW opponent fixture can enter a later target fixture's features. |
| `status_league_rank`, `opp_status_league_rank` (2) | Direct league rank values generated from standings accumulated before each kickoff date | HOLD. Outside anchor selector; rebuild standings strictly at official deadline. |
| `p_any_*`, `p60_*`, `e_minutes_*` (9) | Prior player appearance/minutes rolling means, grouped by FPL code and season, with position baseline fallbacks | Candidate. Recompute from pre-deadline player history; document season reset and cold-start semantics. |
| `ar_defensive_contribution_*`, `ar_cbit_*`, `ar_recoveries_*`, `ar_tackles_*` (16) | Lagged player rolling means over 3/5/10/38 fixture rows | Candidate only from seasons where source stats exist; preserve unavailable vs zero and rebuild after corrected identity. |
| `ar_dc_hit_rate_*`, `ar_dc_near_rate_*`, `ar_dc_ppg_5`, `ar_starts_*` (10) | Lagged threshold/start rates from player fixture rows | Candidate. Verify source availability, position thresholds, missingness and identity grouping. |
| `ar_opp_dc_allowed_*`, `ar_opp_tackles_allowed_5` (4) | Opponent defensive workload aggregated by fixture/conceding team, shifted in kickoff order and joined to the player's opponent | HOLD. Can contain a same-GW post-deadline opponent result; per-player anchoring can also carry first-fixture opponent context to a different DGW opponent. |
| `ar_rest_days` (1) | Difference between current and previous player-row kickoff timestamps, clipped to 1–14 days | HOLD pending semantic decision. It uses the previous fixture row, not the previous appearance (no minutes filter), and actual kickoff timestamps rather than a verified deadline-time state. |
| `ar_team_matches_14d` (1) | Count of earlier EPL team fixture kickoffs within 14 days | Candidate only after deadline schedule audit; EPL-only and not all-competition workload. |
| `ar_ep_next` (1) | Joined from the separate archived FPL pre-deadline `ep_next` artifact; missing values become -1 | Strong provenance candidate. Re-verify snapshot manifest, deadline and coverage for the exact 2PM dataset vintage. |
| `sig_status_risk`, `sig_chance_playing`, `sig_has_news` (3) | Joined from separate archived FPL bootstrap snapshots | Strong provenance candidate. Snapshot must name GW as `is_next`, match official deadline and predate it. |
| `value`, `selected`, `transfers_balance` (3) | Carried from archived FPL per-player Gameweek history rows | HOLD. The rebuild path does not validate a capture timestamp for these fields. Establish exact temporal meaning and compare with archived pre-deadline bootstrap values; otherwise rebuild or exclude. |
| `is_home_num` (1) | Fixture venue flag | Candidate. Verify against the official fixture schedule as known at deadline, including rescheduled fixtures. |

The family counts above reconcile to 286: 115 + 60 + 60 + 2 + 9 + 16 + 10 + 4 + 1 + 1 + 1 + 3 + 3 + 1 = 286.

## 3. Additional confirmed source semantics

### 3.1 Historical FPL market fields are not covered by the snapshot provenance check

In `dastan/rebuild/sources.py`, canonical FPL player rows are read from Vaastav's season `gws/merged_gw.csv`. The builder carries `value`, `selected` and `transfers_balance` into the feature frame through the FPL rows. It separately sets `expected_points_pre_deadline` to a placeholder and comments that Vaastav's xP is not provenance-safe. The verified `ep_next` and availability snapshots are reconstructed separately by `dastan/rebuild/fplcache.py`.

The latter snapshot acceptance logic does not establish the capture time represented by `value`, `selected` or `transfers_balance` in the historical Gameweek rows. Their presence in a historical FPL record is not sufficient proof that each value was known at the deadline. Keep all three HOLD until a field-by-field timestamp and vintage comparison is completed.

### 3.2 Pre-deadline projections and signals have a distinct provenance path

The upstream `fplcache` builder selects a snapshot captured before the deadline (with a five-minute safety buffer), requires the target Gameweek to be marked `is_next`, and checks that the snapshot deadline matches the event calendar. The released model's `ar_ep_next` is populated by joining that separate artifact; it is not the zero placeholder `expected_points_pre_deadline` in the raw rebuilt match table.

The 2PM adapter must use the accepted snapshot artifact and preserve `-1` as missing, distinct from a genuine zero. Do not source these values from the Vaastav historical row or use the raw `expected_points_pre_deadline` placeholder.

### 3.3 Rest and congestion features have narrower meanings than their labels suggest

- `ar_rest_days` is calculated from the difference between the current player-row kickoff and the previous player-row kickoff. The source does not filter the previous row by `minutes > 0`; it is therefore not strictly days since the player's previous played match.
- `ar_team_matches_14d` counts Premier League fixture kickoffs only. It does not represent all-competition workload, and the upstream feature documentation itself identifies this limitation.

These are semantic/model-design questions even if no deadline leakage is found. The 2PM feature definition must not relabel either measure as a broader physical-load or played-match measure.

## 4. Current 2026/27 mapping snapshot reconciliation

The pinned upstream documentation is internally inconsistent about current-roster coverage:

- `docs/DATA.md` says 627 of 654 players are mapped.
- `data/mappings/README.md` says 518 of 577.
- Direct counting of `data/mappings/fpl_understat_current.csv` at the pinned commit (blob SHA `9564eeed46ad0a138ebb91ba99ece0c9a6278b53`) gives 654 roster rows: 626 with `mapping_status=mapped`, 1 with `shared_understat_id`, and 27 `unmapped`. Thus 627/654 are mapped if the shared-ID row is counted as mapped.

For 2PM readiness, use the file-level count (626 mapped + 1 shared = 627 mapped; 27 unmapped) and record the exact file hash. Treat the README's 518/577 statement as stale documentation for this pinned snapshot. This remains a captured 2026/27 roster mapping, not a current live count and not a 2026/27 player-fixture feature frame.

## 5. Required tests before admission

1. Independently reconstruct every candidate feature at each official FPL deadline using only source records whose information timestamp is at or before that deadline.
2. For each of the 286 columns, report release/candidate coverage, null/zero distinction, exact differences, tolerance differences, and source timestamp provenance by season/GW.
3. Explicitly test `opp_*`, direct ranks and `ar_opp_*` on double Gameweeks, opponent double fixtures, postponed/rescheduled fixtures and same-day kickoffs.
4. Compare `value`, `selected` and `transfers_balance` against archived pre-deadline bootstrap snapshots; document any field that cannot be independently matched.
5. Rebuild player rolling history under the corrected historical identity assignments; quantify player-fixture rows and rolling histories affected.
6. Publish season-level availability for defensive-contribution features and distinguish not-collected from true zero.
7. Decide whether to redefine or exclude `ar_rest_days` and `ar_team_matches_14d` for 2PM's five-previous-played-match sequence.

## 6. Decision

- No feature is admitted by this note.
- Keep all 286 features HOLD until independent point-in-time and semantic validation.
- Treat `ar_ep_next` and the three `sig_*` fields as the strongest provenance-backed candidates, subject to exact artifact verification and model-specific utility testing.
- Do not treat `value`, `selected`, `transfers_balance`, `opp_*`, direct rank or `ar_opp_*` as deadline-safe based on the existing Dastan assertion.
- Do not begin model training or freeze the 286-column schema on the basis of this source inspection.

**Gate:** `DASTAN_286_ADAPTATION_AUDIT_IN_PROGRESS`.
