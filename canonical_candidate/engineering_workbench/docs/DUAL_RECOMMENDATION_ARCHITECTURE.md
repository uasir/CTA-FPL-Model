# Dual FPL Recommendation Architecture

Status: **APPROVED ARCHITECTURE / EXPLORATORY V0.1 ENGINES IMPLEMENTED / VALIDATION IN PROGRESS**  
Approved by the project owner: 2026-11-17  
Tracking issue: https://github.com/uasir/CTA-FPL-Model/issues/2

## 1. Purpose

CTA-FPL-Model will expose two recommendation products over one shared, versioned forecasting foundation. The products solve different decision problems and must remain logically independent.

- `general_market`: recommendations that are useful to any FPL manager and do not depend on a manager's squad.
- `personal_squad`: recommendations optimized for one manager's actual squad, budget, transfers, chips, formation and preferences.

The first deterministic versions of both engines now exist in Python and JavaScript with cross-language output-parity tests. They are exploratory only and are not production-ready; the shared FPL baseline still uses official ep_next plus latest-completed-gameweek minutes per fixture scaled by the target gameweek's fixture count.

## 2. Shared forecasting foundation

Both products consume the same validated, versioned player/fixture forecast records and supporting data contracts. Shared records should expose, where available:

- Stable FPL element ID and season identity.
- Position, team, current price and price timestamp/snapshot.
- Forecast horizon and fixture/gameweek context.
- Expected minutes and appearance/minutes uncertainty.
- Expected FPL points (EV) and uncertainty/distribution summaries.
- Fixture and team context.
- Effective ownership (EO) with cohort, sample size, deadline and source metadata.
- Data freshness, provenance, model version and validation status. Snapshots more than 24 hours before the target deadline are marked stale; they cannot be labelled validated.

Missing fields must remain explicitly missing. Current global ownership (`selected_by_percent` or historical `selected` counts) must not be relabelled as EO. Exploratory baselines must not be presented as trained forecasts.

## 3. General market recommendations

### Input contract

General mode accepts a forecast/data snapshot plus optional display filters (gameweek/horizon, position, price range, team, recommendation category and risk profile). It must not require, read, infer or use the user's personal squad, bank, transfers or rank.

### Recommendation categories

- Best overall and best value by position.
- Highest expected-points opportunities.
- Differentials, with EO cohort and sample coverage disclosed.
- Captaincy candidates.
- Short-term fixture targets and longer-term holds.
- Improving/declining prospects.
- High-upside/high-risk options.
- Sell/avoid watchlists.

### Implemented v0.1 output

- Overall EV ranking and ranking by position.
- Expected-points-per-price value ranking.
- Captaincy shortlist based on EV.
- Differential shortlist only when sampled EO includes verified cohort and post-lock provenance matching the forecast deadline.

Fixture targets, trend detection, upside/downside categories and sell/avoid recommendations remain planned, not implemented.

### Invariance rule

For identical forecast snapshots, model versions and filters, general recommendations must be identical regardless of any personal squad state stored elsewhere in the application. This must be enforced by API/service boundaries and regression tests, not merely by convention.

## 4. Personal squad recommendations

### Required manager context

Use an explicit, timestamped squad snapshot with 15 FPL element IDs and the relevant FPL state:

- Bank and squad value; purchase prices where available.
- Free transfers, transfer history/available chips and active chip state.
- Gameweek deadline and squad snapshot timestamp.
- Formation/starting XI and bench constraints or preferences.
- Manager risk profile, rank/target rank and strategic preferences.

If essential squad state is missing or stale, return a clear incomplete-input status and request refresh; never silently optimize a generic or guessed squad.

### Outputs

- Ranked transfer-in/out pairs and alternatives.
- Hold versus transfer/roll recommendation.
- Starting XI, legal formation and bench order.
- Captain and vice-captain.
- Squad-specific coverage, concentration and differential analysis.
- Whole-squad expected points, uncertainty, upside/downside and decision explanation.

The exploratory v0.1 evaluates one transfer at a time, with purchase-to-selling-price rules, budget, position and three-per-team limits, and a configurable hit cost. It builds a legal XI under the selected formation, captain/vice-captain and reserve/bench order. Multi-transfer sequences, chip simulation and future flexibility remain unimplemented. A player ranking alone is not a personal transfer recommendation.

