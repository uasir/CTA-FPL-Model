# FPL data-source blocker register — 2026-11-17

## Executive status

The data pipeline can now preserve historical **global ownership counts** from FPL's per-player history, and a tested estimator exists for **sampled effective ownership (EO)** from deadline-locked manager picks. These are different measures:

- Global ownership: a player is selected by a share of all ranked FPL entries.
- Effective ownership: all 15 squad selections plus captain and Triple Captain extras, measured within a defined rank cohort. Starting-XI and scoring exposure are separate measures.

Neither is interchangeable with current `selected_by_percent` in bootstrap-static.

## 1. Point-in-time FPL data

### What exists

The official FPL workflow runs daily at 05:30 UTC and fetches:
- `bootstrap-static`
- `fixtures`
- Per-player `element-summary` history
- Official `ep_next` and `ep_this` expected-points baselines, plus current form, points-per-game, xG/xA and ICT-related bootstrap fields

Each run records fetch time and SHA-256 hashes, and uploads normalized rows plus the raw bootstrap and fixture feeds. The current player snapshot reports official `ep_next` coverage explicitly. The artifact retention has now been extended from 30 to **90 days**.

The daily workflow is useful for capturing snapshots before some gameweek deadlines, but it does not guarantee a snapshot immediately before every deadline. GitHub Actions schedules are best-effort. A 90-day artifact window is also not a durable full-season archive.

### Storage decision

The CTA repository is public. Do not commit raw FPL API snapshots or user-specific manager picks into its public Git history as a workaround for artifact expiry. The official FPL terms prohibit automated access/extraction and reserve rights in Game data; written permission is required before automated API collection resumes.

A durable archive needs a private user-controlled storage destination, but private storage is not a substitute for data permission. First obtain written permission covering automated collection, private archival, research/model development and publication scope. Then create a private repository or private cloud folder and configure the archive workflow. Until both permission and destination exist, no automated FPL snapshots should be collected and no full-season point-in-time archive is claimed.

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

`standard EO% = 100 × (all 15 squad selections + captain extra + Triple Captain extra) / sampled manager weight`

Rules:
- Ownership counts all 15 picks, whether starting or benched.
- `starting_pct` separately counts positions 1–11.
- `scoring_exposure_pct` counts the starting XI, Bench Boost bench players, captain extra and Triple Captain extra.
- Captain adds one extra unit to standard EO; Triple Captain adds a second extra unit.

The output is explicitly labelled `SAMPLE_ESTIMATE_NOT_GLOBAL_CENSUS`. It does not fetch manager picks or choose a rank cohort itself.

### Candidate sources reviewed

- Fantasy Football Pundit documents a live top-10k EO table soon after the deadline and a top-100k view later, with the formula above. Its public page is a live table, not a documented historical bulk API or a reusable licensed archive.
- LiveFPL publishes gameweek-by-gameweek top-10k ownership and captaincy summaries on its site. The accessible page contains historical tables for a prior season, but no bulk API or explicit data licence was established in this audit.
- The public `Unholy-smoke/fpl-mirror` repository records frequent API snapshots and daily global ownership CSVs, but GitHub reports no recognized repository licence. Its README also describes personal entry and mini-league data. Do not ingest or redistribute its files without permission.
- The `selected` history count from the official FPL feed is the cleanest current route to historical global ownership, but it cannot by itself provide rank-tier captaincy and Triple Captain exposure.

### Next EO data acquisition step

A first-party lock-safe capture workflow is implemented at `.github/workflows/cta-fpl-eo-capture.yml`, with collector `scripts/capture_fpl_ranked_manager_picks.py`.

It runs at minutes 25 and 55 of each hour to cover the observed :30 and :00 FPL deadline times; it only proceeds when the official next deadline is within seven minutes. It:
- samples 100 managers across rank strata within the pre-deadline overall top 10,000;
- records the rank cohort before the deadline and refuses to proceed if the standings fetch crosses the deadline;
- waits until 60 seconds after the official deadline;
- re-fetches official bootstrap data and verifies that the deadline has passed;
- only then fetches manager picks and chip state for the target gameweek;
- weights each sampled manager as 100 entries;
- calculates EO using the tested estimator;
- stores only aggregated EO rows and a hash/summary of the sample, not raw manager IDs or individual picks.

The collector's mocked timing/API tests pass, but it has **not completed a live near-deadline capture**. Its automated job is now gated until written permission for automated FPL data collection is obtained. Once permission is received and the repository variable is enabled, the post-lock picks endpoint must return locked gameweek selections for the sample to be accepted; it must never fall back to provisional picks.

Do not define the cohort using post-gameweek ranks; that would introduce lookahead bias. Do not treat a top-10k sample as whole-game EO. The current collector samples top 10k only; top-100k and broader-field samples remain future work.

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

## 5. Licensed external FPL forecast benchmarks — updated 2026-11-18

### Onside Arena: source audit and official FPL reconciliation passed

- Dataset: Fantasy Premier League — Graded Predictions Dataset, 2026/27.
- CSV: https://onsidearena.com/data/graded-predictions.csv
- DOI: https://doi.org/10.5281/zenodo.22746985
- Provider-stated licence: CC BY 4.0; attribute Onside Arena and link to its data page.
- Audit workflow: `.github/workflows/cta-onside-benchmark.yml`.
- Audit script: `scripts/inspect_onside_fpl_benchmark.py`.
- Latest real-source run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44257909685
- Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44257909685/artifacts/14407050697
- Source SHA-256: `dd51366a5f71d5f0bf26b4265b17188f04774d584c4444172be3f307aaf02a81`.

