# FPL data-source blocker register — 2026-11-17

## Executive status

The data pipeline can now preserve historical **global ownership counts** from FPL's per-player history, and a tested estimator exists for **sampled effective ownership (EO)** from deadline-locked manager picks. These are different measures:

- Global ownership: a player is selected by a share of all ranked FPL entries.
- Effective ownership: all 15 squad selections plus captain and Triple Captain extras, measured within a defined rank cohort. Starting-XI and scoring exposure are separate measures.

Neither is interchangeable with current `selected_by_percent` in bootstrap-static.

## 1. Point-in-time FPL data

### What exists

The official FPL ingestion workflow was previously scheduled daily at 05:30 UTC and fetched:
- `bootstrap-static`
- `fixtures`
- Per-player `element-summary` history
- Official `ep_next` and `ep_this` expected-points baselines, plus current form, points-per-game, xG/xA and ICT-related bootstrap fields

Each run records fetch time and SHA-256 hashes, and uploads normalized rows plus the raw bootstrap and fixture feeds. The current player snapshot reports official `ep_next` coverage explicitly. The artifact retention has now been extended from 30 to **90 days**.

Following the user's explicit engineering instruction, PR #9 removed the `FPL_DATA_PERMISSION_CONFIRMED` execution gate on 2026-11-18. Official FPL ingestion is now scheduled daily at 05:30 UTC and has completed a successful live run (Actions run 44324401400). The job uses low concurrency and records source timestamps and SHA-256 hashes. GitHub Actions schedules remain best-effort; a 90-day artifact window is not a durable full-season archive.

### Storage decision

The CTA repository is public, and GitHub Actions artifacts from it are not private. Do not commit user-specific manager picks, personal squad selections, or account identifiers into public Git history or artifacts. The current EO collector is designed to publish only aggregated EO rows plus a sample hash/report, not raw manager IDs or individual picks. Official bootstrap, fixture and player-history feeds are public-source snapshots but still need careful provenance and retention handling.

The official FPL terms raise a separate data-use question: API reachability and private/non-commercial intent do not themselves establish a licence. That issue is recorded as a caveat, not an engineering execution gate; it does not block the user's private development workflow. Continue with low request rates, preserve source/provenance records, and treat a concrete technical denial, throttling response or access failure as a technical blocker. A durable archive still needs a private user-controlled storage destination because public Actions artifacts expire after 90 days. Private storage is a privacy/retention design decision, not a substitute for rights clearance or a reason to disable the existing workflow.

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

It is scheduled at minutes 5 and 35 of each hour to begin about 25 minutes before observed :30 and :00 deadlines. The collector accepts a 35-minute pre-deadline window to absorb best-effort scheduler delay; the job timeout is 45 minutes. It:
- samples 400 managers across all 200 pre-deadline rank pages in the overall top 10,000 (two managers per 50-rank page);
- records the rank cohort before the deadline and refuses to proceed if the standings fetch crosses the deadline;
- waits until 60 seconds after the official deadline;
- re-fetches official bootstrap data and verifies that the deadline has passed;
- only then fetches manager picks and chip state for the target gameweek;
- weights each sampled manager as 25 entries (total sample weight 10,000);
- calculates EO using the tested estimator, with approximate 95% Wilson intervals for ownership/starting/captain/chip rates and rank-page-stratified intervals for EO/scoring exposure;
- includes all 672 official FPL players, including zero-exposure rows;
- stores only aggregated EO rows and a hash/summary of the sample, not raw manager IDs or individual picks.

The collector's mocked timing/API tests pass. Its first scheduled live job (Actions run 44342865582) completed successfully but returned `SKIPPED_OUTSIDE_DEADLINE_WINDOW`: it started about 4,015.77 minutes before the GW11 deadline (2026-11-21 11:00 UTC). Its 324-byte artifact contains only the skip report; no cohort, picks or EO rows were captured. The new earlier schedule and 35-minute pre-deadline window improve capture resilience. The GW11 capture is expected to start at 10:35 UTC on 2026-11-21, 25 minutes before the 11:00 UTC deadline. A successful live capture still requires the rank cohort to be frozen before deadline, followed by post-deadline picks after the 60-second lock grace and a fresh bootstrap confirmation. It must never fall back to provisional picks.

