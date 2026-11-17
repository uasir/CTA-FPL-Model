# Dual FPL Recommendation Architecture

Status: **APPROVED ARCHITECTURE / IMPLEMENTATION NOT YET COMPLETE**  
Approved by the project owner: 2026-11-17  
Tracking issue: https://github.com/uasir/CTA-FPL-Model/issues/2

## 1. Purpose

CTA-FPL-Model will expose two recommendation products over one shared, versioned forecasting foundation. The products solve different decision problems and must remain logically independent.

- `general_market`: recommendations that are useful to any FPL manager and do not depend on a manager's squad.
- `personal_squad`: recommendations optimized for one manager's actual squad, budget, transfers, chips, formation and preferences.

This is a product and architecture specification. It does not claim that either recommendation engine is implemented or production-ready.

## 2. Shared forecasting foundation

Both products consume the same validated, versioned player/fixture forecast records and supporting data contracts. Shared records should expose, where available:

- Stable FPL element ID and season identity.
- Position, team, current price and price timestamp/snapshot.
- Forecast horizon and fixture/gameweek context.
- Expected minutes and appearance/minutes uncertainty.
- Expected FPL points (EV) and uncertainty/distribution summaries.
- Fixture and team context.
- Effective ownership (EO) with cohort, sample size, deadline and source metadata.
- Data freshness, provenance, model version and validation status.

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

Every proposed transfer must be evaluated as a change to the full squad, including budget, position/team limits, free-transfer/hit consequences and future flexibility. A player ranking alone is not a personal transfer recommendation.

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