Verified:
- 5,450 rows, 14 columns.
- All 5,450 `captured_at` values precede their row's `deadline_utc`.
- All 5,450 deadlines exactly match official FPL event deadlines.
- 608 unique `player_id` values all match official FPL `element` IDs; none match `player_code`.
- Zero duplicate player-gameweek keys.
- 4,954 populated actual-points rows match official FPL event-live totals exactly; zero mismatches.
- 496 blank actual-points rows belong only to gameweeks still marked unfinished by the official API.

Independently recomputed on the same 4,954 scored rows:
- All scored rows: Onside MAE 1.681 / RMSE 2.577; provider-supplied frozen FPL `ep_next` MAE 1.600 / RMSE 2.651.
- Minutes-qualified subset (2,045 rows): Onside MAE 2.515 / RMSE 3.530; FPL `ep_next` MAE 2.685 / RMSE 3.765.

Interpretation:
- This is a verified, season-current external FPL forecast benchmark with an FPL element-ID key and checked realized points.
- The historical `fpl_ep_next` values are supplied by Onside. Their exact historical snapshots cannot be independently reconstructed from today's official API.
- The two eligibility cohorts must be reported separately; do not compare a minutes-qualified metric to an all-player metric.
- Keep Onside forecasts separate from CTA predictions. Do not train on them or blend them into the model.
- This dataset has no event-derived CTA features and does not clear the StatsBomb/Wyscout/Opta event-data integration blockers.

### evmax

The CC BY 4.0 open FPL dataset freezes pre-deadline expected-points projections and includes realized outcomes, but the visible archive covers only a limited number of gameweeks. It can be a secondary benchmark for those rounds, not a substitute for a multi-season training set.

## 6. Exploratory CoVar baseline from Onside actual points

A separate reproducible workflow uses only the provider-stated CC BY 4.0 ledger's realized `actual_points`; it does not call the official FPL API and ignores all forecast columns. Run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220. Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220/artifacts/14407138593. On GW1–GW10, 605 players appeared, 350 had complete panels, 255 incomplete panels were excluded, 54 zero-variance players were excluded, and 296 players remained in the matrix (43,956 pair estimates including diagonal). This is exploratory only: ten gameweeks are too few, complete-case selection is biased toward repeated appearances, and the underlying FPL data rights chain is not independently cleared. Do not enable CoVar in `personal_squad`.

## 7. Decisions and gates

| Blocker | Current evidence | Gate to clear |
|---|---|---|
| Point-in-time FPL vintages | Historical snapshots exist, but automated jobs are gated pending written permission | Written FPL permission + private durable storage + deadline-aware snapshots |
| Global ownership | Official history `selected` + event `ranked_count` | Pipeline run verifies full-roster coverage and values |
| Rank-tier EO | Lock-safe collector tested; standard EO formula corrected; no live capture | Written FPL permission + deadline-locked manager-pick sample or licensed provider |
| Event/FPL season overlap | Wyscout 2017/18 candidate | Reconcile official data and secure FPL target rights |
| Opta/PulseLive player-match feed | No per-player-match files found in inspected tree | Provider documentation, actual files, and explicit data rights |
| Historical target rights | Onside provider states CC BY 4.0; Vaastav 2017/18 archive rights and underlying FPL rights remain unresolved | Obtain written permission or another source with a cleared rights chain before FPL target ingestion |

## Sources reviewed

- FPL official API schema reference: https://github.com/shyndman/fpl-scrapper/blob/main/docs/API.md
- FPL mirror snapshot README: https://github.com/Unholy-smoke/fpl-mirror
- Fantasy Football Pundit EO method: https://www.fantasyfootballpundit.com/fpl-effective-ownership/
- LiveFPL top-10k summary: https://plan.livefpl.net/top10k_summary
- Wyscout event data: official Pappalardo–Massucco Figshare collection (see existing Wyscout source audit in this workbench)
- Opta/PulseLive candidate: https://github.com/imadeddine-belkat/Premier-League-Stats
- Vaastav FPL historical archive: https://github.com/vaastav/Fantasy-Premier-League
- Onside Arena FPL graded predictions and CC BY 4.0: https://onsidearena.com/data and https://onsidearena.com/accuracy; Zenodo DOI: https://doi.org/10.5281/zenodo.22746985
- evmax projection data and CC BY 4.0 terms: https://evmax.ai/data/


### Official FPL baseline and live general-market smoke test (2026-11-18)

Actions run 44254087867 completed successfully and uploaded artifact 14405276623:
https://github.com/uasir/CTA-FPL-Model/actions/runs/44254087867

- 672/672 `ep_next` and `ep_this` values present.
- 672 player forecasts built for GW11 from the official FPL baseline.
- Target fixture counts are read from normalized fixture columns `gameweek`, `team_h_id`, `team_a_id`; minutes per prior fixture are scaled by the target GW fixture count.
- The general-market engine ranked all 672 players.
- The snapshot was 76.164 hours before deadline and correctly labelled `STALE_OVER_24H`; recommendations remain exploratory.
- No EO was attached; no CoVar was used.
- Historical lagged training remains `NOT_VERIFIED` for point-in-time reconstruction.