Do not define the cohort using post-gameweek ranks; that would introduce lookahead bias. Do not treat a top-10k sample as whole-game EO. The current collector samples top 10k only; top-100k and broader-field samples remain future work.

## 4. Player-level event data aligned to FPL

### StatsBomb Open Data

The current StatsBomb Open Data Premier League seasons (2003/04 and 2015/16) do not overlap the commonly used FPL historical archive, which begins in 2016/17. The 34-match benchmark (Actions run 44348748561) has now passed end-to-end: 34/34 Python–JavaScript match runs, 125,719 events, 113,373 sequence comparisons, 21,567 player comparisons and 6,528 xT-grid comparisons. The data-quality audit reports 22 usable 360 joins, 11 matches without a 360 source and one quarantined zero-join match (3837706). FPL-name and trusted-minutes coverage remain 0/1,027, so this is an engineering benchmark, not an FPL training set.

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

A separate reproducible workflow uses only the provider-stated CC BY 4.0 ledger's realized `actual_points`; it does not call the official FPL API and ignores all forecast columns. Run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220. Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44259763220/artifacts/14407138593. On GW1–GW10, 605 players appeared, 350 had complete panels, 255 incomplete panels were excluded, 54 zero-variance players were excluded, and 296 players remained in the matrix (43,956 pair estimates including diagonal). A split-window diagnostic comparing GW1–GW5 with GW6–GW10 across 260 players and 33,670 pairs found correlation-of-correlations 0.0078, median absolute correlation change 0.5004 and mean absolute change 0.5780. This is not a formal stationarity test, but it is a strong warning that the pairwise estimates are unstable. Ten gameweeks are too few, complete-case selection is biased toward repeated appearances, and the underlying FPL data rights chain is not independently cleared. Do not enable CoVar in `personal_squad`. Run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44260264105; artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44260264105/artifacts/14407094178.

## 7. Decisions and gates

| Blocker | Current evidence | Gate to clear |
|---|---|---|
| Automated FPL API access | Scheduled official API ingestion completed successfully on 2026-11-18; no technical denial observed. Official terms/data-use interpretation remains a separate caveat. | No permission-variable execution gate. Keep request rate low, preserve provenance, monitor for concrete technical failures, and obtain legal advice if use scope expands. |
| Point-in-time FPL vintages | Current snapshot captured 2026-11-18 14:28 UTC; historical feature table is structurally lagged but source-vintage status remains `NOT_VERIFIED`. Artifacts expire after 90 days. | Capture and privately retain pre-deadline snapshots over time; prove immutable source vintages before claiming point-in-time backtests. |
| Global ownership | Official per-player history `selected` and event `ranked_count` are ingested for all 672 players; coverage and row reconciliation passed. | Add validation for denominator completeness and persist deadline-vintage snapshots. |
| Rank-tier EO | Formula and collector are tested; first live scheduled attempt skipped outside the deadline window, so no locked EO sample exists yet. | Obtain a successful pre-deadline cohort and post-lock manager-pick sample, then validate weighted EO and sample uncertainty. |
| Event/FPL season overlap | Wyscout 2017/18 candidate | Reconcile official data and secure FPL target rights |
| Opta/PulseLive player-match feed | No per-player-match files found in inspected tree | Provider documentation, actual files, and explicit data rights |
| Historical target rights | Onside provider states CC BY 4.0; Vaastav 2017/18 archive rights and underlying FPL rights remain unresolved | Obtain written permission or another source with a cleared rights chain before FPL target ingestion |

## Sources reviewed

