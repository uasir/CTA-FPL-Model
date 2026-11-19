# CTA-FPL Research Execution Framework

Status: active research protocol  
Scope: external FPL forecast benchmarks, ABC contextual model, conventional-history 2PM Transformer, and the CTA feature/tool engine.  
Data boundary: this public repository may contain code, protocols, hashes, provenance metadata, and aggregate evaluation results only. Raw provider forecasts and player-level restricted research data remain in the private archive.

## 1. Research objectives

The project has four independent objectives:

1. Establish realistic, reproducible external benchmarks using actual published FPL forecast outputs.
2. Improve and validate the ABC contextual predictor independently.
3. Improve and validate the conventional-history 2PM Transformer independently.
4. Improve the CTA feature/tool engine (event parsing, xT, xSuccess, identity joins, temporal aggregation, and coverage) independently of point-prediction model results.

Only after these tracks have independent evidence may we test cross-model augmentation or combination. External provider forecasts are comparators, not training inputs or blend components.

## 2. Workstream separation

| Track | Inputs | Primary question | Promotion gate |
|---|---|---|---|
| External benchmarks | Frozen provider xP outputs, official FPL outcomes | How do real tools perform on the same player-GW cohort? | Reproducible source, vintage, coverage, and scoring audit |
| ABC | Lagged FPL history plus eligible contextual A/B/C features | Do contextual signals add predictive or ranking value? | Multi-season chronological evidence against history-only |
| 2PM | Conventional lagged FPL history and derived temporal features | Can the temporal/hurdle model improve point forecasts? | Walk-forward improvement with stable tails and calibration |
| CTA engine | Event data, identity maps, xT/xSuccess and aggregation code | Are features correctly extracted, joined, and temporally valid? | Unit/parity/coverage tests plus downstream feature validity |
| Interaction experiments | Frozen, independently validated ABC and 2PM outputs | Does either model add incremental value to the other? | Same folds, rows, target, training cutoff, and paired inference |

No track may claim success solely because another track improved.

## 3. Data and point-in-time contract

Every forecast row must identify, where available:

- provider and provider variant;
- player identifier and verified official FPL element identifier;
- gameweek and fixture grain;
- forecast value and forecast units;
- provider model/version and provider-generated timestamp;
- retrieval timestamp and official deadline;
- raw snapshot path and SHA-256;
- normalization version and identity-resolution status;
- source-vintage / point-in-time status.

Rules:

1. A forecast is point-in-time verified only when its actual captured vintage is demonstrably before the relevant deadline. A historical page reconstructed later is retrospective, even if it describes an earlier GW.
2. Missing values remain null with an explicit reason. Never replace missing xP, xMins, xG, xA, or contextual fields with zero unless zero is the true observed value by definition.
3. Keep provider variants separate (for example, served xP and odds-derived xP).
4. Preserve native provider grain. Any fixture-to-player-GW aggregation must be explicit, deterministic, and audited.
5. Validate player and fixture IDs against official FPL bootstrap/fixture data. Name-only joins require a reviewed crosswalk and ambiguity report.
6. Freeze raw provider snapshots privately before scoring. Public outputs may expose hashes and aggregate results, not restricted player-level forecasts.
7. Score against official FPL event-live points only after the official event is finished. Retain provider-reported actuals as audit fields only.

## 4. Benchmark design

### 4.1 Cohorts

Report three distinct cohorts for each GW and evaluation window:

- provider-specific valid cohort;
- common intersection across the providers being compared;
- broad eligible FPL cohort for internal models, where source coverage permits.

Never imply that a provider's top-N list represents all players. If a provider only publishes a selected cohort, label the selection mechanism and report its coverage.

Historical reconstructed data and prospective frozen data must never be pooled without explicit stratification. Report source coverage and point-in-time status beside every score.

### 4.2 Metrics

Core point-forecast metrics:

- MAE;
- RMSE / MSE;
- signed bias (forecast minus actual);
- median and upper quantiles of absolute error;
- large-error rates at predeclared thresholds;
- calibration slope/intercept and score-distribution diagnostics.

Ranking metrics, computed separately per GW:

- Spearman rank correlation;
- NDCG@10 and NDCG@15;
- top-10 and top-15 overlap;
- mean realized points of selected top-k players.

Captain analysis, where relevant:

- captain pick realized points;
- regret relative to the best eligible captain;
- top-captain hit rate.

Probability metrics (Brier, log loss, reliability curves) are allowed only when the source model emits calibrated event probabilities. Do not infer probabilities from xP alone.

Do not pool top-k overlap across GWs. Summarize the per-GW values with distributions and uncertainty.

### 4.3 Statistical comparison

- Use paired comparisons on identical player-GW rows.
- Cluster bootstrap by player (or player-season where appropriate), preserving repeated observations.
- Report interval estimates and effect sizes, not only point estimates or p-values.
- Use chronological walk-forward splits; all preprocessing, imputation, feature selection, calibration, and hyperparameter selection must be fitted on training data only.
- Keep a final untouched chronological holdout for model-selection confirmation.
- Record both average performance and tail-risk behaviour. A lower MAE does not compensate automatically for materially worse RMSE or tail error.
- Provider agreement is not evidence of accuracy.

## 5. ABC contextual model plan

### 5.1 Feature families

- A: on-ball progression, passing, carrying, chance creation, and threat actions.
- B: off-ball / receiving / pressure / role-context signals where source coverage and identity are reliable.
- C: team and opponent context, match state, possession, territorial pressure, and defensive environment.

