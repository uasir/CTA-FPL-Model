# Four-layer CTA-FPL integration and decision-quality evaluation

Status: **IMPLEMENTATION PROTOTYPE / RESEARCH ONLY / NOT PROMOTED**

## Objective

The model should forecast repeatable future FPL performance from deadline-available evidence. It must not be trained to imitate the last points total, nor judged by whether it guessed the exact realised haul of every player.

A player with strong, persistent attacking involvement and threat indicators may deserve a stronger forward forecast before goals, assists, xG or xA fully reflect that threat. The model must estimate that prospect probabilistically; it must not assume that every underperforming player is "due" a return.

## Evaluation policy: points, distributions and decisions

Keep MAE and RMSE on the full, unchanged validation cohort. Never remove, winsorise or relabel a 16-point haul merely because it creates a large error.

RMSE is retained as a tail-sensitive diagnostic, not a standalone promotion gate. MAE measures ordinary absolute points error. The evaluator additionally reports error quantiles, large-error rates, forecast-range diagnostics, Brier score and log loss for 6+, 8+ and 10+ outcome probabilities, plus top-k ranking lift/regret when a ranking score is supplied.

Post-deadline red cards, injuries and tactical changes may be annotated during error review. Such annotations are explanatory only: they cannot alter the forecast, feature matrix, validation cohort or primary metrics. Events known before the deadline belong in the point-in-time feature set if reliable data exist. An event cannot be called unpredictable merely because it explains a miss after the fact.

Promotion must be based on paired chronological out-of-sample comparisons, player-season cluster uncertainty, calibration, ranking/decision utility and robustness across seasons and forecast ranges. No single metric, including MAE, RMSE or haul hit-rate, is sufficient.

## Four layers

### A — Temporal Football Value

Measures the value and development of actions over time: progression, carries, dangerous receipts, sequence contribution and action trends. Provider-specific definitions and missingness must be preserved.

### B — Risk and Defensive Intelligence

Measures the defensive and risk context in which player actions occur: pressure, duels, turnovers under pressure, defensive exposure and opponent threat allowed. It must distinguish observed zero from unavailable data.

### C — Player Intelligence

Combines A and B with role stability, minutes trend, attacking involvement, threat creation/reception/realisation and contextual threat. It is the player representation and feature-integration layer, not a post-hoc points ranking.

### D — 2PM-Transformer

A temporal two-part model with a shared sequence encoder and separate outputs:
1. minutes/appearance distribution;
2. points-band distribution conditional on appearance.

The unconditional points distribution adds non-appearance probability to the zero-points class. The initial bands are negative, zero, 1–2, 3–5, 6–9 and 10+. This is a research architecture, not a validated model. Compare it against persistence, Ridge, raw/calibrated two-part, six-band and appearance-hurdle baselines on identical expanding-season folds.

## Integration contracts

cta_four_layer_pipeline.py defines explicit A/B/C feature contracts, source coverage, provenance, as-of deadline checks and a fail-closed integration status. Null is not zero. A research-only feature set cannot be promoted by being passed into a model. D consumes ordered player histories built from the integrated A/B/C sequence and must keep target-fixture outcomes out of inputs.

Current provider reality remains a hard constraint:
- StatsBomb 360 is sampled context, not continuous tracking.
- Wyscout 2017/18 is a separate provider namespace and still needs a verified season-scoped FPL identity bridge.
- 11footy current-season identity candidates are not automatically verified; its panel remains ineligible until crosswalk approval.
- No provider's player IDs may be joined by name similarity alone.

## Implementation delivered in this branch

- scripts/evaluate_fpl_decision_quality.py: full-cohort point-error metrics, forecast bands, threshold probability calibration, ranking metrics and explanatory-only post-deadline annotations.
- scripts/cta_four_layer_pipeline.py: A/B/C schema, provenance, coverage and deadline contracts.
- scripts/two_pm_transformer.py: optional PyTorch shared temporal encoder with separate minutes and conditional-points heads.
- Tests cover haul retention, probability scoring, ranking diagnostics, deadline leakage rejection, explicit missingness and Transformer outputs.

## Not yet completed

- The four layers are not yet populated by a verified common multi-season player-fixture panel; A/B/C contracts are implemented but data adapters are not yet all wired into one production sequence.
- The Transformer has architecture and forward-pass tests, but no trained walk-forward experiment, calibration, hyperparameter selection or paired cluster-bootstrap report yet.
- The decision-quality evaluator is a standalone module; the existing historical walk-forward report has not yet been migrated to emit all its outputs. Existing historical results remain unchanged and authoritative.
- CTA remains RESEARCH_ONLY / DO_NOT_PROMOTE, weight zero. No recommendation engine may consume these research outputs.

## Next acceptance gates

1. Complete verified provider-to-FPL identity panels and point-in-time feature snapshots.
2. Build one player-season-gameweek sequence with explicit missingness and A/B/C provenance; enforce deadline cutoffs and chronological folds.
3. Train D only within each training fold. Fit calibration and all preprocessing on earlier training/calibration blocks only.
4. Compare all models on the exact common validation cohort. Report MAE, RMSE, probability calibration for 6+/8+/10+, ranking lift/regret, tail diagnostics, paired player-season cluster intervals and season stability.
5. Run a decision simulation with realistic FPL constraints only after forecast calibration and ranking quality pass.
6. Promote nothing unless it demonstrates repeatable incremental value over conventional baselines. Preserve the separate general-market and personal-squad recommendation products.