- Official FPL Terms & Conditions: https://fantasy.premierleague.com/help/terms
- Premier League Terms of Use: https://www.premierleague.com/en/terms-and-conditions
- Premier League data-permission contact guidance (match data via Football DataCo): https://www.premierleague.com/en/news/102426
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

### Latest live FPL run — 2026-11-18

Official ingestion Actions run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44324401400. Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44324401400/artifacts/14436735723.

- 672 players, 380 fixtures, 6,562 player-fixture rows.
- 672/672 player-summary requests succeeded; no unknown player IDs, orphan fixtures, minute mismatches or total-points mismatches.
- All 672 players had official `ep_next` and `ep_this`.
- Python/JavaScript parity passed for both `general_market` and the synthetic 15-player `personal_squad` scale run across the same 672-player forecast pool.
- The baseline forecast is still exploratory: official `ep_next` is not a CTA-trained forecast, minutes are a proxy, EO coverage is zero, and point-in-time historical status is not verified.
- The exploratory ridge model remains `DO_NOT_PROMOTE`; its points MAE was 1.2016 versus 1.1855 for the baseline. CoVar remains disabled due to weak split-window stability.

Original source archive recovery and SHA-256 verification are documented in `reports/INTEGRATION_PROGRESS_2026-11-18.md`, section 11.

## 8. Opta/PulseLive current-season integration — 2026-11-18 update

Live Actions run 44352173248 passed the exact 2026/27 FPL/Opta identity, team, and fixture reconciliation:

- 511/511 shared `playerId = FPL code` joins and 511/511 provider `team_id = FPL team code` checks; zero mismatches.
- 161/672 FPL players have no provider player-season row.
- 100/100 provider match IDs match FPL fixture `code`; 200 team-match rows have exactly two team rows each.
- 760 team-fixture features and 18,816 prospective player-fixture rows generated, with 10 team metrics lagged to strictly before target kickoff.
- Generated crosswalk passes strict validation, 511 verified rows accepted.
- Workflow publishes aggregate counts and source hashes only; raw provider data, crosswalk rows and player-fixture rows are not uploaded.

This resolves the **technical ID/fixture mapping** blocker for the provider snapshot, but not the data-use or vintage blockers:
1. Underlying Premier League/PulseLive data rights remain unverified.
2. The player-season and team-match CSVs are current cumulative snapshots; no archived deadline-vintage history exists yet. `point_in_time_status = NOT_VERIFIED`.
3. The provider tree does not establish player-level per-match event metrics; current integration supplies team context only.
4. Do not attach these team features to predictive scoring or strict historical backtests until point-in-time capture and out-of-sample value are demonstrated.

Detailed results and source hashes: `reports/OPTA_PULSELIVE_LIVE_INTEGRATION_2026-11-18.md`.

## 9. Opta team-context predictive value — 2026-11-18

The live adapter now joins 6,562/6,562 historical FPL player-fixture rows to strictly prior team-level Opta context. A paired temporal holdout (train GW1–6; validate GW7–10) tested the player-form ridge model against the same model plus 11 Opta team-context features:

- Player-form ridge: MAE 1.201603; RMSE 2.015697.
- Player-form + Opta team context: MAE 1.229909; RMSE 2.022270.
- Adding team context worsened MAE by 0.028306 and RMSE by 0.006573.
- Naive last-five-GW points baseline MAE: 1.185511.
- Decision: `DO_NOT_PROMOTE`.

This is a single-season exploratory holdout and provider source-vintage remains `NOT_VERIFIED`; it is not a strict historical backtest. Do not attach these features to EV, ranking, transfer or squad-scoring decisions. Preserve the adapter as a validated structural/research sidecar only.

Full run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44353308393. Detailed report: `reports/OPTA_TEAM_CONTEXT_TEMPORAL_EVALUATION_2026-11-18.md`.

## 10. Nested ridge alpha selection — 2026-11-18

