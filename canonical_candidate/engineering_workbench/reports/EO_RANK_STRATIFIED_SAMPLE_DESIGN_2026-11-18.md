# Effective ownership sample design — 2026-11-18

## GW11 capture plan

- Target cohort: top 10,000 managers in the overall global league, ranked before the GW11 deadline.
- Rank pages: 200 pages × 50 managers.
- Sample: 2 managers selected uniformly without replacement from every rank page (400 managers total).
- Expansion weight: 25 per sampled manager; total sample weight = 10,000.
- The rank cohort is frozen before deadline. Picks are fetched only after the deadline plus 60 seconds and after a fresh official bootstrap confirms the deadline has passed.
- The workflow runs at minutes :05 and :35, accepts a 35-minute pre-deadline window, and has a 45-minute timeout. For the GW11 deadline on 2026-11-21 at 11:00 UTC, the expected capture run is scheduled for 10:35 UTC.

## Estimands

- `owned_by_pct`: all 15 squad selections.
- `starting_pct`: positions 1–11.
- `captain_pct`: captain selections.
- `triple_captain_pct`: captain selections when the locked chip is Triple Captain.
- `effective_ownership_pct`: all 15 squad selections + captain extra + Triple Captain extra.
- `scoring_exposure_pct`: starters + Bench Boost bench + captain extra + Triple Captain extra.

The official locked bootstrap player universe is passed to the estimator so all 672 FPL players appear, including zero-sample-exposure players. No manager IDs or individual picks are written to the output artifact.

## Uncertainty intervals

- 95% Wilson intervals are reported for ownership, starting, captain and Triple Captain rates, using the effective manager sample size.
- 95% rank-page-stratified normal intervals with finite population correction are reported for EO and scoring exposure, using within-page sample variance.
- When the EO/scoring sample variance is zero, conservative component-interval bounds are used.
- The intervals are approximate. They do not capture every source of uncertainty in the rank cohort, manager churn, or selection bias. They are not a substitute for a whole-game census.

## Validation

- Python unit tests verify complete page coverage, two random managers per page, equal weights, locked-picks timing, all-15 ownership, captain/Triple Captain exposure, Bench Boost treatment, zero-exposure player rows, and confidence-interval bounds.
- Engineering CI run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44355853392
- CI: 38 JavaScript tests, 10 canonical Python unittests, 190 pytest tests + 3 subtests passed.

## Status

This is the improved capture design, not a live EO result. The first deadline-locked sample will only be claimed after the scheduled GW11 run completes and the cohort/picks/lock checks pass. The estimate remains a top-10k weighted sample, not whole-game ownership.
