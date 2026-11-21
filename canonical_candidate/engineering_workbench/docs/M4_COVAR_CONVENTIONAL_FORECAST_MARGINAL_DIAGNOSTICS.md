# M4 CoVar: Conventional Forecast Marginal Diagnostics

## Purpose

This evaluator measures how the conventional player-level expected-points and
expected-minutes forecasts compare with final official FPL outcomes after
prospective forecast capture and exact finality reconciliation.

It is a marginal forecast-quality diagnostic. It is **not** a joint player
outcome model, does not estimate covariance, and cannot validate CoVar's
joint scenario probabilities.

## Inputs and safeguards

Input must be the output of `m4_covar_matched_outcome_panel.py` and must:

- contain one season and distinct, positively numbered Gameweeks;
- carry exact official finality status for every matched player-Gameweek row;
- have no zero-filled missing observations;
- declare Gameweek as the cluster unit;
- explicitly state that joint dependence was not inferred from marginal rows;
- remain `decision_weight=0` and `production_eligible=false`.

The evaluator rejects duplicate player-Gameweek keys, non-finite forecast or
outcome values, rows from undeclared Gameweeks, and non-final rows.

## Reported diagnostics

- Points: pooled mean expected/actual points, signed bias, MAE and RMSE.
- Minutes: pooled mean expected/actual minutes, signed bias, MAE and RMSE.
- Descriptive error summaries by expected-points and expected-minutes bands.
- Per-Gameweek metrics.
- 95% percentile intervals from resampling whole Gameweeks, not individual
  player rows. Pooled metrics weight matched player-Gameweek rows equally;
  the bootstrap preserves within-Gameweek clustering.
- An explicit warning when fewer than 20 independent Gameweeks are available.

The intervals are exploratory when the number of independent Gameweeks is
small. Bands are descriptive and do not prove predictive-distribution
calibration.

## Run through GitHub Actions

1. Build a multi-Gameweek panel using the successful
   `CTA CoVar multi-Gameweek matched outcome panel` workflow.
2. Open `CTA CoVar marginal forecast diagnostics` and dispatch it with that
   successful panel run ID and the exact artifact name.
3. Inspect the `marginal_diagnostics.json` artifact.

The workflow validates the source run's completion, success, workflow name
and manual-dispatch event before downloading the panel.

## Interpretation boundary

This is a first stage of conventional forecast validation only. It can
identify marginal forecast bias and error patterns. It does not establish
player-to-player covariance, tail co-movement, candidate-versus-field joint
portfolio variance, or calibrated joint CoVar scenarios. Those require
prospective complete joint scenarios and independent joint-outcome validation.

No recommendation, transfer, starting XI, captaincy or production decision
is changed by this work.
