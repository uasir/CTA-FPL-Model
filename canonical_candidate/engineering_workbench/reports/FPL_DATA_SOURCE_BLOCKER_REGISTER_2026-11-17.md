# FPL data-source blocker register — 2026-11-17

## Executive status

The data pipeline can now preserve historical **global ownership counts** from FPL's per-player history, and a tested estimator exists for **sampled effective ownership (EO)** from deadline-locked manager picks. These are different measures:

- Global ownership: a player is selected by a share of all ranked FPL entries.
- Effective ownership: selected starting-lineup exposure plus captain and Triple Captain exposure, measured within a defined rank cohort.

Neither is interchangeable with current `selected_by_percent` in bootstrap-static.

## 1. Point-in-time FPL data

### What exists

The official FPL workflow runs daily at 05:30 UTC and fetches:
- `bootstrap-static`
- `fixtures`
- Per-player `element-summary` history

Each run records fetch time and SHA-256 hashes, and uploads normalized rows plus the raw bootstrap and fixture feeds. The artifact retention has now been extended from 30 to **90 days**.

The daily workflow is useful for capturing snapshots before some gameweek deadlines, but it does not guarantee a snapshot immediately before every deadline. GitHub Actions schedules are best-effort. A 90-day artifact window is also not a durable full-season archive.

### Storage decision

The CTA repository is public. Do not commit raw FPL API snapshots or user-specific manager picks into its public Git history as a workaround for artifact expiry.

A durable archive needs a private user-controlled storage destination. Dropbox was identified as an available connection option and suggested to the user; it is not connected yet. Until a private destination is connected, workflow artifacts remain the temporary evidence store. No claim of a complete season-long point-in-time archive is allowed.

### Backtest policy

A feature row may be called point-in-time verified only when it can be reconstructed from a source snapshot captured no later than its target deadline. A current API snapshot with kickoff-filtered historical rows is structurally lagged, but is not enough to prove that prior values were not retrospectively revised.

## 2. Historical global ownership

FPL per-player `element-summary.history[]` records include a `selected` count for each gameweek. The matching `bootstrap-static.events[].ranked_count` provides the ranked-entry denominator for that gameweek. This allows:

`historical_global_ownership_pct = 100 * selected / ranked_count`

The ingestion adapter has been extended to retain:
- `selected`
- `transfers_balance`
- `transfers_in`
- `transfers_out`
- `value`

It now requests element summaries for the full FPL roster, not only players with positive minutes, so the historical ownership coverage is not restricted to active-minute players.

The lagged feature builder uses only ownership from earlier gameweeks and adds:
- `prior_gw_selected_count`
- `prior_gw_selected_pct`
- `prior3_gw_selected_pct_avg`
- `prior5_gw_selected_pct_avg`

It validates that a player's selected count is consistent across all fixtures in the same gameweek. These are global ownership features, **not EO**, and remain subject to source-vintage caveats until the relevant pre-deadline snapshots are durably stored.

## 3. Effective ownership

### Formula and estimator

A tested adapter now accepts one row per manager-player pick, including manager ID, rank-sample weight, pick position, captain flag, and active chip. It computes weighted EO as:

`EO% = 100 × (starting selections + captain extras + Triple Captain extras) / sampled manager weight`

Rules:
- Normal gameweek: positions 1–11 count as selected starters.
- Bench Boost: all 15 count as selected starters.
- Captain adds one extra exposure unit.
- Triple Captain adds a second extra exposure unit.

The output is explicitly labelled `SAMPLE_ESTIMATE_NOT_GLOBAL_CENSUS`. It does not fetch manager picks or choose a rank cohort itself.

### Candidate sources reviewed

- Fantasy Football Pundit documents a live top-10k EO table soon after the deadline and a top-100k view later, with the formula above. Its public page is a live table, not a documented historical bulk API or a reusable licensed archive.
- LiveFPL publishes gameweek-by-gameweek top-10k ownership and captaincy summaries on its site. The accessible page contains historical tables for a prior season, but no bulk API or explicit data licence was established in this audit.
- The public `Unholy-smoke/fpl-mirror` repository records frequent API snapshots and daily global ownership CSVs, but GitHub reports no recognized repository licence. Its README also describes personal entry and mini-league data. Do not ingest or redistribute its files without permission.
- The `selected` history count from the official FPL feed is the cleanest current route to historical global ownership, but it cannot by itself provide rank-tier captaincy and Triple Captain exposure.

