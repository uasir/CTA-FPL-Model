# Milestone 2 model-layer audit — 2026-11-20

Status: **IN PROGRESS / RESEARCH ONLY / NO MODEL PROMOTION**

This audit records the model-layer evidence and the next comparability gate. It does not change the five-milestone sequence or mark Milestone 1 complete.

## 1. Independent model tracks

Keep three distinct research outputs:

1. **Integrated ABC predictor:** A/B/C football-intelligence features, evaluated independently.
2. **Conventional 2PM predictor:** FPL history and context only, with separate minutes/appearance and conditional-points distributions.
3. **Optional ABC-augmented 2PM:** a later ablation after tracks 1 and 2 have independent results.

Do not make ABC dependent on the Transformer, and do not feed CTA features into the conventional 2PM control.

## 2. Evidence currently available

### Standalone 2PM-Transformer

Workflow run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44700800076

- Completed successfully: nine expanding-season folds, with base and position variants evaluated on the same folds and player-gameweek keys.
- Base model pooled point-error cohort: 214,956 player-gameweeks; MAE 1.15517; RMSE 2.14126.
- The model also reports 6+, 8+ and 10+ probability diagnostics, forecast-band errors and tail-error concentration.
- Position ablation did not establish incremental value: macro Spearman was 0.69322 for base versus 0.69190 with position; top-100 selected mean points were 3.55919 versus 3.56214. The season-cluster bootstrap interval for the selected-mean difference crossed zero. Calibrated MAE/RMSE were marginally better for base (1.143429 / 2.140013) than position (1.143503 / 2.141651).
- **Decision:** retain the simpler base feature set as the control; do not promote position features from this single retrospective ablation.
- Point-in-time source vintages remain unverified. This is retrospective research, not a prospective accuracy claim.

### Historical ABC

Latest historical Wyscout/11footy evaluation recorded in draft PR #47:
- 800 player-gameweeks in the evaluated holdout.
- FPL-history-only MAE/RMSE: 2.429 / 3.131.
- ABC MAE/RMSE: 2.382 / 3.110.
- This is a small, selected 2017/18 cross-provider cohort with retrospective source vintages. It is an exploratory signal only; it does not establish generalisable or prospective uplift.

### Current-season ABC panel

The 2026/27 panel build is structurally useful for prospective collection, but it is a single-season snapshot and is not a training or validation archive. Missing player-level progression, dangerous-receipt, pressure/turnover and role-stability features remain null; contextual-threat score remains withheld until calibrated.

## 3. Comparability defect to resolve before interpreting ABC versus 2PM

The existing `compare_abc_with_2pm_same_cohort.py` intersects forecasts on exact player-GW keys and checks that official actual points agree. That is a valuable validation-cohort control, but it does **not** yet make the model experiment fold-aligned:

- ABC is evaluated with expanding whole-gameweek folds inside 2017/18, trained on the Wyscout/11footy-matched cohort.
- The 2PM call uses `evaluate_fold(..., "2017-18")`: it trains on the prior 2016/17 season, calibrates on the latest 20% of that prior season, and validates on 2017/18.
- The 2PM fit population is the broad FPL universe; ABC's training population is the smaller verified CTA cohort.
- The validation intersection can therefore be identical while training periods, training populations and calibration procedures differ.

Consequently, the existing result can be described as a **common-validation-cohort comparison**, not a fully matched model experiment and not evidence that one architecture is superior.

## 4. Required next engineering deliverable

Build a fold-aligned ABC-versus-2PM evaluator with an explicit comparison contract:

1. Define one ordered list of whole-GW train, calibration and validation blocks. No fixture-level split.
2. For each fold, define a shared eligible player-GW training population and exact common validation population. Record all excluded keys and reasons; never silently drop mismatches.
3. Train ABC variants and the conventional 2PM model using the same training target rows and same validation deadlines. The 2PM may use conventional FPL history as sequence inputs, but its target rows must obey the shared cohort rule.
4. Fit all preprocessing and calibration only within the fold's training/calibration window. Keep raw and calibrated results separate.
5. Require exact FPL element + season + GW keys and exact official actual-point agreement. Preserve double-gameweeks at player-GW grain.
6. Report full-cohort MAE, RMSE, bias, error quantiles, haul probability calibration where supported, deadline-local Spearman/top-k selection utility, and paired player-cluster uncertainty. Retain every realised outcome, including exceptional hauls.
7. Report coverage and sample composition alongside performance. Distinguish model capability from the effect of a restricted CTA-verified population.
8. Keep all outputs research-only until point-in-time vintages, rights, identity coverage and multi-season robustness are validated.

A separate descriptive comparison may still be retained for historical context, but it must be labelled as such and must not be used as the promotion test.

## 5. Milestone 2 gates

- [ ] Independent ABC and conventional 2PM input contracts remain separate.
- [ ] ABC feature availability, missingness and source provenance are reported by fold.
- [ ] Standalone 2PM walk-forward is reproducible on pinned inputs.
- [ ] Base-vs-position ablation remains paired and position features remain unpromoted absent repeatable gain.
- [ ] ABC-vs-2PM comparison uses shared folds, train/calibration/validation boundaries and exact cohorts.
- [ ] External forecast benchmarks are captured with provider variant, generation time, capture time, coverage and immutable hashes.
- [ ] Multi-season point-in-time validation and data-rights gates are satisfied before any recommendation weight is enabled.


## 6. Additional reporting gap found in the 2PM workflow

The evaluator computes matched conventional two-part, direct-Ridge and last-five persistence comparisons, plus paired cluster-bootstrap results. However, the successful Actions workflow's aggregate-only summary publishes the pooled Transformer point-error/probability diagnostics and the base-versus-position ablation, but omits those conventional comparator results and paired intervals.

Therefore the 214,956-row base-model MAE/RMSE are descriptive model errors, not evidence that the Transformer beats a conventional baseline. The next 2PM reporting change must publish aggregate-only metrics for:
- calibrated conventional two-part comparator;
- direct Ridge comparator;
- last-five persistence comparator;
- paired player-season cluster-bootstrap deltas for Transformer versus each comparator;
- validation cohort counts and fold coverage.

Keep player-level predictions runner-local. This reporting change does not require uploading raw data or per-player predictions.

**Current disposition:** 2PM base remains the control; position features are not adopted; ABC remains an exploratory independent candidate; no model is connected to recommendation weights.