Each feature must carry source, timestamp, grain, coverage, and missingness metadata. Features unavailable in a source remain unavailable; do not fabricate proxy values without a separately named feature definition.

### 5.2 Required ablations

Evaluate on identical rows and folds:

- FPL history only;
- A only, B only, C only;
- AB, AC, BC;
- ABC;
- FPL history + A, + B, + C;
- FPL history + AB, + AC, + BC;
- FPL history + ABC.

The key question is incremental value over FPL history, not whether contextual features correlate with points.

### 5.3 Expansion safeguards

Expand beyond the current small Wyscout/11footy-linked cohort by season and source only when identity, coverage, and temporal cutoffs pass validation. Publish cohort composition and survivorship diagnostics. Never silently broaden the cohort by weakening identity rules.

## 6. 2PM Transformer optimization plan

Keep 2PM independent from ABC during its optimization.

Diagnostic sequence:

1. Reproduce the existing walk-forward baseline and preserve its exact cohort and feature vintage.
2. Inspect predicted-versus-realized distributions by minutes band, position, price/role cohort, and predicted-score decile.
3. Decompose error into appearance/minutes and conditional-points components.
4. Measure calibration slope/intercept, residual quantiles, high-score recall, and large underprediction/overprediction rates.
5. Compare the existing five minutes classes and six conditional-points bands against simpler and finer alternatives using training-only selection.
6. Test training-only calibration (affine and monotonic where justified) separately from model fitting.
7. Test loss reweighting or distributional objectives only as controlled ablations; monitor whether tail gains damage MAE or calibration.
8. Compare with two-part, Ridge, persistence, and season-adaptive baselines on identical folds.

Do not tune against the FPL Wildcard top-50 cohort or the small ABC matched cohort. A change is retained only when it improves the predeclared validation objective and does not create unacceptable regressions in secondary metrics.

## 7. CTA tool-engine quality plan

The engine is not the same thing as a points predictor. Its quality gates are:

- event parsing correctness and schema validation;
- stable player/team identity crosswalks;
- event-to-feature unit tests;
- xT grid versioning and reproducibility;
- xSuccess definition and calibration audit;
- correct fixture-to-GW aggregation, including double gameweeks;
- lagged feature cutoffs and no target-GW leakage;
- null preservation and explicit coverage reporting;
- Python/JavaScript parity tests;
- source provenance and deterministic output hashes.

Feature quality is reported separately from downstream predictive value. A correct feature extractor is necessary but not sufficient evidence that the feature improves FPL forecasts.

## 8. Interaction and combination experiments

Only begin after independent ABC and 2PM baselines are frozen.

Use identical chronological folds, target definition, eligible rows, and forecast cutoffs. Compare:

1. 2PM alone;
2. ABC alone;
3. 2PM + ABC feature augmentation;
4. 2PM + ABC forecast residual correction;
5. a simple calibrated blend as a reference only.

Train every combination only on training folds. Include ablations that remove each contextual family. Report incremental MAE, RMSE, bias, tail error, ranking metrics, paired cluster intervals, and coverage. If augmentation does not add stable value beyond 2PM, retain independent outputs rather than forcing a blend.

## 9. Decision gates

| Gate | Evidence required | Permitted status |
|---|---|---|
| G0 — Data integrity | IDs, grain, timestamps, nulls, actual points audited | Eligible for analysis |
| G1 — Reproducible baseline | Frozen cohort, code/version, repeatable metrics | Baseline established |
| G2 — Independent value | Chronological multi-fold improvement over relevant baseline | Research candidate |
| G3 — Robustness | Stable across seasons/cohorts, tail and calibration checks | Validation candidate |
| G4 — Incremental interaction | Same-fold paired evidence of added value | Augmentation candidate |
| G5 — Operational readiness | Prospective captures, monitoring, fallback, documented limitations | Eligible for controlled use |

No arbitrary accuracy target is imposed in advance. Performance expectations are derived from observed external benchmarks and uncertainty. No promotion occurs from a single season, single cohort, or retrospective reconstruction.

## 10. Experiment ledger template

Every run should record:

- experiment ID, date, code commit, data snapshot hashes;
- track and hypothesis;
- training/validation/test dates and cutoffs;
- player-GW counts, player clusters, source coverage;
- features and ablations;
- baseline and candidate metrics;
- paired uncertainty intervals;
- missingness, identity exclusions, and mismatch audit;
- point-in-time status;
- decision: retain, reject, or investigate;
- next experiment and reason.

## 11. Current execution order

1. Keep the four-provider GW11 prospective benchmark pipeline intact; validate normalization/scoring and wait for official event completion before scoring.
2. Expand the ABC historical panel with strict multi-season identity and coverage audits.
3. Run the 2PM distribution/tail diagnostic and controlled loss/calibration ablations independently.
4. Continue CTA engine correctness, parity, and feature-coverage work.
5. Once independent results are stable, run the pre-registered ABC/2PM interaction experiments.
6. FPL Review and FPL Forecaster historical mapping are explicitly deferred and must not block these tracks.

## 12. Non-negotiable safeguards

- Do not merge PRs without explicit authorization.
- Do not publish raw provider forecasts or player-level restricted rows.
- Do not call retrospective reconstructed forecasts prospective.
- Do not use target-GW outcomes or post-deadline information in features, calibration, or selection.
- Do not silently impute missing forecasts or features.
- Do not promote a model because it wins one metric while materially losing on another.
- Keep ABC, 2PM, and CTA engine work independently measurable.
