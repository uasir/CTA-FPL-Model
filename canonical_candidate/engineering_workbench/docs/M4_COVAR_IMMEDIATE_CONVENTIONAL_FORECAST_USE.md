# Immediate CoVar use with the conventional M3 forecast

## Decision

The current recommendation path may use CoVar immediately as a **historical covariance decision-support overlay**. It does not wait for CTA/Zazz training or future optimization.

- Expected points come from the existing conventional M3 forecast.
- Player dependence comes from the latest available historical, diagonal-shrunk FPL points covariance matrix.
- The overlay scores the current starting XI and each legal one-transfer starting-XI alternative, including the current captain multiplier.
- It reports expected-points change, portfolio variance, off-diagonal covariance contribution, and the EV/variance Pareto frontier.
- It identifies the lowest-variance and highest-expected-points alternatives separately.

## What this does not claim

This is a practical historical proxy, not a trained or calibrated forward joint forecast. It does not estimate the probability of beating the field, because the field's joint manager portfolios are not part of this overlay. Marginal EO remains a separate field-exposure input and is never used to reconstruct manager portfolios.

The historical covariance panel is retrospective. A successful finality reconciliation confirms realized scoring values, not what was knowable at the original deadline or whether historical dependence will persist in the next Gameweek.

The overlay is currently limited to the starting XI. It does not simulate autosubs, bench order, Bench Boost, Free Hit, or fixture-level event scenarios.

## Recommendation behavior

The canonical conventional EV recommendation remains intact. The overlay adds CoVar alternatives and their EV opportunity costs; it does not silently replace the EV choice or alter the XI/captaincy. This preserves a transparent two-axis decision rather than inventing a universal CoVar weight.

`decision_weight` remains 0 and `production_eligible` remains false. The user can use the lowest-variance alternative or select from the Pareto frontier as a human decision aid. Any automatic CoVar weighting is a separate explicit decision.

## Build the current matrix without local execution

Open the GitHub Actions workflow **Build current historical CoVar matrix from reconciled FPL outcomes**. Its defaults use the verified GW1–GW10 finality evidence run `44882707622`, artifact `cta-covar-realized-evidence-44882707622-1`, a 10-Gameweek window, and 50% off-diagonal shrinkage. The workflow publishes only the manager-free covariance matrix, player variance summary, and report; it never exports sampled manager portfolios.

## Integration

Use `recommend_personal_squad_with_historical_covar(...)` from `personal_squad_covar_recommendation.py`, supplying:
- the ordinary personal-squad request with the conventional forecast rows;
- the exploratory covariance report from `estimate_fpl_covariance.py`;
- its covariance-pair rows, including `shrunk_covariance`.

If any current XI or candidate player lacks a complete covariance estimate, the overlay returns `NOT_AVAILABLE_INCOMPLETE_COVARIANCE_COVERAGE`. Missing observations and zero-variance players are not imputed as zero risk.

## Future optimization

Future work can replace the historical proxy with prospective joint scenario forecasts, calibrated on complete Gameweek clusters, and compare actual sampled field portfolios. That training/optimization work is independent; it is not a prerequisite for using the current historical proxy.
