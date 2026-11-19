# FPL Multi-Season Data Readiness

## Purpose

Prepare the FPL-points predictor for multi-season chronological evaluation. This is a data-eligibility gate, not a model promotion decision. The four-layer CTA architecture remains unchanged, and CTA-derived features retain zero recommendation weight until incremental out-of-sample value is demonstrated.

## Source audit

### Official FPL public API

- The ingestion pipeline captures the current bootstrap, fixtures, and each player's element-summary history.
- Source and normalized-output hashes are recorded in `source_metadata.json`, together with capture time and a deterministic source snapshot ID.
- A current capture can support a genuinely upcoming deadline when fetched before that deadline.
- The ingestion workflow currently retains its uploaded FPL snapshot artifact for 90 days. Hashes prove the identity of captured files but do not make the raw snapshots a durable multi-season archive; a long-term archive/manifest retention path is still required.
- It cannot recreate historical pre-deadline vintages. Earlier player history may have been retrospectively revised, so historical training rows remain `NOT_VERIFIED` for strict point-in-time backtesting.
- The official API feed is therefore suitable for current-season forward snapshots and as a source of final historical targets, but not as proof that a feature value was available at an old deadline.

### vaastav/Fantasy-Premier-League

- Public repository inspected: https://github.com/vaastav/Fantasy-Premier-League
- It contains season folders and gameweek-level CSV files, including 2017/18 through 2024/25.
- Its README states that weekly updates stopped after 2024/25 and describes only three subsequent major updates per season.
- The README explicitly warns that the `xP` field may contain post-match information and should be shifted or excluded.
- GitHub reports the repository licence as `Other` / SPDX `NOASSERTION`; this metadata is recorded as provenance, not used as a data-discovery exclusion.
- **Decision: use the dataset to advance internal project research and model development.** We do not claim authorship or ownership of the source data, and no dataset distribution is planned. Keep source files and player-level panels out of the Git repository while retaining attribution, pinned source revision, and per-file hashes. Historical gameweek files are not independently proven to be exact deadline-time snapshots.

### Multi-season research implementation

