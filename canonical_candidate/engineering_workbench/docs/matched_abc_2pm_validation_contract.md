# Matched ABC–2PM Validation Contract

Status: design contract for Milestone 2; not yet an executed comparison.
Branch: `feat/matched-abc-2pm-validation-contract`.

## Purpose

Compare the independent ABC model and standalone conventional-FPL 2PM model on the same historical player–Gameweek targets, chronological folds, and scoring population. Existing pooled reports are not directly comparable: ABC's Wyscout-linked study is a single-season, identity-restricted cohort, while the current 2PM study uses expanding-season folds and a broader population.

## Evaluation unit and join key

The canonical target grain is one player in one FPL Gameweek, including double Gameweeks:

`(season, fpl_element_id, gameweek)`

Both source panels are fixture-grain. Aggregate each panel to player–Gameweek before joining or scoring:

- ABC: sum `target_fpl_total_points` over eligible fixture rows.
- 2PM/FPL: sum `target_total_points` and `target_minutes` over fixture rows, using the same player and Gameweek key.
- Require one unambiguous aggregate per key.
- Require exact key-set equality after restricting the 2PM target rows to ABC's verified and conservative-cutoff eligible cohort.
- Require ABC and 2PM actual total points to agree for every joined key (floating-point tolerance no larger than 1e-9). Any mismatch, duplicate ambiguity, missing target, or unmatched eligible key is a hard failure, not a silent inner-join drop.

The ABC panel's `research_eligible_for_analysis` flag is the cohort gate. Do not infer eligibility from non-null features or identity alone.

## Common chronological folds

The first matched experiment is deliberately limited to the shared 2017/18 season. It must not be compared with the nine-fold, multi-season 2PM pooled report.

- Split only on whole FPL Gameweeks; never split a Gameweek by kickoff or fixture.
- Use the ABC walk-forward schedule: minimum 18 initial training Gameweeks; first test block begins at `max(18, floor(number_of_gameweeks / 2))`; subsequent test blocks are four consecutive Gameweeks (final block may be shorter).
- For every fold, publish exact train and test Gameweek lists and sorted player–Gameweek keys.
- Apply the same eligible player–Gameweek target keys to both model tracks for fitting and validation.
- For 2PM sequence construction, retain the full chronological FPL history needed to build lagged windows for eligible players; restrict supervised fit, calibration, and scored target rows to the common eligible cohort. No future Gameweek rows may enter a target's history window.
- Reserve the latest 20% of pre-test training Gameweeks as a calibration partition for both tracks. Neither model may fit its base estimator on those calibration targets. Any calibration map must be fitted only on this shared calibration partition and frozen before test scoring.
- If a fold cannot meet the minimum fit/calibration/test row requirements for either model, mark that fold unavailable for both; never report different fold populations as a paired comparison.

## Model tracks

Primary head-to-head:

1. `ABC_ONLY_ABC`: the independent A+B+C feature model, trained only on the shared fit cohort.
2. `STANDALONE_CONVENTIONAL_FPL_2PM_TRANSFORMER`: the existing 2PM architecture, with its feature set and training settings predeclared, trained on the same shared fit target rows.

Required reference and later ablation:

- `FPL_HISTORY_ONLY` is the common conventional-feature reference, evaluated on exactly the same fold keys.
- `FPL_PLUS_ABC` is a separate incremental-value ablation. Do not blend its result into the standalone ABC-versus-2PM winner decision.
- Keep the current position-aware 2PM feature-set comparison separate from the primary comparison unless position features are predeclared for both relevant tracks.

## Leakage and provenance gates

- Preserve the ABC conservative eligibility gate and its source hashes.
- Historical source-vintage integrity remains `NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES`; this experiment is research-only even if all structural checks pass.
- ABC's one-season Wyscout identity cohort is a restricted, potentially survivorship-biased population. State the population limitation in every report.
- Do not zero-fill unsupported provider features. Missingness handling must be fitted on each fold's fit rows only.
- No validation targets may influence feature selection, imputation, scaling, calibration, hyperparameter selection, or model choice.
- The 2PM sequence may use only lagged conventional FPL features. ABC provider features remain excluded from the standalone 2PM track.