A nested rolling-origin experiment selects alpha only inside the outer training window (inner train GW1–4, inner validation GW5–6), then evaluates on GW7–10:

- Points alpha selected: 300; minutes alpha: 0.1.
- Tuned points MAE/RMSE: 1.199065 / 2.009075.
- Fixed alpha10 points MAE/RMSE: 1.201603 / 2.015697.
- Naive last-five-GW points MAE: 1.185511.
- Tuned minutes MAE: 15.367280 vs naive last-GW minutes MAE 11.098918.
- Decision: `DO_NOT_PROMOTE`; no recommendation scoring uses either model.

The outer GW7–10 holdout has now been consumed. Any further tuning must use new later-gameweek data or another season, not reuse this test window. Historical source-vintage remains `NOT_VERIFIED`.

## 11. Rank-tier EO sample precision — 2026-11-18

The EO collector has been upgraded for GW11:
- Top-10k overall-rank cohort, all 200 standings pages captured.
- Two managers sampled per 50-rank page (400 managers), equal weight 25.
- Complete rank-page coverage is required; a missing/incomplete page aborts the sample.
- The estimator includes the full official player universe (672), including zero sample exposure, and reports approximate 95% intervals for ownership, starting, captain, Triple Captain, EO and scoring exposure.
- The capture still freezes ranks before the deadline and fetches picks only after deadline + 60-second grace + fresh bootstrap confirmation.
- No manager IDs or individual picks are uploaded.

CI run 44355853392 passed. Design report: `reports/EO_RANK_STRATIFIED_SAMPLE_DESIGN_2026-11-18.md`.

No live rank-tier EO sample has yet been captured. The GW11 deadline is 2026-11-21 11:00 UTC; expected pre-deadline run is 10:35 UTC. If scheduler delay or incomplete page coverage prevents a valid capture, no EO estimate will be published.

## 12. CoVar sample horizon — 2026-11-18

The weekly Onside actual-points covariance workflow now takes up to the latest 20 fully graded gameweeks, using all available completed gameweeks when fewer than 20 exist. This allows the split-window stability diagnostic to compare two 10-GW halves once the season has 20 completed observations.

The previous 10-GW split-window result remains unstable (correlation-of-correlations 0.0078; median absolute correlation change 0.5004). The longer panel must be observed before any reliability claim. Complete-case exclusion, no zero-filling, and 50% diagonal shrinkage remain. CoVar is still disabled in `personal_squad`.

## 13. Onside actual-points source validation — 2026-11-18

The daily FPL ingestion workflow cross-audited Onside `actual_points` against official FPL history for GW1–GW10:

- 4,954/4,954 overlapping player-gameweek rows matched exactly.
- Zero point mismatches; MAE 0.0 and maximum absolute difference 0.0.
- Onside covers 4,954 rows across 605 players; official FPL contains 6,562 rows across 672 players.
- 1,608 FPL rows have no Onside counterpart; zero Onside rows lack an FPL counterpart. Missing rows are not zero-filled.
- Double-gameweek FPL fixture rows are aggregated before comparison.

This verifies the Onside actual-points values for the overlapping subset and supports their continued use as an exploratory CoVar input. It does not establish full-population coverage, point-in-time historical vintages, or covariance stability. CoVar remains disabled in `personal_squad`.

Detailed report: `reports/ONSIDE_FPL_ACTUALS_CROSS_AUDIT_2026-11-18.md`.
Final integrated pipeline run 44357649202 (artifact 14451857683; digest `sha256:45b7d36cb2ea6806d1a10f9d18828bbfefcbb220102c32aa9f3733ae10b5f1e2`) republishes the aggregate audit result and confirms 4,954/4,954 exact matches. It also passes the live-pool general-market and synthetic personal-squad Python–JavaScript parity checks. The Onside source validation is therefore part of the end-to-end FPL ingestion artifact, not just a standalone log.