- Pinned source revision: `d7b05b51d137bfefef4b692386d18c610975b9b9`.
- Research seasons: 2016/17 through 2025/26; the incomplete 2026/27 season is excluded from the initial multi-season holdout.
- Builder: `scripts/build_vaastav_fpl_multiseason_panel.py`.
- Manual workflow: `.github/workflows/cta-fpl-multiseason-research.yml`.
- The builder downloads each season's `gws/merged_gw.csv` into runner-local storage, hashes each source file, builds player-season-GW lagged features, and runs a chronological 80/20 gameweek holdout.
- FPL element IDs are treated as season-scoped. The FPL-only experiment does not pretend they are persistent cross-season identities.
- `xP`, ownership/selected counts, transfers, and post-match `modified` values are explicitly excluded from model features.
- No raw source files or player-level panel artifacts are uploaded by the research workflow.
- First completed run: [GitHub Actions run 44498912828](https://github.com/uasir/CTA-FPL-Model/actions/runs/44498912828), successful. It downloaded all 10 seasons (2016/17–2025/26), producing 253,900 player-fixture rows. The chronological split used 295 training gameweeks and 74 validation gameweeks (2024/25 GW2 through 2025/26 GW38), with 190,754 training fixture rows and 55,712 validation fixture rows.
- On 54,924 scored validation player-gameweeks, the lagged FPL ridge achieved MAE 1.050478 and RMSE 2.031025, versus the last-five-gameweek-points baseline MAE 1.080018 and RMSE 2.175455. Absolute improvements were 0.029540 MAE and 0.144430 RMSE (approximately 2.7% and 6.6% relative). This is a modest positive exploratory result, not a promotion decision; there is one pooled holdout and no probability calibration or season-by-season stability test yet.
- Engineering CI after the builder and encoding regression test: [Run 44498912537](https://github.com/uasir/CTA-FPL-Model/actions/runs/44498912537), 332 tests and 3 subtests passed.
- Follow-up diagnostics: [Run 44499306152](https://github.com/uasir/CTA-FPL-Model/actions/runs/44499306152), successful. Approximately 59.7% of scored player-gameweeks had zero minutes, so the pooled MAE is strongly influenced by non-appearances. On the 22,110 player-gameweeks with positive actual minutes (a post-outcome diagnostic cohort, not a deployable selection rule), the model MAE was 1.942446 versus 2.175305 for the last-five baseline; RMSE was 2.967345 versus 3.181374. Both held-out seasons showed a positive improvement, but this still does not test whether the model can predict availability/playing time before kickoff.
- The next predictor-specific task is a two-part evaluation: forecast appearance/minutes from pre-deadline information, then forecast points conditional on playing, and combine them into an unconditional points distribution. Keep the direct points model as a comparator. Do not filter live recommendations using actual minutes or promote this retrospective result.
- The resulting scores remain exploratory: source vintages are retrospective, not verified deadline-time snapshots.

### Two-part availability and conditional-points experiment

- Evaluator: `scripts/evaluate_fpl_two_part_model.py`.
- The experiment predicts appearance probability and minutes separately, trains conditional points only on positive-minute training labels, and combines appearance probability with conditional points for unconditional expected points.
- It aggregates double-gameweek labels at player-gameweek level and never filters validation rows using actual minutes.
- Corrected full multi-season run: [GitHub Actions run 44502848341](https://github.com/uasir/CTA-FPL-Model/actions/runs/44502848341), successful. It used the same 80/20 chronological split and 54,924 validation player-gameweeks as the direct model.
- Before probability calibration, the appearance model achieved Brier 0.088220 and log loss 0.313398, versus 0.106510 and 1.365719 for the prior-five appearance-rate baseline.
- Before calibration, two-part expected-points MAE was 1.055221 versus 1.061375 for direct ridge and 1.080018 for the last-five-points baseline. Its RMSE was 2.050783, slightly worse than direct ridge at 2.034614, though better than the last-five baseline at 2.175455.
- Minutes MAE was 14.055 minutes versus 11.220 for the last-gameweek-minutes baseline; the minutes model did not win this metric.
- Positive-minute-only comparisons are post-outcome diagnostics and cannot be used to select live players.
- The calibrated evaluation reserves the latest 20% of pre-test training gameweeks for Platt calibration and leaves the final chronological test window untouched. The calibrated appearance model achieved Brier 0.093324 and log loss 0.311468; raw clipped probabilities achieved 0.093148 and 0.327838; the prior-five appearance-rate baseline achieved 0.106510 and 1.365719. Calibration improved log loss but did not improve Brier versus the raw model.
- Calibrated two-part expected-points MAE/RMSE were 1.059978/2.052511; raw two-part values were 1.057824/2.050414; direct ridge was 1.061375/2.034614. Calibration therefore retains a small MAE advantage over direct ridge but not an RMSE advantage. The raw two-part output has slightly better point MAE/RMSE than its calibrated counterpart.
- Minutes MAE remains 14.055 minutes versus 11.220 for the last-gameweek-minutes baseline; the minutes model did not win this metric.
- Calibrated full research run: [GitHub Actions run 44503481951](https://github.com/uasir/CTA-FPL-Model/actions/runs/44503481951), successful. Engineering CI: [run 44503481955](https://github.com/uasir/CTA-FPL-Model/actions/runs/44503481955), 336 tests and 3 subtests passed.
- Expanding-season walk-forward evaluation was implemented in `scripts/evaluate_fpl_walk_forward.py`, with one full held-out season per fold and calibration drawn only from earlier seasons. Successful initial run: [GitHub Actions run 44504997563](https://github.com/uasir/CTA-FPL-Model/actions/runs/44504997563). It completed 9 folds from 2017/18 through 2025/26 and scored 214,956 player-gameweeks.
- Across the nine folds, appearance Brier/log loss were 0.105105/0.345895 for calibrated probabilities, 0.104476/0.383109 for raw clipped probabilities, and 0.119955/1.508366 for the prior-five appearance-rate baseline. Calibration substantially improved log loss over raw and baseline probabilities, but raw probabilities had a marginally lower Brier score.
- Walk-forward expected-points MAE was 1.160736 calibrated two-part, 1.160585 raw two-part, 1.168723 direct ridge, and 1.190693 last-five baseline. The two-part model reduced MAE against direct ridge in 8 of 9 held-out seasons.
- Correct pooled RMSE, recomputed from fold-level squared errors, was 2.151449 calibrated two-part, 2.151055 raw two-part, 2.147811 direct ridge, and 2.301198 last-five baseline. Thus, two-part improved MAE but did not beat direct ridge on RMSE.
- Walk-forward minutes MAE was 16.518 versus 13.728 for the last-gameweek-minutes baseline. The current unconditional minutes regressor is not competitive and should be redesigned rather than promoted.
- Engineering CI on the latest code: [run 44505161984](https://github.com/uasir/CTA-FPL-Model/actions/runs/44505161984), 338 tests and 3 subtests passed. The exact pooled-RMSE implementation and regression test were then validated in the successful final rerun [44505162152](https://github.com/uasir/CTA-FPL-Model/actions/runs/44505162152).
- Next engineering priority: replace the weak unconditional minutes regression with a better conditional-minutes or minutes-band model, then test whether that improves the expected-points distribution. Keep all actual-minute labels out of prediction-time filtering. Historical source vintages remain unverified pre-deadline snapshots, so all model results remain research-only.

### Existing CTA-linked historical panel

- The existing Wyscout/11footy/FPL research panel covers 2017/18 only.
- It contains 91 verified cross-provider player identities and 2,693 verified player-fixture rows across 380 mapped EPL fixtures.
- This is useful for a single-season paired CTA experiment, but not enough for a multi-season CTA claim.
- 11footy source data is labelled CC BY-NC 4.0. Retain attribution and source provenance; this label is not used as a data-discovery exclusion, and no dataset distribution is planned.

## Feature-integrity decisions

- Missing provider metrics remain missing. Training uses training-window medians plus explicit missingness indicators; observed zero is not conflated with missing.
- Missing/non-finite targets fail closed rather than becoming zero.
- Imputation values and scaling statistics are fitted on training rows only.
- Target-gameweek fixture count is not used as a predictor or to scale historical features.
- Fixture difficulty is excluded from the exploratory FPL model because no archived pre-deadline fixture snapshot proves its historical value.
- Historical ownership percentages based on current bootstrap denominators are not used as model features.
- FPL `xP` is excluded from historical features because the inspected dataset warns of possible post-match leakage.
- Historical FPL player statistics are structurally lagged by kickoff/deadline, but source-vintage revisions remain an explicit limitation.

## Data and experiment eligibility

Data discovery is driven by predictive usefulness, coverage, quality, temporal structure, and reproducibility. An unclear or non-commercial repository licence label is not, by itself, a reason to exclude a useful dataset from user-directed internal research. Preserve source attribution, repository revision, file hashes, and provenance; do not claim authorship or ownership of third-party data. The project is not planning dataset distribution.

The model-quality gates remain:
1. stable season, player, fixture, and gameweek identifiers;
2. complete and correctly aggregated FPL targets;
3. features that are available before the target deadline, or an explicit warning where historical point-in-time availability cannot be verified;
4. durable source revision and file hashes; and
5. reproducible identity mapping where cross-provider joins are used.

Data can be used for exploratory experiments before all point-in-time conditions are proven, but those results must remain labelled research-only. Do not promote the ridge baseline, the two-part model, the 2PM-Transformer candidate, or CTA features into recommendation decisions without stronger chronological validation.

### Updated walk-forward verification — 19 November 2026

- Latest evaluator commit: `f3838089f2d8ff87ebd0929cd8dbbed500e4139b`.
- Full multi-season walk-forward run: [GitHub Actions run 44508165247](https://github.com/uasir/CTA-FPL-Model/actions/runs/44508165247), successful. It completed all 9 expanding-season folds (2017/18 through 2025/26) and scored 214,956 player-gameweeks.
- Engineering CI for the same code commit: [GitHub Actions run 44508165350](https://github.com/uasir/CTA-FPL-Model/actions/runs/44508165350), successful; 338 tests and 3 subtests passed.
- Appearance: calibrated Brier/log loss 0.105105/0.345895; raw clipped 0.104476/0.383109; prior-five appearance-rate baseline 0.119955/1.508366. Calibration improves log loss but is marginally worse on Brier than raw probabilities.
- Points: calibrated two-part MAE/RMSE 1.160736/2.151449; raw two-part 1.160585/2.151055; direct ridge 1.168723/2.147811; last-five-points baseline 1.190693/2.301198. Two-part improves pooled MAE over direct ridge and last-five baseline, but direct ridge retains the best RMSE. Raw two-part is marginally better than calibrated two-part on both point metrics.
- Minutes: calibrated two-part MAE 16.268 minutes; raw two-part 16.638; unconditional regression 16.518; last-gameweek baseline 13.728; prior-three-gameweek baseline 14.727; prior-five-gameweek baseline 15.676. The latest diagnostics confirm the minutes component remains weaker than simple persistence baselines.
- Calibration chronology is now explicit in every fold report: appearance-fit last gameweek, calibration first/last gameweeks, calibration positive/negative counts and appearance rate. The tests verify that the appearance-fit and calibration periods are disjoint, ordered, and entirely before the validation season.
- Decision remains `RESEARCH_ONLY / DO_NOT_PROMOTE`. Do not assign CTA weight or connect this model to live recommendations. The source-vintage limitation remains: historical exports are not verified pre-deadline snapshots.
- Next predictor task: improve minutes/availability estimation using training-only model selection and identical expanding-season folds. Candidate directions include an appearance-conditioned minutes distribution and minutes bands; compare them against last-GW, prior-three-GW and prior-five-GW baselines. Keep point-prediction model comparisons separate so a better minutes submodel is not assumed to improve expected points without evidence.


### Compact lagged-minutes experiment — 19 November 2026

- Evaluator commit: `0cb51764dcffd32a42a869216273bb9c7796097f`.
- Research run: [GitHub Actions run 44509025664](https://github.com/uasir/CTA-FPL-Model/actions/runs/44509025664), successful. All evaluation and final no-upload verification steps passed.
- Engineering CI for this evaluator commit: [GitHub Actions run 44509025343](https://github.com/uasir/CTA-FPL-Model/actions/runs/44509025343), successful; 338 tests and 3 subtests passed.
- The evaluator added direct unconditional Ridge and appearance-conditioned Ridge models using only prior-GW, prior-three-GW average, and prior-five-GW average minutes features. The same nine expanding-season folds and 214,956 validation player-gameweeks were retained.
- Pooled minutes MAE: last-GW persistence 13.727782; prior-three average 14.727045; prior-five average 15.676373; full-feature two-part calibrated 16.268261; compact two-part calibrated 16.269289; full-feature unconditional regression 16.517519; compact two-part raw 16.555608; compact unconditional Ridge 17.187541. Compact lagged features do not improve the model; last-GW persistence remains clearly superior on MAE.
- The compact two-part calibrated model is effectively tied with the full-feature two-part calibrated model on pooled minutes MAE, but neither is competitive with simple persistence. The model should not be promoted as a minutes predictor.
- Points results are unchanged: calibrated two-part MAE/RMSE 1.160736/2.151449; raw two-part 1.160585/2.151055; direct ridge 1.168723/2.147811; last-five baseline 1.190693/2.301198. The points model remains a useful research candidate, with the expected MAE/RMSE trade-off, but the weak minutes component does not justify assuming a better playing-time estimate.
- Decision: stop testing minor Ridge variants on the same three lagged minutes features. The next minutes experiment should change the problem formulation rather than simply add another linear fit: predict minutes as a conditional distribution or ordinal minutes bands (for example 0, 1–29, 30–59, 60–89, 90), with expected minutes reconstructed from calibrated band probabilities or a conditional distribution. Train and calibrate strictly within each fold's pre-validation seasons, preserve all validation player-gameweeks, and compare both MAE and probabilistic/distribution quality against persistence baselines. Then independently test whether its outputs improve FPL expected-points MAE/RMSE.
- All results remain `RESEARCH_ONLY / DO_NOT_PROMOTE`. Historical source exports are retrospective rather than verified pre-deadline snapshots.


### Minutes-band model evaluation — 19 November 2026

- Evaluator commit: `97e825fdf6c1964c49ffa9d55c9edb16752307ae`.
- Research run: [GitHub Actions run 44524183223](https://github.com/uasir/CTA-FPL-Model/actions/runs/44524183223), successful. All nine expanding-season folds (2017/18–2025/26) completed across 214,956 validation player-gameweeks. The runner-local panel and chronological evaluation completed; final workflow verification confirmed that no source data or player-level outputs were uploaded.
- Engineering CI: [GitHub Actions run 44524183333](https://github.com/uasir/CTA-FPL-Model/actions/runs/44524183333), successful. JavaScript recommendation contract tests, canonical Python feature-core tests, engineering tests, and StatsBomb, Wyscout, Opta/PulseLive and 11footy identity-crosswalk validations all passed.
- Minutes-band model: multinomial regularized softmax over five classes (0, 1–29, 30–59, 60–89, 90 minutes), with training-only imputation/scaling and chronological temperature calibration. Pooled calibrated minutes-band MAE/RMSE were 16.459/26.605; raw values were 16.922/26.616. Calibrated multiclass log loss/Brier were 0.7764/0.3730. The last-gameweek-or-training-prior baseline had MAE 13.172 and RMSE 29.358. Thus the distribution model improves RMSE and probabilistic scores against the persistence-class baseline, but does not improve minutes MAE.
- Pooled minutes MAE comparison: last-GW persistence 13.728; prior-three-GW average 14.727; prior-five-GW average 15.676; calibrated two-part regression 16.268; minutes-band calibrated 16.459; unconditional regression 16.518. The minutes-band model does not solve the minutes point-estimation problem.
- Expected-points integration on the same scored cohort: calibrated two-part MAE/RMSE 1.160736/2.151449; raw two-part 1.160585/2.151055; direct Ridge 1.168723/2.147811; minutes-band calibrated 1.180080/2.149247; minutes-band raw 1.191560/2.149116; last-five-points baseline 1.190693/2.301198. The minutes-band distribution does not improve expected-points MAE and is not competitive with the existing two-part candidate. Direct Ridge retains the lowest RMSE by a small margin.
- Interpretation: this is a useful probability/distribution experiment, not a promotion. It shows that discretized minutes probabilities can outperform the simple persistence-class baseline on distributional scoring while still failing to improve expected minutes or expected points. Keep the minutes-band head as an optional research component only; do not replace the current points model with it.
- The evaluator's chronological leakage controls were confirmed: no validation season contributes to fitting or calibration for its own fold; features are lagged; target fixture statistics are excluded; calibration is earlier than validation. Historical source files remain retrospective exports, not verified pre-deadline snapshots.
- Decision remains `RESEARCH_ONLY / DO_NOT_PROMOTE`; CTA weight remains zero and the predictor is not connected to recommendation decisions.
- Next experiment should not be another small variation of the same linear minutes head. Prioritize a points-first model that learns the conditional points distribution and availability jointly, with explicit probabilistic calibration and season-level stability reporting; retain last-GW minutes persistence as a serious benchmark. Separately audit whether the scoring function is being penalized by the coarse band representatives (0/15/45/75/90) before considering finer bins or a continuous conditional-minutes distribution.


### Training-derived minutes-band representatives — 19 November 2026

- Implementation commits: `af49bc4e97bb9767fbc3a1a794a062e61cc3e56b` (training-only class representatives) and `4ae9b8fafca7abdd382abbd8441fbaf0598be46a` (regression test).
- Research run: [GitHub Actions run 44524756937](https://github.com/uasir/CTA-FPL-Model/actions/runs/44524756937), successful. Engineering CI: [run 44524756915](https://github.com/uasir/CTA-FPL-Model/actions/runs/44524756915), successful. Wyscout audit: [run 44524764589](https://github.com/uasir/CTA-FPL-Model/actions/runs/44524764589), successful. Opta/PulseLive integration: [run 44524764627](https://github.com/uasir/CTA-FPL-Model/actions/runs/44524764627), successful.
- Representatives were recomputed from the appearance-positive training partition within each fold only. No validation minutes were used. The resulting pooled representatives were approximately 0, 13.7, 44.6, 74.6 and 93.6 minutes (fold-specific values differ).
- Pooled minutes-band expected-minutes MAE improved from 16.458952 (fixed midpoints) to 16.256615 (training-derived representatives), a 0.202337-minute reduction. It improved in all nine individual season folds (2017/18–2025/26), indicating a consistent but small gain rather than a single-fold artifact.
- Pooled RMSE moved from 26.604864 to 26.619652 (slightly worse). Multiclass log loss, Brier and accuracy are unchanged because representative values do not alter predicted class probabilities.
- The gain does not close the gap to simple last-gameweek persistence: 13.727782 MAE. The two-part regression remains 16.268261 MAE, so the training-derived band expectation narrowly beats that regression on MAE but is still far behind persistence. It is not a sufficiently strong operational minutes forecast.
- Expected-points performance remains unchanged by this representative-only change; the integrated minutes-band model remains behind the leading two-part and direct points candidates. No recommendation component uses this head.
- Decision: retain training-derived representatives as the better implementation of the experimental band head, but keep the entire head research-only. Do not promote it as the minutes forecaster or as a points-model replacement.
- CI and provider audits completed successfully. The research workflow again confirmed that the source data and player-level evaluation panel remain runner-local and are not uploaded.
- Next priority: stop tuning minutes-band representatives. Investigate points-first distributional prediction and improve forecast-time data realism, especially obtaining genuine deadline-time snapshots rather than relying solely on retrospective historical exports.


### Points-first six-band distribution evaluation — 19 November 2026

- Implementation commit: `285860627fc0dd268ebb73c49bb61a201d30c130`; tests commit: `26ef7eb29f191ed02bf493f5a720592e3b37148e`.
- Full expanding-season research run: [GitHub Actions run 44527138101](https://github.com/uasir/CTA-FPL-Model/actions/runs/44527138101), successful. It completed all nine season folds (2017/18–2025/26) and scored 214,956 player-gameweeks. Engineering CI: [run 44527141997](https://github.com/uasir/CTA-FPL-Model/actions/runs/44527141997), successful.
- Added a six-class points distribution: negative points, exactly zero, 1–2, 3–5, 6–9, and 10+. The regularized multinomial model uses training-only median imputation, missingness indicators and scaling; temperature calibration is selected on a chronological slice of earlier training seasons. Expected points are reconstructed from probabilities and training-only within-band mean representatives.
- Pooled calibrated distribution results: expected-points MAE/RMSE 1.164028/2.148350; multiclass log loss 0.805062; multiclass Brier 0.396117; ranked probability score 0.308909; accuracy 0.712522. Raw distribution: MAE/RMSE 1.245266/2.150009; log loss 0.809397; Brier 0.394889; ranked probability score 0.308283. Training-class-prior expected-points MAE/RMSE were 1.684365/2.524954.
- Like-for-like expected-points comparison: calibrated six-band 1.164028 MAE / 2.148350 RMSE; raw two-part 1.160585 / 2.151055; calibrated two-part 1.160736 / 2.151449; direct Ridge 1.168723 / 2.147811; last-five baseline 1.190693 / 2.301198. The six-band head does not beat the best MAE model (raw two-part) or the best RMSE model (direct Ridge). It does improve on direct Ridge MAE and last-five baseline MAE, but not enough to justify replacing the current candidate.
- Temperature calibration materially improved the distribution model's expected-points MAE (raw 1.245266 to calibrated 1.164028) and log loss (0.809397 to 0.805062), while raw probabilities were marginally better on Brier and ranked probability score. This is a metric trade-off, not a universal calibration win.
- Cohort integrity was audited in `score_fold`: points probabilities, prior probabilities and actual labels are appended only after the same last-five-baseline availability check, so all compared metrics use the same validation cohort. No validation outcomes enter fitting, preprocessing, representatives or temperature selection.
- Important formulation limitation: the six classes form an unconditional full-outcome points distribution and include zero-point outcomes, but the zero class does not distinguish a player who did not appear from a player who appeared and scored zero. It therefore does not yet provide a separate appearance/conditional-points decomposition. A subsequent hurdle formulation should explicitly model (P(appearance)), then (P(points\ band\mid appearance)), with a played-zero class retained, and combine them into an unconditional distribution. Evaluate whether that structure improves proper scoring rules and expected-points MAE/RMSE.
- Decision: retain as a research candidate only; no model promotion, no recommendation integration, and CTA weight remains zero. All historical results still inherit the retrospective-source-vintage limitation and are not verified pre-deadline forecasts.
- Next experiment: implement the explicit appearance hurdle plus conditional points-band distribution, preserving the same expanding-season folds and validation cohort; compare against current raw/calibrated two-part expected points, direct Ridge, the six-band full-outcome model, and simple baselines. Report per-season metrics and pooled proper scoring rules before deciding whether to refine band boundaries or tail representation.
