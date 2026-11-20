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




### Follow-up implementation — 2026-11-20 11:17 UTC

The 2PM workflow summary was updated in commit `1c79ce45506bfe5123db58978bbec9255611d345` to publish aggregate-only base-model comparator metrics, paired bootstrap outputs, calibrated expected-points metrics and per-season fold coverage. Player-level predictions remain runner-local. The rerun is queued as Actions run [44726375243](https://github.com/uasir/CTA-FPL-Model/actions/runs/44726375243); this gate remains pending until it completes and the aggregate outputs are reviewed.

## 6. Additional reporting gap found in the 2PM workflow

The evaluator computes matched conventional two-part, direct-Ridge and last-five persistence comparisons, plus paired cluster-bootstrap results. However, the successful Actions workflow's aggregate-only summary publishes the pooled Transformer point-error/probability diagnostics and the base-versus-position ablation, but omits those conventional comparator results and paired intervals.

Therefore the 214,956-row base-model MAE/RMSE are descriptive model errors, not evidence that the Transformer beats a conventional baseline. The next 2PM reporting change must publish aggregate-only metrics for:
- calibrated conventional two-part comparator;
- direct Ridge comparator;
- last-five persistence comparator;
- paired player-season cluster-bootstrap deltas for Transformer versus each comparator;
- validation cohort counts and fold coverage.

Keep player-level predictions runner-local. This reporting change does not require uploading raw data or per-player predictions.


## 7. Completed aggregate comparator run — 2026-11-20

Workflow run [44726375243](https://github.com/uasir/CTA-FPL-Model/actions/runs/44726375243) completed successfully on commit `1c79ce45506bfe5123db58978bbec9255611d345`. All contract tests, pinned panel build, nine base folds, nine position folds, exact-key ablation, aggregate summary and privacy guard passed. The output is still explicitly research-only; source vintages are retrospective and player-level predictions remained runner-local.

### Pooled point-error evidence (214,956 player-gameweeks; nine validation seasons)

| Model | MAE | RMSE |
|---|---:|---:|
| 2PM base Transformer | 1.155169 | 2.141261 |
| 2PM affine-calibrated | 1.143429 | 2.140013 |
| Conventional two-part calibrated | 1.158262 | 2.151422 |
| Direct Ridge | 1.172428 | 2.147593 |
| Last-five persistence | 1.190693 | 2.301198 |

Player-season cluster bootstrap, 6,645 clusters and 1,000 replicates:
- Raw 2PM minus calibrated conventional two-part MAE 95% CI: [-0.004791, -0.001437].
- Affine-calibrated 2PM minus calibrated conventional two-part MAE 95% CI: [-0.016402, -0.013232].
- Raw 2PM minus direct Ridge MAE 95% CI: [-0.018846, -0.015729].

These are statistically clear retrospective point-error improvements on the tested cohort. They do not establish prospective validity, and they do not establish a decision-level advantage.

### Position ablation decision

On the same 214,956 player-GWs and 332 deadlines:
- Raw MAE: base 1.155169; position 1.155608.
- Raw RMSE: base 2.141261; position 2.142320.
- Deadline-local macro Spearman: base 0.690174; position 0.689207.
- Deadline-local macro selected mean points at top 100: base 3.559187; position 3.562139.
- Paired season-cluster bootstrap selected-mean delta (position minus base) 95% CI: [-0.015273, +0.022492].
- Paired player-season cluster-bootstrap MAE delta 95% CI: [-0.000243, +0.001082].

**Decision unchanged:** position features are not adopted. The selected-mean difference is tiny and uncertain; rank correlation and point-error metrics lean toward the simpler base model.

### Important ranking-metric qualification

The pooled model summary's top-100 selected-mean figures (base 5.08, affine 5.79, calibrated conventional 5.32) are pooled across validation rows and are not a deadline-by-deadline FPL selection evaluation. The position ablation does separately calculate ranking metrics within each of 332 deadlines, but the baseline comparator output does not yet publish the same paired deadline-local ranking comparison for all model variants.

Do not use pooled top-100 values as evidence of FPL decision utility. Add a paired per-deadline ranking evaluation before any ranking or selection claim.

## 8. Fold-aligned ABC-versus-2PM comparison: data-grain constraint

Code inspection found a second comparability issue beyond the differing train populations:
- ABC currently fits Ridge on **player-fixture** rows and sums fixture predictions to player-GW.
- 2PM trains and predicts on **player-gameweek** rows.
- The current ABC candidate model also uses expanding 2017/18 folds, while the Transformer evaluation uses expanding prior-season folds.
- ABC A/B/C inputs include both fixture-level event counts/rates and player-level rolling features; simply summing every ABC feature across double-gameweeks would be invalid.

Therefore the next evaluator must first define a typed player-GW aggregation contract for ABC features:
1. FPL player-GW target and conventional-history fields: one exact value per player-GW; fail on conflicting repeated values.
2. Fixture-level additive event counts: sum only where the source definition establishes additivity.
3. Rates and percentages: recompute from numerator/denominator when available; otherwise use a documented exposure-weighted aggregation or mark unavailable.
4. Rolling/player-level snapshot features: retain the single pre-deadline snapshot; fail if fixture rows disagree.
5. Team/opponent context: preserve fixture-specific values as separate context features or use a predeclared aggregation; never average/sum blindly.
6. Keep explicit coverage, source vintage and aggregation provenance per player-GW feature.

After that transformation, define identical whole-GW fit/calibration/validation blocks and exact shared player-GW keys for both tracks. Restrict both models' **target rows** to the shared CTA-eligible population for the primary matched-capability experiment; separately report the broader 2PM universe as a distinct population-generalisation analysis. For 2PM, historical sequence rows may provide lagged conventional inputs, but target labels used to fit/calibrate must follow the shared cohort plan. Fit/calibrate only on earlier blocks, never validation.

The evaluator must report (a) full-cohort MAE/RMSE/bias and tail errors, (b) within-deadline Spearman and top-20/top-100 realised selection utility, (c) paired player-cluster uncertainty, (d) per-fold sample/feature coverage, and (e) explicit excluded-key reasons. Keep raw and calibrated outputs separate.

**Next implementation task:** build and test the ABC player-GW feature aggregator and fold-plan contract first. Do not attempt the joint model comparison until this grain contract passes its tests.


## 9. ABC player-GW aggregation contract implemented

Added:
- `scripts/aggregate_abc_player_gameweeks.py`
- `tests/test_aggregate_abc_player_gameweeks.py`

The aggregator now:
- groups by exact season + FPL element ID + GW;
- sums only fixture-level target points and minutes labels;
- retains an ABC or conventional-history feature only when all fixture rows agree within tolerance;
- marks feature values as MISSING, PARTIAL or CONFLICT rather than summing or blindly averaging them;
- requires the exact fixture-ID set from the pinned FPL history reference for each player-GW, not just a fixture count, before marking the row eligible;
- rejects duplicate player-fixture rows and blocks incomplete target labels or inconsistent feature cutoffs;
- retains source provenance and per-feature aggregation status.

This is deliberately conservative. Conflicting fixture-specific opponent context becomes null at player-GW grain until a separate context aggregation is specified. Missing/conflicting feature values do not become zero.

CI run [44732404991](https://github.com/uasir/CTA-FPL-Model/actions/runs/44732404991) completed successfully on commit `30358957ac30be59f59503111693b6f439b36517`: JavaScript contracts, Python core tests, the full engineering pytest suite, and all four identity-crosswalk validators passed. The new aggregation tests are included in the successful engineering suite.

**Remaining before fold-aligned comparison:** provide the independent official player-GW fixture-ID universe file, run the aggregator on the historical Wyscout panel, inspect the conflict/coverage report, and then construct identical fit/calibration/validation cohorts for ABC and 2PM.


## 10. Independent fixture-reference builder added

Added `scripts/build_abc_expected_fixture_universe.py` and unit tests. It derives the expected player-fixture IDs from the independently built, pinned Vaastav FPL history panel, normalizes season labels for joining, and checks fixture-level points and minutes against the ABC panel before emitting the reference CSV.

This source is a pinned historical FPL export, **not** a verified point-in-time or live official API snapshot. The script fails closed on missing player-GW keys, missing fixtures, extra ABC fixtures, or any fixture-level target mismatch. The resulting reference CSV is then consumed by the strict ABC player-GW aggregator.

The combined CI run [44732745533](https://github.com/uasir/CTA-FPL-Model/actions/runs/44732745533) passed, including the full engineering test suite and all identity crosswalk validators. The follow-up terminology change distinguishes the pinned reference export from official/live FPL data.

**Current disposition:** 2PM base remains the control; position features are not adopted; ABC remains an exploratory independent candidate; no model is connected to recommendation weights.