## 5. CoVar and portfolio risk

CoVar/covariance belongs to the portfolio-risk layer; it is not a property that a squad must contain. It can inform the personal optimizer only after stability, calibration and out-of-sample utility gates pass. Current short-window historical-points covariance remains exploratory and must not influence production recommendations.

General mode may optionally display validated player-pair or factor-risk context as supplementary information, but it must remain useful without CoVar and must not turn an individual player ranking into a hidden squad optimization.

## 6. Separation and reproducibility

- Keep recommendation services/contracts distinct: `general_market` and `personal_squad`.
- Share forecast/data services; do not duplicate the prediction engine.
- General mode has no dependency on personal-squad storage or manager-specific state.
- Personal mode requires an explicit squad snapshot and records exactly which snapshot and constraints it used.
- Every result records data snapshot IDs/hashes, model version, forecast horizon, source coverage, EO cohort metadata, and validation state.
- Preserve deterministic Python/JavaScript parity for shared deterministic calculations. Recommendation ranking and optimizer outputs require their own parity or contract tests where implemented in both languages.

## 7. Acceptance tests

1. General mode runs with no squad input.
2. General mode is invariant when the user's squad, bank, transfers or rank changes.
3. General rankings are reproducible for identical snapshot/model/filter inputs.
4. Personal mode rejects absent, malformed or stale squad snapshots rather than substituting a generic squad.
5. Personal mode changes appropriately when squad/bank/transfers/chips/constraints change.
6. Every suggested transfer satisfies FPL squad, position, team and budget constraints.
7. Personal recommendations report the exact squad snapshot and assumptions used.
8. EV, minutes, price, fixture and EO provenance/coverage are traceable; unavailable values are not fabricated.
9. CoVar is excluded from decision scoring until the documented statistical gates pass.
10. Shared deterministic calculations pass Python/JavaScript parity checks.
11. Regression tests prove general/personal isolation and prevent accidental cross-contamination.

## 8. Implementation sequence

1. Inspect the recovered Python source, current canonical candidate and existing FPL ingestion/feature contracts before coding.
2. Define shared forecast schema and versioned recommendation input/output contracts.
3. Implement `general_market` first using only validated shared forecasts; add category/ranking tests and squad-invariance tests.
4. Implement `personal_squad` with explicit FPL legality and budget constraints; add squad-sensitivity and optimizer tests.
5. Add portfolio-risk/CoVar integration only after its separate validation gates pass.
6. Run full CI, source regression tests, Python/JavaScript parity and end-to-end reproducibility checks.

Do not rebuild the existing engine, replace recovered source lineage, fabricate player identity/EO/minutes, or claim production readiness from passing structural tests alone.


## 9. Current implementation and validation status

### Implemented, exploratory only
- Python: `scripts/general_market_engine.py` and `scripts/personal_squad_engine.py`.
- JavaScript: `src/js/general_market_engine.mjs` and `src/js/personal_squad_engine.mjs`.
- Shared request contracts reject personal context from general-market inputs and validate the personal squad separately.
- Both engines have deterministic Python/JavaScript output-parity tests.
- The personal optimiser enforces one-transfer budget, position and three-player team constraints, legal formations, starting XI, captain, vice-captain and bench order.
- The general engine uses EV and value; it uses EO only when locked cohort metadata and the matching target deadline are present.
- Neither engine uses CoVar or pretends that the supplied risk profile has been applied.

### Not yet production-ready
- Official FPL `ep_next` is the current points baseline; it is not a CTA-trained forecast.
- Baseline freshness is labelled relative to the deadline; snapshots older than 24 hours remain exploratory even if captured before the deadline.
- Expected minutes are proxied by latest completed-gameweek minutes per fixture, scaled to the target gameweek fixture count; this is not a trained minutes model.
- Live post-lock EO capture has not yet been validated.
- Multi-season, point-in-time historical training data and out-of-sample predictive validation remain incomplete.
- Multi-transfer optimisation, chip effects, multiweek planning and CoVar utility validation remain future work.

## 10. Verified live state — 2026-11-18

### End-to-end FPL ingestion and engine parity