### Next EO data acquisition step

Use either:
1. an authorized source that supplies rank-tier ownership and captaincy by gameweek; or
2. a carefully sampled set of public FPL manager picks, where the rank cohort is selected using standings captured **before** the target deadline and the picks are fetched after the deadline.

Do not define the cohort using post-gameweek ranks; that would introduce lookahead bias. Do not treat a top-10k or top-100k sample as whole-game EO.

## 4. Player-level event data aligned to FPL

### StatsBomb Open Data

The current StatsBomb Open Data Premier League seasons (2003/04 and 2015/16) do not overlap the commonly used FPL historical archive, which begins in 2016/17. The 34-match parity set remains an engineering benchmark, not an FPL training set.

### Wyscout 2017/18

The official Wyscout Figshare event collection is a promising event-side candidate for 2017/18 and its event/match/player/team/competition items display CC BY 4.0. The season overlaps 2017/18 FPL history. However:
- the FPL historical target archive's data-use rights are unresolved;
- the current player metadata and EPL appearance counts have not yet been reconciled to the official files;
- candidate normalized-name matches are not verified identity links.

Keep this as a candidate provider, not production data, until both event and target rights plus numeric player/fixture mappings are proven.

### Opta/PulseLive candidate

The inspected public repository `imadeddine-belkat/Premier-League-Stats` has 2026/27 FPL gameweek rows and team-match event rows. Its current Git tree has no `players_match_stats` outputs despite the README describing such files. GitHub metadata reports no recognized licence and no root LICENSE file. The 511 shared player IDs and 100 shared fixture IDs are promising structural evidence, but not permission to integrate or redistribute underlying Opta/PulseLive data.

### Historical FPL targets

Vaastav's historical repository contains useful gameweek targets, but its licence notice says the underlying FPL/Understat data belongs to those providers; the repository's MIT code licence is not a data-use grant. No authorized historical FPL target archive has been confirmed in this audit.

## 5. Projection data is not a historical target archive

The evmax open-data page publishes expected-points projections under CC BY 4.0, but only a small number of recent gameweeks were available at the time of review. It may be useful as an external forecast benchmark where coverage exists; it does not solve the need for season-aligned historical event features and actual FPL target labels.

## 6. Decisions and gates

| Blocker | Current evidence | Gate to clear |
|---|---|---|
| Point-in-time FPL vintages | Daily GitHub Actions artifacts; 90-day retention | Private durable storage + deadline-aware snapshots |
| Global ownership | Official history `selected` + event `ranked_count` | Pipeline run verifies full-roster coverage and values |
| Rank-tier EO | Tested estimator; no authorized feed wired | Deadline-locked manager-pick sample or licensed provider |
| Event/FPL season overlap | Wyscout 2017/18 candidate | Reconcile official data and secure FPL target rights |
| Opta/PulseLive player-match feed | No per-player-match files found in inspected tree | Provider documentation, actual files, and explicit data rights |
| Historical target rights | No grant established | Written permission or licensed target source |

## Sources reviewed

- FPL official API schema reference: https://github.com/shyndman/fpl-scrapper/blob/main/docs/API.md
- FPL mirror snapshot README: https://github.com/Unholy-smoke/fpl-mirror
- Fantasy Football Pundit EO method: https://www.fantasyfootballpundit.com/fpl-effective-ownership/
- LiveFPL top-10k summary: https://plan.livefpl.net/top10k_summary
- Wyscout event data: official Pappalardo–Massucco Figshare collection (see existing Wyscout source audit in this workbench)
- Opta/PulseLive candidate: https://github.com/imadeddine-belkat/Premier-League-Stats
- Vaastav FPL historical archive: https://github.com/vaastav/Fantasy-Premier-League
- evmax projection data and CC BY 4.0 terms: https://evmax.ai/data/