## Required outputs and gates

Before scoring, emit a fold manifest with:
- source identifiers/hashes and season;
- eligible cohort size, unique player count, and Gameweek coverage;
- per-fold fit, calibration, and test Gameweeks;
- per-fold counts and sorted key hashes for each partition;
- exact joined-key and actual-points parity checks;
- explicit exclusion counts and reasons.

For every fold and pooled common cohort, report:
- MAE, RMSE, mean signed error, absolute-error P50/P90/P95, and large-error rates;
- calibration/bias diagnostics and appropriate uncertainty intervals;
- deadline-local player ranking quality (Spearman and top-K selection utility), computed within each Gameweek rather than on pooled raw points;
- fold-to-fold stability and paired differences on identical player–Gameweek keys.

The comparison is valid only if all structural parity gates pass. A model is not selected from MAE/RMSE alone; ranking usefulness, tail behaviour, calibration, stability, and uncertainty must also be reviewed. No production promotion is permitted from this retrospective one-season experiment.

## Implementation order

1. Build the shared player–Gameweek cohort and fail-closed parity report.
2. Generate the common fold manifest and verify key/target parity.
3. Adapt both evaluators to consume the same manifest and partitions.
4. Run fold-level paired evaluations and tests.
5. Publish the research report with limitations; retain the existing multi-season 2PM results as a separate evidence stream.


## Implemented gate: shared fold-manifest builder

The first implementation is `scripts/build_matched_abc_2pm_fold_manifest.py`.

It consumes the strict ABC player–Gameweek aggregation output and the pinned conventional FPL fixture panel. Before emitting folds it:

- excludes GW1 to match the current 2PM evaluator's existing target eligibility;
- rejects duplicate ABC player–Gameweek rows and duplicate FPL player-fixture rows;
- aggregates conventional FPL fixture targets to player–Gameweek, including DGWs;
- checks the exact fixture-ID set, summed actual points, and summed actual minutes against ABC for every eligible ABC key;
- checks that lagged conventional FPL features do not conflict across a player's DGW fixture rows;
- fails closed with hashed mismatch keys and no folds if any target or fixture parity check fails;
- records source-file SHA-256 hashes, common-cohort hash, and per-partition key hashes;
- creates expanding whole-Gameweek fit/calibration/test partitions with the latest 20% of pre-test training Gameweeks reserved for calibration;
- blocks a fold if fit/calibration/test counts are too small or a test key lacks the 2PM last-five baseline required by its existing evaluator.

The published manifest contains counts, Gameweek lists, and hashes rather than raw player IDs. A separate partition-key CSV is written to the workflow runner's temporary directory for the later model runners; it is not uploaded as an artifact. Its unit tests cover exact parity, target mismatch, missing fixture, DGW aggregation, inconsistent lagged features, ABC eligibility, and the test-only last-five baseline gate.

**Implementation status:** the shared matched-fold key reader now normalizes season labels, rejects duplicate/overlapping partitions, and refuses any manifest that is not in PASS_MATCHED_FOLD_MANIFEST state with every fold READY. Both evaluators now accept the private partition-key CSV plus the public manifest.

- 2PM selects exact fit/calibration/test player-GW rows from the conventional FPL panel, while retaining the full conventional panel as the sequence-history index. It checks every requested key exists and records the three partition hashes in each fold report.
- ABC selects fixture rows for the exact same player-GW partitions, fits only on fit fixtures, fits an affine calibration map on aggregated calibration player-GWs, and scores test player-GWs. It also evaluates the FPL-history-only reference on the same partitions.
- The workflow now invokes both matched evaluators after the manifest gate. Raw player-ID partition keys and prediction rows remain runner-local; only aggregate reports and hashes are eligible for upload.

**Validation boundary:** this code has not yet passed the full CI run or completed a matched evaluation. The first CI attempt was blocked by an existing ABC aggregation unit test expectation after a temporary schema change; that compatibility change has now been reverted. The same attempt also lacked the historical ABC panel because the preceding test failure skipped the conditional 11footy download/build chain. No matched scores are claimed until the corrected CI run builds the inputs, passes the manifest, and both evaluators finish successfully.
