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
- Next: evaluate the appearance, minutes, and points components over expanding-season walk-forward folds. Calibration must be fitted independently inside each fold using only earlier data. All results remain research-only because historical source vintages are not verified deadline-time snapshots; a single holdout is not enough for promotion.

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
