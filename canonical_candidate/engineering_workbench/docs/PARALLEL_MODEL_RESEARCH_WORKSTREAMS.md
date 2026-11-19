# Parallel Model Research Workstreams

Status: ACTIVE RESEARCH PLAN
Branch: feat/four-layer-2pm-transformer-evaluation

## The four independent workstreams

### 1. External benchmark system

Collect authentic historical pre-deadline forecasts wherever recoverable, and freeze all accessible provider forecasts prospectively from GW11 onward. Preserve each product tier and model variant separately. Raw player-level provider data remains in the private archive. Evaluate only on exact common player-GW/horizon cohorts, with source coverage shown separately.

### 2. Independent ABC FPL predictor

The integrated A/B/C predictor maps contextual football intelligence to expected FPL performance:

- A — Temporal Football Value: progression, penetration, sequence value and attacking threat.
- B — Risk / Defensive Intelligence: defensive actions, duel outcomes, pressure and opponent threat.
- C — Player Intelligence: role, availability, involvement, creation, reception and realization.

It must be trained and evaluated using A/B/C inputs only. A conventional FPL-history model is a separate comparator, not an input to the standalone ABC predictor. Evaluate A, B, C, AB, AC, BC and ABC, as well as conventional-history-plus-ABC ablations. Missing evidence stays null with explicit coverage.

Current historical evidence is limited to a small, survivorship-biased Wyscout/11footy identity subset from 2017/18. Historical provider vintages are retrospective, not point-in-time verified. The first next step is an expanding whole-gameweek walk-forward evaluation, with player-fixture forecasts summed to player-gameweek before scoring.

### 3. Standalone conventional 2PM-Transformer

The 2PM-Transformer remains independent and uses conventional FPL history: minutes, appearance, points, xG/xA and related lagged FPL information. It must never consume A/B/C features in its standalone track. Continue its independent architecture, calibration, loss, sequence and tail-error optimization.

**Current controlled experiment:** a position-aware 2PM ablation is implemented as a separate base-vs-position comparison. It adds only four FPL position indicators, uses identical expanding-season folds and seeds, exports predictions runner-locally, and compares exact matched player-GWs with player-season clustered intervals. Its workflow is running; results are pending. The source position labels are retrospective and do not yet constitute deadline-vintage proof.
### 4. CTA tool / football-intelligence engine

Optimize the underlying CTA tool independently from both point predictors. Its objectives are correct football-event interpretation and high-quality contextual features: identity-safe event aggregation, sequence construction, direction, xT, pass success, pressure/defensive context, player availability and Python/JavaScript parity.

Engineering parity is not predictive validity. The engine can be considered improved only when its own structural, event-level and feature-quality tests improve without breaking parity or data provenance. New engine features enter ABC only through explicit, versioned ablations after they pass their own checks.

## Cross-improvement experiments — only after independent baselines

Run these as separate experiments on identical chronological folds and player-GW cohorts:

1. ABC versus standalone 2PM.
2. 2PM plus ABC features versus standalone 2PM.
3. ABC plus out-of-fold 2PM expected-points / minutes signals versus standalone ABC. The 2PM signals must be generated without training on the target fold.
4. Improved CTA-engine feature versions versus the prior ABC feature version.
5. If useful, test whether residual patterns from either predictor identify missing features for the CTA engine; do not feed in-sample residuals back into training.

The core models remain independent. No forecast provider's output is a model input. Do not blend or promote based on one metric, one gameweek or a retrospective-only experiment.

## Common comparison contract

- Same target definition, exact player-GW cohort and deadline information set.
- Expanding chronological folds; split at whole FPL gameweek boundaries.
- Train-only preprocessing and calibration; nested chronological tuning for hyperparameters.
- Report MAE, RMSE, signed bias, error tails, ranking quality and top-k decision metrics.
- Paired player-cluster bootstrap intervals for model differences.
- Include full coverage and missingness; no missing-to-zero imputation.
- Report source vintage status separately from chronological feature construction.
- Keep prospective GW11 onward results distinct from retrospective reconstruction.
- Preserve model versions, feature lists, data hashes, fold boundaries and run manifests.

## Promotion rule

ABC, 2PM and the CTA engine are not promoted by virtue of being connected or having matching code. Each first needs independent, repeatable evidence. Synergy is a later hypothesis to test, not an assumption.