- The latest engineering CI passed: 221 Python tests, 3 subtests, the legacy unit tests and the JavaScript contract/parity suite. [CI run](https://github.com/uasir/CTA-FPL-Model/actions/runs/44391549591)
- The official FPL ingestion completed successfully for GW11: 672 players, 380 fixtures, 6,562 player-fixture history rows and 459 players with positive minutes. All 672 players have official `ep_next` coverage. [FPL ingestion run](https://github.com/uasir/CTA-FPL-Model/actions/runs/44391549645)
- General-market and personal-squad engines passed the full-pool Python/JavaScript parity and scale checks. The personal-squad scale check uses a synthetic legal 15-player squad; it is not a recommendation for the manager's actual squad.
- The current general-market output is still based on official FPL `ep_next`. Effective-ownership coverage is zero, CoVar is not used in the recommendation score, and the risk profile is not yet applied.

### Prediction and data-validation results

- The latest nested ridge experiment achieved MAE 1.1991 and RMSE 2.0091; the last-five-points baseline achieved MAE 1.1855 and RMSE 2.1513. Ridge improves RMSE but not MAE. It remains exploratory, not a promoted production model.
- Adding Opta team context worsened both MAE and RMSE relative to the player-form ridge baseline. It has therefore not been promoted.
- The Onside/FPL actual-points cross-audit found 4,954 exact player-fixture matches with zero points mismatches.
- Opta identity reconciliation has 511 exact numeric player-ID matches to FPL, with no team mismatches; 161 FPL players have no corresponding Opta row.
- The current historical-points covariance matrix covers 420 players over 10 gameweeks with 50% off-diagonal shrinkage. It remains exploratory and is not supplied to the recommendation engine.
- The GW11 snapshot was captured on 2026-11-18 at approximately 20:31 UTC, more than 24 hours before the 2026-11-21 deadline. The forecast is correctly labelled exploratory.

### Contextual threat and 11footy integration

- **11footy:** 100/100 completed 2026/27 matches reconcile to FPL fixtures, producing 4,000 player-match rows. There are 490 candidate identities, 340 with exact normalized name/team/birth-date evidence, and 68 with exact team/minutes/goals/assists consistency across at least three overlapping matches. No candidate team conflicts were observed. No candidates were automatically verified; the model-ready panel remains empty until the season-scoped crosswalk is approved. [Integration run](https://github.com/uasir/CTA-FPL-Model/actions/runs/44391549645)
- **StatsBomb 360:** The pilot produced 2,568 usable contextual rows from 3,021 supported events (85.0% frame coverage) and 31 player-match aggregates. All 2,568 rows have known attack direction using StatsBomb's ACTION_EXECUTING_TEAM coordinate convention; no global direction map is required. The sample contains 363 threat-creation pass attempts (234 completed), 249 progressive pass attempts (157 completed), 76 progressive carries, 125 dangerous receipts and 24 shots (3.312 xG, four goals).
- **Receiving opportunities:** 7,124 event-frame option observations include 2,645 open and 368 dangerous-open observations. These are repeated frame observations, not unique opportunities. Team-possession deduplication uses the maximum simultaneous option count per possession: 525 open-option peaks across 188 possessions, 124 dangerous-open peaks across 81 possessions and 720 blocked-option peaks across 200 possessions. Possession IDs were available for all usable event rows; player-match features use actor-possession peaks rather than summing repeated frames. No StatsBomb-to-FPL identity join exists, and prediction validation remains NOT_EVALUATED. [Latest pilot run](https://github.com/uasir/CTA-FPL-Model/actions/runs/44394518349)
- **Wyscout:** The 2017/18 EPL audit covers 643,150 events across 380 matches. It remains a historical event source without an FPL identity crosswalk.
- CTA's new non-shot and receiving-opportunity features remain provisional. No CTA feature has yet demonstrated incremental FPL points prediction value.

### Current readiness boundary

The complete architecture remains active, but the current working forecast is a baseline system, not yet the finished CTA-driven prediction system. The next engineering priorities are to review and verify the strongest 11footy identity candidates, complete StatsBomb-to-FPL identity mapping, add a common-frame transform only for cross-team spatial comparisons, and connect verified player-match rows to the shared training layer, and run chronological out-of-sample tests before promoting any CTA features. Keep general-market and personal-squad services separate; keep CoVar as a complementary portfolio-risk layer rather than a substitute for CTA points prediction.
