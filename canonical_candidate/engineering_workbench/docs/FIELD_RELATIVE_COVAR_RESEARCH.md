# Field-relative CoVar research layer

Status: **RESEARCH-ONLY / ZERO RECOMMENDATION WEIGHT**

## Purpose

The personal optimiser needs to distinguish raw expected points from the risk of scoring relative to the field. This module is a separate diagnostic layer; it does not alter the conventional expected-points recommendation or the CTA-informed recommendation.

## Exposure definitions

For player i:

- Own exposure w_i: 1 for each starting XI player, plus 1 additional unit for the captain.
- Field exposure f_i: deadline-matched standard effective ownership percentage divided by 100.
- Differential exposure d_i = w_i - f_i.

The expected points difference is:

E[S_own - S_field] = sum_i d_i E[P_i]

Given a player-points covariance matrix Sigma:

Var(S_own) = w' Sigma w

Var(S_field) = f' Sigma f

Cov(S_own, S_field) = w' Sigma f

Var(S_own - S_field) = d' Sigma d
= Var(S_own) + Var(S_field) - 2 Cov(S_own, S_field)

This estimates the variance of the starting-XI score difference under the declared exposure approximation. It is not a probability of gaining rank.

## Input requirements

1. Forecasts for the complete player universe used by the field comparison.
2. LiveFPL standard EO for every player in that universe, including explicit zero values where applicable.
3. EO cohort, sample size, capture timestamp, target deadline and EO deadline.
4. Verified post-lock picks (picks_lock_verified=true) and an exact EO/target-deadline match.
5. A complete symmetric shrunk covariance matrix for the same player universe.
6. A positive-semidefinite covariance matrix.

Missing EO or covariance pairs are not imputed as zero. Incomplete data returns a non-scored status. A non-PSD matrix is rejected.

## Current exclusions

- Bench auto-substitution and bench boost.
- Triple captain and other chip effects.
- Field formation and bench-selection interactions.
- Rank-cohort uncertainty beyond the supplied EO sample metadata.
- Multiweek covariance and transfer flexibility.

## Promotion gate

The covariance estimator must demonstrate stability and out-of-sample usefulness before this layer can affect decisions. At minimum, validate rolling-window covariance forecasts against subsequent realised covariance, test sensitivity to window length and shrinkage, quantify uncertainty, and show that CoVar-aware choices improve realised field-relative decision outcomes over the same EV-only decisions on matched chronological cohorts.

Until then:
- decision_weight = 0
- used_for_recommendation = false
- Use the output for research and diagnostics only.

The module is scripts/analyze_fpl_field_relative_risk.py; tests are in tests/test_fpl_field_relative_risk.py.
