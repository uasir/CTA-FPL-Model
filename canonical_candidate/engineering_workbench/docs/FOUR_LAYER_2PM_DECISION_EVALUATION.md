# Independent CTA-FPL prediction tracks and decision-quality evaluation

Status: **IMPLEMENTATION PROTOTYPE / RESEARCH ONLY / NOT PROMOTED**

## Objective

Forecast repeatable future FPL performance from deadline-available evidence. Do not train merely to imitate the last points total or judge the model only by whether it guessed each realised haul exactly.

A player with strong, persistent attacking involvement and threat indicators may deserve a stronger forward forecast before goals, assists, xG or xA fully reflect that threat. Estimate that prospect probabilistically; do not assume every underperforming player is "due" a return.

## Agreed model architecture: independent tracks

### Track 1 — Integrated contextual CTA predictor (A + B + C)

This is a standalone conceptual predictor built from the three football-intelligence layers. It does not require the 2PM-Transformer and must first be evaluated on its own merits.

- **A — Temporal Football Value:** progression, carries, dangerous receipts, sequence contribution and action trends.
- **B — Risk and Defensive Intelligence:** pressure, duels, turnovers under pressure, defensive exposure and opponent threat allowed.
- **C — Player Intelligence:** integrates A and B with role stability, minutes trend, attacking involvement, threat creation/reception/realisation and contextual threat.

A and B provide independent evidence domains; C integrates them into a player representation. The A+B+C output is the integrated contextual FPL predictor. It is not required to be a Transformer or to use Layer D.

### Track 2 — Conventional FPL predictor (standalone 2PM-Transformer)

This model uses conventional, deadline-available FPL information only: historical minutes/points, appearance history, xG/xA history, season-to-date form and fixture context where point-in-time reliable.

The 2PM-Transformer has a shared temporal encoder and separate outputs:
1. minutes/appearance distribution;
2. points-band distribution conditional on appearance.

The unconditional points distribution adds non-appearance probability to the exact-zero points class. Initial points bands: negative, zero, 1–2, 3–5, 6–9 and 10+. This is a research architecture until trained and validated.

**The standalone 2PM-Transformer does not depend on A/B/C.** It must be trained and evaluated without CTA features first.

### Optional Track 3 — A/B/C-augmented 2PM-Transformer

Only after Tracks 1 and 2 have independent results, test whether adding A/B/C features to the conventional 2PM-Transformer improves performance. This is an ablation experiment, not an architectural dependency or assumption. Compare conventional-only 2PM against conventional-plus-A/B/C 2PM on the exact same player-fixture cohort and folds.

## Evaluation policy: points, distributions and decisions

Keep MAE and RMSE on the full, unchanged validation cohort. Never remove, winsorise or relabel a 16-point haul merely because it creates a large error.

RMSE remains a tail-sensitive diagnostic, not a standalone promotion gate. MAE measures ordinary absolute points error. Also report error quantiles, large-error rates, forecast-range diagnostics, Brier score and log loss for 6+, 8+ and 10+ outcome probabilities, plus top-k ranking lift/regret.

Post-deadline red cards, injuries and tactical changes may be annotated during error review. Such annotations are explanatory only: they cannot alter forecasts, features, validation cohorts or primary metrics. Events known before the deadline belong in the point-in-time feature set if reliable data exist. Do not call an event unpredictable merely because it explains a miss after the fact.

Promotion must use paired chronological out-of-sample comparisons, player-season cluster uncertainty, calibration, ranking/decision utility and robustness across seasons and forecast ranges. No single metric is sufficient.

## Data and leakage contracts

- Exact player-fixture identity joins only; never join provider IDs by name similarity alone.
- Preserve source provenance, coverage, null-vs-zero distinctions and provider namespace.
- Every feature snapshot must be available by the target FPL deadline.
- Target-fixture outcomes must never enter inputs.
- Use identical folds and the exact common validation cohort for all compared models.
- Fit preprocessing, calibration, model parameters and hyperparameters within each chronological training fold.
- Post-deadline event labels are explanatory-only.

Current provider constraints:
- StatsBomb 360 is sampled context, not continuous tracking.
- Wyscout 2017/18 remains a separate provider namespace and requires a verified season-scoped FPL identity bridge.
- 11footy candidate identities are not automatically verified; its panel remains ineligible until crosswalk approval.
- Retrospective FPL/provider snapshots are not proven pre-deadline archives.

## Implementation delivered in this branch

- `scripts/evaluate_fpl_decision_quality.py`: full-cohort point-error metrics, forecast bands, threshold probability calibration, ranking metrics and explanatory-only post-deadline annotations.
- `scripts/cta_four_layer_pipeline.py`: A/B/C schema, provenance, coverage and deadline contracts; explicit independent model-track input contracts.
- `scripts/two_pm_transformer.py`: optional PyTorch shared temporal encoder with separate minutes and conditional-points heads.
- Tests cover haul retention, probability scoring, ranking diagnostics, deadline leakage rejection, explicit missingness and Transformer outputs.

## Not yet completed

- A/B/C are not yet populated by a verified common multi-season player-fixture panel; feature contracts exist but provider adapters are not fully wired into one panel.
- The standalone 2PM-Transformer has architecture and forward-pass tests, but no trained walk-forward experiment, calibration, hyperparameter selection or paired cluster-bootstrap report.
- The optional A/B/C-augmented Transformer experiment has not been run.
- The decision-quality evaluator is a standalone module; the existing historical walk-forward report has not yet been migrated to emit all its outputs. Existing historical results remain unchanged and authoritative.
- Current multi-season FPL history is retrospective, not a verified pre-deadline snapshot; this limits the strength of point-in-time claims.
- CTA remains RESEARCH_ONLY / DO_NOT_PROMOTE, weight zero. No recommendation engine may consume these research outputs.

## Next acceptance gates

1. Complete verified provider-to-FPL identity panels and point-in-time feature snapshots.
2. Build the integrated A/B/C player-fixture panel with explicit missingness, provenance and deadline guards.
3. Independently build conventional FPL temporal sequences for the standalone 2PM-Transformer.
4. Train each track only within expanding-season folds; fit preprocessing and calibration on earlier training/calibration blocks.
5. Compare models on the exact common validation cohort. Report MAE, RMSE, 6+/8+/10+ calibration, ranking lift/regret, tail diagnostics, paired player-season cluster intervals and season stability.
6. Run the optional A/B/C augmentation ablation only after the independent tracks are established.
7. Promote nothing unless it demonstrates repeatable incremental value over conventional baselines.
