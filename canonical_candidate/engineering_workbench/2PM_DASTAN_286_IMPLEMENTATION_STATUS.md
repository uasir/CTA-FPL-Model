# 2PM — Dastan 286 Implementation Status

**Updated:** 2026-11-27  
**Branch:** `feat/2pm-defensive-2025-26-train-2026-27-oot`  
**State:** Six-season grouped tensor dataset built and integrity-audited; candidate data not admitted; no model training

## Confirmed implementation direction

- Use the exact ordered 286-column Dastan input inventory as the candidate 2PM feature foundation.
- Preserve the paper's encoder-only Transformer and two-component Poisson-mixture forecasting objective.
- Build samples around five previous fixtures actually played, plus a target-fixture query token.
- Keep the 2PM scope to player FPL-point prediction. No transfer, squad, captaincy, ownership, EO, CoVar or recommendation logic is placed inside the forecaster.
- The 286-column schema remains a candidate contract until feature-level admission is complete.

## 286-feature post-match treatment register

`2PM_DASTAN_286_FEATURE_ADMISSION_REGISTER.md` now enumerates every one of the 286 schema columns in pinned order and assigns an explicit post-match treatment, admission state and feature-specific evidence gate.

The register distinguishes:
- player, own-team, opponent, rank and availability histories that must be reconstructed at each historical token's post-match cutoff;
- historical fixture context that remains a known pre-kickoff value (venue, rest/congestion);
- historical pre-deadline snapshots retained as stale context (ep_next, availability/news signals and market fields).

All 286 remain HOLD. This is a feature-by-feature implementation map, not admission evidence. In particular, market snapshot provenance/units/coverage, source-vintage verification, identity corrections, structural defensive-stat missingness and double-Gameweek/postponement row-level parity remain blocking gates. The 286 input contract is preserved without falsely treating every column as validated.

## Implemented repository components

### 1. Pinned feature schema

`config/2pm_dastan_286_schema.json`

- Copies the exact ordered feature list from `qazybekb/smartplayfpl-dastan@758db9247e8b3a9a870c991064f74d8339d61cd0/models/feature_cols.json`.
- Validates 286 unique columns.
- Labels the schema `CANDIDATE_NOT_FROZEN`; it does not imply feature admission.

### 2. Corrected-identity candidate reconstruction

`scripts/rebuild_2pm_dastan_286_candidate.py`

- Requires the exact pinned Dastan source checkout.
- Reuses Dastan's public-source acquisition and feature-construction code, not its predictor or weights. The documented residual-NaN-to-zero tensor preprocessing is applied only after raw candidate missingness is audited.
- Replaces the two known incorrect historical Understat assignments with the evidence-backed corrected mapping while preserving the historical player/Gameweek assignment intervals.
- Uses the Dastan operational mapping resolver only for an explicitly requested active season.
- Rebuilds the candidate feature frame and pre-deadline `ep_next`, availability and market snapshot artifacts.
- Replaces unvintaged historical price, ownership and transfer-balance values with `now_cost` unchanged in native FPL tenths-of-a-million units, `selected_by_percent` and `transfers_in_event - transfers_out_event` from snapshots accepted only when the target GW is `is_next`, the deadline matches, and capture is at least five minutes before the deadline.
- Independently rebuilds all 115 player rolling features, all 9 availability features and 26 defensive/player-history engineered features using only player fixtures available before each target deadline. The rolling semantics retain Dastan's all-fixture player windows; the separate sequence builder still requires five previous appearances.
- Rebuilds all 60 own-team rolling features, all 60 opponent rolling features and both direct league-rank fields per target deadline from Understat team-match history. Historical matches are admitted only when their conservative 24-hour post-kickoff availability bound is strictly before the deadline.
- Rebuilds six fixture-specific `ar_*` context features per target fixture: rest days, team congestion and opponent defensive-contribution/tackle allowance. These are recomputed after Dastan's player/Gameweek anchor so distinct fixtures in a Double Gameweek retain their own context.
- Applies the same five-minute safety buffer to the `ep_next` and availability snapshot artifacts; rows inside the buffer are removed and become the explicit `-1` missing-snapshot sentinel.
- Downloads the pinned season fixture calendars and attaches a conservative 24-hour post-kickoff availability upper bound for fixtures marked finished. This is explicitly not an exact finish timestamp and excludes borderline matches rather than guessing.
- Attaches the official FPL Gameweek deadline calendar.
- Writes the exact 286 ordered inputs, identity/source hashes, snapshot timestamps, feature cutoff, fixture-availability quality and explicit non-admission status.

The output is deliberately labelled `RETROSPECTIVE_SOURCE_VINTAGE_NOT_VERIFIED` and `INDEPENDENT_286_FEATURE_RECONSTRUCTION_NOT_SOURCE_VINTAGE_ADMITTED`. The pipeline now independently rebuilds the 115 player rolling features, 9 availability features, 26 defensive/player-history features, 60 own-team rolling features, 60 opponent rolling features, both direct ranks and all six fixture-specific context features. It also uses accepted pre-deadline `ep_next`, `sig_*` and market snapshots. A fail-closed contract checks the exact 286 schema-family counts and that all 286 columns have an explicit reconstruction path. This does not yet prove historical source vintages: match availability still uses a conservative 24-hour upper bound, and retrospective-field parity is diagnostic rather than proof of what was known at the historical deadline. The price feature now preserves native `now_cost` units unchanged; the parity audit is used to detect any remaining unit or vintage mismatch.

### 3. Five-previous-played-fixture sequence builder

`scripts/build_2pm_dastan_sequence_dataset.py`

- Requires five prior player-fixture rows with `minutes > 0`.
- Requires each prior match to have completed strictly before the target Gameweek deadline.
- Selects the five most recent eligible played fixtures by completion/kickoff order.
- Rejects samples with fewer than five prior played fixtures; it does not pad.
- Enforces the paper's 21-day maximum gap between consecutive observation kickoffs, including the target fixture.
- Produces six tokens: five historical Dastan feature snapshots and one target-fixture query snapshot.
- Keeps target points as a separate label, never as an input feature.
- Supports memory-bounded float32 tensor shards with aligned metadata CSVs, avoiding a single oversized wide DataFrame.
- Handles a Double Gameweek by reusing the same deadline-eligible history for both target fixtures; a match completed after the shared deadline cannot enter either target sequence.

The current candidate prototype uses each historical fixture's Dastan 286-feature pre-match snapshot. The latest prior match's completed result is represented in the target token through Dastan's lagged rolling history. This is a provisional, testable sequence implementation; it is not the recommended post-match state-vector proposal and is not frozen as the final sequence semantics.

The sequence builder requires `feature_cutoff_time` to equal the official deadline, an explicit `source_vintage_status`, and a per-fixture `match_available_at` plus its quality label. It accepts an observed completion timestamp or the conservative 24-hour upper bound. An optional `source_as_of_time`, when present, must be strictly pre-deadline. The corrected-identity candidate builder now emits the required structural fields, so candidate sequences can be built without inventing timestamps; they remain `NOT_ADMITTED` while the underlying 286-feature source-vintage audit is open.

### 4. Candidate structural audit

`scripts/audit_2pm_dastan_286_candidate.py`

- Checks the exact 286-column order, numeric/finite values, player-fixture key uniqueness and non-overlapping feature-family totals.
- Reports per-season finite coverage, `-1` sentinel counts, genuine zero counts, defensive-family value coverage, and pre-deadline `ep_next`, signal and market snapshot age/post-deadline counts.
- Enforces the exact 286 schema-family counts and a separate 286/286 reconstruction-path count before writing the candidate artifact.
- Reports player-history, fixture-context and deadline team-context reconstruction separately; these remain candidate values until source-vintage and value-parity checks are admitted.
- Checks same-player/Gameweek invariance for player/team/availability history and separately diagnoses fixture-context flattening in `opp_*`, opponent defensive allowance, rest, congestion and venue fields.
- Reports the independent reconstruction coverage for opponent rolling, direct ranks, market snapshots and fixture-specific context, while keeping source-vintage and value-parity admission open.

### 5. Focused CI

`.github/workflows/cta-2pm-dastan-sequence-contract.yml`

- Compiles all three new scripts.
- Tests the 286-column schema, player/team/opponent/fixture-context reconstruction, deadline exclusions, same-deadline Double Gameweek handling, no-padding rule, 21-day gap, non-finite feature rejection, post-deadline snapshot rejection, market unit parity, corrected historical identity mapping, candidate schema/coverage checks and feature-family count reconciliation.

The latest focused run at commit `3e7c66ac4a4d3f9a808f511ac37219d0b85bd94c` completed successfully. It includes the player-history and availability reconstruction tests, team/opponent rolling and rank tests, fixture-context deadline tests, market snapshot and unit-parity tests, exact 286-family coverage, and the sequence contract.

### 5A. Clean paper-governed Poisson-mixture model core

`scripts/two_component_poisson_transformer.py`

- New independent encoder-only Transformer; does not import the frozen categorical `TwoPMTransformer` or Dastan predictive model code.
- Uses the current six-token × 286-feature candidate input contract, with an explicit final target-query token.
- Emits the paper's mixture probability `p` and positive Poisson rates `lambda_1` / `lambda_2`.
- Computes analytic expected points, variance and standard deviation.
- Implements stable two-component Poisson-mixture NLL and 6+/8+/10+ style tail probabilities.
- Implements the paper's negative-target-to-zero transformation without mutating or discarding raw target values.
- Includes a deterministic training-target-only two-Poisson EM/MLE head-initialization candidate. The quantile seed/component ordering is documented as an adaptation; exact author initialization details remain unresolved.
- Requires `num_layers` explicitly. The paper's selected layer count is not clearly reported; no default is inferred from the branch name.
- The configuration marks paper-unspecified implementation choices and keeps training unauthorized.

The test-only two-layer instantiation is a shape/gradient smoke test, not a selected research configuration. The model has not been trained, evaluated or connected to M3.

### 5B. Player-level forecast record adapter

`scripts/two_pm_forecast_records.py`

- Serializes player-fixture analytic mixture parameters, expected points, variance/SD and 6+/8+/10+ probabilities; includes target fixture ID as well as player and Gameweek IDs.
- Requires player IDs, target Gameweeks, timezone-aware forecast-as-of and training-cutoff timestamps, feature-schema version and data snapshot hashes.
- Carries quality metadata and marks every record `production_eligible=false`.
- Contains no transfers, ownership/EO, CoVar, squad, XI, bench, captaincy or recommendation logic.

The adapter is a model-to-forecast-record boundary only. M3 integration remains pending the actual M3 contract review and model validation.

### 5C. Player-Gameweek aggregation helper

`scripts/two_pm_gameweek_aggregation.py`

- Converts one or more player-fixture mixture forecasts into a player-Gameweek distribution under an explicitly required independence assumption.
- Preserves the exact sum as a generalized `2^n`-component Poisson mixture (two components for one fixture, four for a Double Gameweek).
- Produces GW-level expected points, variance, standard deviation and 6+/8+/10+ probabilities.
- Keeps the fixture-level forecasts in the output and marks the result research-only.
- Focused tests passed for single-fixture and Double Gameweek cases.

Cross-fixture dependence is not modelled. This is a mathematically exact convolution only under independent fixture-score draws; it remains a provisional aggregation assumption and is not yet an approved M3 integration.

### 6. Active-season target query builder

`scripts/build_2pm_active_target_queries.py`

- Uses the pinned Dastan source builder with the checked-in current operational player/club mapping.
- Selects the official pre-deadline FPL snapshot only when it marks the requested Gameweek as `is_next`, matches the official deadline and falls within a five-minute-to-30-hour capture window.
- Builds one target-fixture query at a time, preserving fixture-specific opponent/home-away context for Double Gameweeks rather than flattening all target fixtures into one player/Gameweek row.
- Produces current-season historical player-fixture rows plus target-query rows, joins pre-deadline `ep_next`, availability signals and market fields, and marks all outputs `NOT_ADMITTED`.
- Refuses to build if any fixture in the requested Gameweek has already started. It does not use a post-deadline partial-Gameweek history to construct an ostensibly pre-deadline query.
- A focused CI contract tests player-fixture grain, mapping behavior, Double Gameweek context and deadline/start-time refusals.

This builder is implemented but has not yet been run against the live 2026/27 source snapshot. The six completed-season historical candidate and the current-season target query are separate artifacts; they must be joined deliberately for current inference sequences.

### 6B. Candidate tensor preparation

`scripts/prepare_2pm_candidate_tensors.py`

- Audits per-feature residual NaN counts before imputation.
- Rejects infinite feature values.
- Applies the pinned Dastan model preprocessing rule: residual NaN → 0.0.
- Preserves existing `-1.0` missing-snapshot sentinels and genuine zeros as distinct values.
- Builds memory-bounded float32 candidate shards without modifying the raw Parquet candidate.
- Its focused CI contract passed, including explicit checks that NaN becomes 0.0 and `-1.0` remains unchanged.

**Open downstream grain:** M3 consumes player-Gameweek forecasts, while the paper sequence is match-level. Double Gameweeks therefore create multiple fixture forecasts per player/GW. A separate, explicit GW aggregation contract is still required; the sum of independent two-component Poisson mixtures is not generally another two-component mixture. No silent averaging or fixture dropping is permitted.

### 6A. Current target-query tensor builder

`scripts/build_2pm_target_query_tensors.py`

- Combines the six-season historical candidate with the active-season candidate.
- Uses active `TARGET_QUERY` rows only as inference targets; historical played rows provide sequence context.
- Emits exactly five previous played-fixture tokens plus one target-query token, requiring five prior appearances and enforcing the 21-day maximum gap.
- Preserves Double Gameweek target fixtures as separate player-fixture inference examples.
- Applies the explicit residual-NaN-to-zero tensor preparation policy while preserving `-1` snapshot sentinels and reporting the raw missingness count.
- A focused CI contract passed for target-only emission and insufficient-history exclusion.

This builder is implemented but depends on both the six-season historical candidate and a successful active-season query build. No current-season inference tensors have yet been produced.

### 6. Candidate rebuild workflow

`.github/workflows/cta-2pm-dastan-286-candidate-rebuild.yml`

- Checks out the pinned Dastan source and rebuilds the six completed seasons (2020/21–2025/26).
- Runs the 286 structural audit, audits raw residual missingness, applies the documented residual-NaN-to-zero tensor preparation while preserving -1 sentinels, and builds five-played-match candidate tensor shards after reconstruction.
- Keeps raw player-level source data, candidate feature frames and tensor shards on the ephemeral runner; only aggregate candidate status is written to the workflow summary.
- Does not train the 2PM model or promote data.

The six-season candidate rebuild has now completed on this branch in Run 82 (workflow run `45896384255`, commit `f657055de8694b8b68fdfd4371d0a735007216aa`). The pinned raw-source cache was restored successfully; the candidate cache was absent, so the corrected-identity six-season reconstruction ran and completed in approximately 1 hour 52 minutes. The candidate frame and its structural/snapshot reports were saved to the candidate cache. The run then reached the grouped tensor build but hit the workflow's 120-minute job timeout before all seasons completed. Its 30-day artifact is `15159367608` (`2pm-six-season-tensor-candidate-run-82`); it contains partial Gameweek tensor shards and audit reports, not a complete grouped dataset. The workflow now has a 360-minute timeout and a resumable per-Gameweek tensor cache. Do not treat the candidate as admitted or the partial tensor artifact as complete.

## Immediate engineering continuation

1. Complete and inspect the six-season corrected-identity candidate rebuild.
2. Inspect the conservative fixture-availability calendar coverage and retain its explicit upper-bound quality; obtain exact finish/capture times only where an authoritative source provides them.
3. Complete feature-by-feature point-in-time admission across all 286 columns; the rebuilt team/opponent, direct-rank and fixture-context values still require source-vintage and parity checks.
4. Verify historical market snapshot coverage, field-unit parity and capture-vintage quality; exclude unresolved rows/features from admission rather than silently substituting retrospective values.
6. Quantify defensive-feature coverage by season and preserve structural missingness.
7. Run the active-season target query builder for an upcoming, not-yet-started 2026/27 Gameweek; join its current-season history and target queries to the six-season historical candidate before constructing current inference sequences. Keep candidate and admitted sequence artifacts separate.

## Guardrails

- No feature rows are promoted by this implementation status note.
- No 2PM training or forecast evaluation is authorized by these data-engineering changes.
- The model remains research-only, production weight 0, and `production_eligible=false`.
- M2 forecast evaluation and M4 recommendation-product evaluation remain deferred until the upcoming Gameweek's official scores are available.
- No PR merge is performed without explicit approval.


## 2026-11-23 decision update — post-match historical state is governing

The governing 2PM sequence choice is now **five post-match historical state vectors plus a strictly pre-deadline target query**. The earlier six-token pre-match-row implementation remains a reference prototype only; it is not the selected historical-token semantics.

A new candidate builder has been added:

- `scripts/build_2pm_postmatch_state_vectors.py`
- `tests/test_2pm_postmatch_state_vectors.py`

The builder reconstructs player rolling/availability/defensive history, own-team/opponent rolling features and league ranks at a common conservative post-match state timestamp. It uses:

`max(player match_available_at, kickoff_time + 24h) + 1ns`

This timestamp ensures the just-completed player and team match data are eligible under the existing strict-before-cutoff reconstruction functions. It does not claim that the data were available immediately at full time.

The builder deliberately preserves the completed fixture's pre-kickoff context (`ar_rest_days`, `ar_team_matches_14d`, venue) and the archived pre-kickoff market/projection/news snapshot fields (`value`, `selected`, `transfers_balance`, `ar_ep_next`, `sig_*`). It refreshes player/team rolling state, ranks and opponent defensive allowance after the match. The target query remains a separate, strictly pre-deadline object.

The new contract tests verify post-match timestamp anchoring, feature-family refresh, retention of pre-match contextual/snapshot values, and rejection of non-appearances, missing availability timestamps and duplicate player-fixture keys. The focused 2PM workflow now compiles and runs this new contract.

**Not yet complete:** this is the post-match state-vector reconstruction layer, not the final sequence tensor or training implementation. The initial post-match and grouped player-Gameweek builders now implement these contracts. They remain candidate implementations pending full historical-data execution, temporal/source admission and CI verification.

All vectors remain `NOT_ADMITTED`. Historical source-vintage/rights checks, 286-feature admission, row-level temporal validation, model training and M2/M4 evaluation gates remain unchanged.


## 2026-11-23 continuation — player-Gameweek sequence grouping

A second sequence layer has been added:

- `scripts/build_2pm_player_gameweek_sequence_tensors.py`
- `tests/test_2pm_player_gameweek_sequence_tensors.py`

It consumes the post-match state vectors for historical context and the original pre-deadline 286-feature rows for target fixture queries. It creates one sample per `(season, gameweek, fpl_code)`, with a separate six-token input for each target fixture:

- tensor shape: `[player_gameweek, target_fixture, 6, 286]`;
- each fixture query shares the same five eligible post-match history tokens;
- each target fixture retains its own opponent/home-away/deadline snapshot;
- the fixture mask distinguishes real target queries from padding;
- historical tokens are restricted to the same season and must have `postmatch_state_as_of_time < target deadline`;
- the 21-day gap rule is applied from the five historical match kickoffs to the first target fixture kickoff.

For a Double Gameweek, the dataset now represents **one player-Gameweek sample with two fixture queries and one Gameweek label**. The pinned Dastan source contract has now been checked directly at revision `758db9247e8b3a9a870c991064f74d8339d61cd0`: one row per player-fixture, with `target_points` defined as points scored in that fixture. The candidate builder stamps this metadata and the grouped builder infers `player_fixture` only from that verified declaration. Other providers still require an explicit grain:
- `player_fixture`: sum fixture-level points once to form the Gameweek total;
- `player_gameweek`: require the same Gameweek total on every fixture row and deduplicate it, never sum duplicates.

The builder preserves negative integer points. It does not clip or reclassify them. Inference mode emits the same grouped fixture-query structure with no realized target label.

The intended model call is to flatten the player-Gameweek and fixture axes, run the existing six-token encoder independently for each fixture query, reshape the per-fixture mixture outputs, then aggregate them to one Gameweek distribution before computing one player-Gameweek loss. This prevents training the same full-GW label twice for a Double Gameweek. The differentiable exact generalized-mixture likelihood is implemented. Cross-fixture independence is an explicit provisional assumption and still requires calibration/sensitivity testing.

The focused workflow now includes the post-match state and grouped player-Gameweek sequence contracts. Its latest status has not yet been independently verified; no test-pass claim is made.


## 2026-11-23 continuation — preserve negative FPL points with a shifted mixture

The primary research candidate no longer clips negative player points to zero. A signed-score adaptation has been added to `two_component_poisson_transformer.py`:

- the model retains the two-component Poisson mixture and predicts a non-negative latent count;
- the observed FPL point value is represented as `count - support_shift`;
- fixture expected points are `p*lambda_1 + (1-p)*lambda_2 - support_shift`;
- the constant shift leaves the mixture variance unchanged;
- the likelihood uses `observed_points + support_shift`, and rejects labels below the configured support floor;
- the original `prepare_paper_targets` negative-to-zero transformation remains available only as a paper-faithful benchmark, not the primary signed-score path.

The support offset is not selected from validation or test data. The candidate policy chooses it from each training fold only: at least 20 points, or five points below the most negative verified fixture-level training label if that requires a larger offset. If only repeated Gameweek labels exist, use the minimum 20-point offset and fail closed below its aggregate support. Any validation/test label below the frozen floor fails closed and requires a new training-fold configuration; it is not clipped.

The fixture forecast adapter and player-Gameweek aggregator now carry the offset. Under the explicit independent-fixture assumption, a Gameweek with F fixtures has aggregate lower support `-F * support_shift`, a `2^F)-component Poisson mixture, and one signed Gameweek forecast.

A differentiable `independent_fixture_gameweek_negative_log_likelihood` now expands the fixture mixtures and computes one loss per player-Gameweek. This is the training-loss contract needed by the grouped DGW tensor format. The tests cover negative values, shifted moments/tails, training-only support selection, exact two-fixture mixture likelihood and gradients.

This is a clearly labelled distributional adaptation, not the paper's original non-negative Poisson target. It remains research-only until chronological out-of-sample calibration and predictive performance can be compared against (a) the paper-faithful clipped baseline and (b) alternative signed discrete distributions. The 20-point minimum is a provisional floor policy, not a claim that the theoretical FPL lower bound is exactly -20.


The grouped historical target builder also retains **non-appearance target fixtures** (normally zero FPL points). The five history tokens must be actual appearances, but the target outcome is not filtered by minutes. This keeps the model's target population aligned with player-point forecasting and avoids confusing a DNP zero with an appearance that earned negative points. Negative played-match points remain unchanged.

For auditability, historical shards retain both the single player-Gameweek target and the underlying fixture-level labels when the verified target grain is `player_fixture`. The pinned Dastan candidate now stamps this metadata, so the grouped builder can infer it safely; other sources must declare their grain. This is useful for support-floor selection from training-fold fixture outcomes; repeated player-Gameweek labels are never misrepresented as fixture-level scores.


The post-match builder uses corrected stable Understat player identity history across seasons where a verified mapping exists, matching the Dastan 286 player/defensive rolling-feature semantics. The five sequence-token fixtures themselves remain restricted to the target season. Team/rank and availability feature histories retain their source-defined season scope. This separates cross-season rolling context from cross-season sequence-token selection.


A model-side batch adapter, `forward_player_gameweek_batch`, now accepts the grouped tensor shape `[B, F, 6, 286]`, flattens the player-Gameweek/fixture axes for the Transformer, reshapes the per-fixture mixture outputs, sums fixture expected points and variances under the declared independence assumption, and returns one exact aggregate NLL per player-Gameweek when labels are supplied. This connects the grouped dataset to the model without introducing fixture-grain duplicate training labels.


The post-match state builder now also fails closed if a played row's player-data availability exceeds the conservative kickoff + 24-hour team-data bound. This keeps the state timestamp from drifting far enough to admit a later-kickoff fixture under the same availability rule. The guard is a source-contract check, not a substitute for row-level validation of the archived availability metadata.


Target-query provenance validation was hardened in the grouped player-Gameweek builder. If a general `source_as_of_time` column is supplied, every row must have a valid timestamp strictly before the deadline. If individual ep_next, availability/news or market snapshot timestamps are supplied, malformed timestamps are rejected; missing timestamps are accepted only when the corresponding feature values are all the explicit `-1` missing-snapshot sentinels; present timestamps must meet the five-minute safety buffer. Exactly five minutes before deadline is accepted. Tests cover missing general capture time, unvintaged real market values, valid missing sentinels and the five-minute boundary.

The latest focused-test commit has no reported commit-status checks available through the repository connection. These tests have been added to the existing focused workflow, but execution remains unverified.


## 2026-11-26 decision update — all historical seasons for independent 2PM

The governing 2PM decision is to use the extended Dastan dataset as the input foundation and adapt it to the 2PM Transformer independently. The model is not designed to reproduce, compare with, or inherit feature policy from XGBoost. All six eligible historical seasons in the verified Dastan foundation (2020/21–2025/26) are included in the candidate training pool; 2020/21 and 2021/22 are no longer reserved generalisation seasons. Use expanding chronological walk-forward validation within those historical seasons, then refit the selected configuration on all eligible 2020/21–2025/26 training samples. Keep 2026/27 sealed as the out-of-time evaluation season. This decision does not authorize training: feature admission, point-in-time/source-vintage checks, sequence integrity, target integrity, and fold-only preprocessing must pass first. The current sequence tensor builder remains season-scoped for its five historical tokens; cross-season token continuity is not silently enabled by expanding the training pool.



### Independent Poisson-mixture training path audit (2026-11-26)

The independent core at `scripts/two_component_poisson_transformer.py` implements the encoder, shifted two-component Poisson-mixture output, analytic moments, mixture likelihood, training-fold-only initialization helper, and grouped player-Gameweek forward/loss adapter. It is **not yet a complete trainable pipeline**: there is no dedicated chronological trainer for this model that loads the grouped 286-feature tensors, creates the expanding six-season folds, fits fold-only preprocessing/support shifts, early-stops on the validation partition, writes fold predictions/checkpoints, and finally refits on all six seasons.

Do not reuse `scripts/evaluate_two_pm_transformer_walk_forward.py` for this purpose. That script explicitly evaluates the older `STANDALONE_CONVENTIONAL_FPL_2PM_TRANSFORMER`: a categorical minutes/conditional-points model with conventional lagged FPL inputs, one-layer small-width settings, and retrospective source-vintage limitations. It is a separate legacy research track, not the independent Poisson-mixture 2PM forecaster now being developed. Its results and workflow must not be treated as 2PM Poisson-mixture training or validation.

The next modelling implementation task, after the six-season data and tensor audits, is a new trainer/evaluator dedicated to `PaperTwoComponentPoissonTransformer`, with all preprocessing and support-floor decisions fitted independently inside each chronological training fold. Model training remains unauthorized until the data admission gates pass.

### Six-season source-registry verification (2026-11-26)

The pinned Dastan source commit `758db9247e8b3a9a870c991064f74d8339d61cd0` declares all six historical seasons as completed and release seasons in `data/season_registry.json`. Its registry reports 163,072 expected release rows across the six seasons and 380 fixtures in each season (2022/23 has 37 Gameweeks but still 380 fixtures). Per-season declared rows are: 2020/21 24,365; 2021/22 25,447; 2022/23 26,505; 2023/24 29,725; 2024/25 27,283; 2025/26 29,747. The pinned Vaastav and fplcache commits are recorded in `data/source_pins.json` (`8c97b2adb123863c3dd581e730f1360e89815ac2` and `6c364bfbd9914649dc5dec016e544be3ae4fe767`).

This verifies that the pinned source release declares the six-season scope and its expected row/fixture coverage. Run 82 has now independently rebuilt all 163,072 player-fixture rows across 2020/21–2025/26, matching the registry's per-season row counts. It does **not** establish feature admission or complete tensor integrity: the grouped tensor job timed out part-way through its Gameweek loop, and the candidate remains explicitly NOT_ADMITTED.

### Independent-branch CI verification (2026-11-26)

The previously branch-filtered contract workflows have been enabled for this independent development branch. The following GitHub Actions runs completed successfully:

- Poisson-mixture model contract: 8 tests passed (`45879306741`).
- Dastan 286 reconstruction and grouped sequence contract: 88 tests passed (`45879391367`).
- Candidate tensor-preparation contract: 2 tests passed (`45879395917`).
- Target-query tensor contract: 4 tests passed (`45879401719`).
- Active-season query and post-match inference contract: 7 tests passed (`45879406061`).

These are focused unit/contract checks only. They do not constitute the six-season rebuild, full dataset/tensor audit, feature admission, model training, or OOT evaluation.


### Six-season rebuild and audit findings (2026-11-27)

Run 82 (`45896384255`) checked out the SciPy-patched workflow commit `f657055de8694b8b68fdfd4371d0a735007216aa`. The pinned Dastan raw-source cache was restored. The six-season candidate cache was not present, so the workflow reconstructed the candidate from the cached raw sources, passed the reconstruction step, and saved the completed candidate cache. The candidate report confirms:

- 163,072 player-fixture rows across all six seasons, exactly matching the pinned season-registry row counts.
- 286 ordered features with the expected feature-order hash; all 286 feature families have an explicit reconstruction path.
- 4,700 player-fixture rows whose fixtures had already started by the official deadline were excluded as forecast targets, leaving 158,372 deadline-eligible player-fixture targets.
- No duplicate player-fixture keys.
- 66,640 mapped played-player Understat rows; 79.14% metric coverage across the mapped Understat metrics.
- Pre-deadline snapshot timestamp checks found zero post-deadline rows and zero rows inside the five-minute safety buffer.

The run's structural and parity diagnostics also expose unresolved admission gates:

- 78 candidate kickoff timestamps disagree with the pinned Vaastav fixture calendar; the calendar is the authority and these rows require reconciliation.
- The same-player/Gameweek anchor diagnostic found 2,793 groups with differences, confined to five `player_relevant_fpl_points_{1,3,5,10,38}` rolling columns among the 212 player/team/availability/non-fixture-history columns checked. Root cause and row-level parity must be resolved before admission.
- The retrospective market-value field `value` matched the accepted deadline snapshot exactly on 142,151 paired rows. The `selected` and `transfers_balance` fields did not: their distributions/scales differ substantially. They must not be normalized or admitted based on correlation alone; source semantics and units need resolution.
- The structural audit counted 10,442,140 non-finite values across 163,072 × 286 candidate cells. Missingness remains explicit; any imputation/scaling must be fitted inside each chronological training fold only.
- Defensive source fields are structurally absent in the pinned historical source for 2020/21–2024/25 and present in 2025/26. Missing values must not be recoded as observed zeros.
- Retrospective provider source-vintage validity, opponent/context value parity, direct-rank tie-break parity, and the fixture-specific feature semantics remain open.

The grouped tensor step began after the candidate cache was saved but the job reached its 120-minute timeout while processing the six-season Gameweek sequence. The uploaded artifact contains 105 per-Gameweek reports and 86 Gameweek directories with emitted tensor shards, progressing through 2022/23 GW30; it does not contain the final aggregate tensor report or integrity audit. The candidate rebuild itself succeeded; the tensor build was incomplete due to the workflow time limit, not a data exception.

To make the expensive work resumable, the branch now:
- reuses completed Gameweek tensor reports only when every declared tensor, fixture-mask, label and metadata shard exists and is non-empty;
- discards and rebuilds an incomplete Gameweek directory;
- restores/saves a versioned grouped-tensor cache with a run-specific cache key, preserving completed Gameweeks after an interrupted run;
- raises the job timeout to 360 minutes.

The resume logic and cache changes are implementation changes only. They do not admit the candidate or authorize training. The next rebuild should use the already saved six-season candidate cache and resume the grouped tensor build from the latest valid per-Gameweek checkpoint. After completion, run the full tensor integrity audit and separately resolve the admission findings above.


### Six-season grouped tensor completion (2026-11-27)

Run 83 (`45936066859`, commit `b229b2ee55a0ccf4cbe5e5c9a44accbf9bdd8313`) completed successfully using the saved six-season candidate cache and the resumable Gameweek tensor cache. The six-season candidate reconstruction step was skipped because the verified candidate cache was restored. The workflow completed the structural audit, snapshot safety sanitization, grouped tensor build, tensor integrity audit, artifact upload and cache save.

The uploaded artifact is `15170914605` (`2pm-six-season-tensor-candidate-run-83`, 112,413,996 bytes; 30-day retention). Its summary and tensor integrity report confirm:

- Candidate: 163,072 player-fixture rows; six seasons 2020/21–2025/26; 286 ordered features; feature-order SHA-256 `9360ada967a808c1a43444a596c9e043970b505fb48a73589c7a533fe3335c0d`.
- Grouped tensors: 40,872 unique player-Gameweek samples in 193 shards; 42,687 valid target fixture queries; six-token sequences with 286 features; 49,745 fixture slots.
- Per-season samples: 2020/21 6,698; 2021/22 6,158; 2022/23 5,832; 2023/24 7,069; 2024/25 7,871; 2025/26 7,244.
- Fixture-count distribution: 39,068 single-fixture samples, 1,793 double-fixture samples and 11 triple-fixture samples.
- Tensor integrity audit: **PASS**. It verified shard shapes, matching tensor/mask/metadata counts, unique player-Gameweek keys, fixture masks, strict historical/target timing, five history gaps no greater than 21 days, fixture-label aggregation, preservation of negative labels, and absence of infinite features/non-finite targets.
- There are 12,469,572 preserved NaN feature values (14.61% of all tensor feature values); these must remain un-imputed until fold-specific preprocessing is fitted.
- 341 negative target labels were preserved.
- The sequence builder considered 151,756 candidate player-Gameweek groups. It excluded 81,878 for insufficient prior appearances, 29,004 for a gap over 21 days, and 2 because post-match state was not available by deadline.

**Important:** tensor integrity PASS is not data admission. Both candidate and grouped tensor reports remain `NOT_ADMITTED`; `training_authorized=false`. The 40,872 samples are the output of the currently specified same-season five-appearance/21-day sequence policy, not a claim that every historical player-Gameweek is eligible.

The candidate-level admission blockers remain:

- 78 candidate kickoff timestamps disagree with the pinned Vaastav fixture calendar.
- 2,793 same-player/Gameweek groups differ in five rolling relevant-FPL-points columns; the underlying aggregation/anchor discrepancy needs a row-level root-cause analysis.
- Market `value` matches exactly across 142,151 paired rows. `selected` and `transfers_balance` remain semantically unresolved between retrospective fixture rows and deadline-anchored snapshots; high correlation is not proof of equivalence.
- Defensive source columns are structurally absent in 2020/21–2024/25 and present in 2025/26. This must remain structural missingness, not zero.
- Historical provider source-vintage, direct-rank tie-break, opponent/context parity and feature-level temporal admission remain open.
- The structural audit records 10,442,140 non-finite candidate cells. Missingness is preserved and preprocessing must be fitted within each chronological fold.

The grouped tensor artifact-integrity audit is complete. The next work is now **feature/data admission**, not another rebuild and not model training. Resolve each blocker with targeted source/code analysis and row-level tests; do not regenerate the historical foundation unless a specific corrected source or reconstruction rule requires it. After admission, implement the dedicated chronological trainer for `PaperTwoComponentPoissonTransformer`. The 2026/27 OOT season remains sealed.


### Venue-conditioned rolling-feature audit correction (2026-11-27)

The Run 83 same-player/Gameweek diagnostic reported 2,793 groups with differences in five columns: `player_relevant_fpl_points_{1,3,5,10,38}`. A source-level review of `rebuild_2pm_fixture_context.py` established that these are not ordinary player-history features expected to be constant across a Gameweek. They are **venue-conditioned rolling FPL-points features**: for each target fixture, the reconstruction selects the player's previous FPL points from matches at the same venue (home or away) as that target fixture, using only matches whose availability is strictly before the shared Gameweek deadline. Therefore, a home and away fixture for the same player in one Gameweek can legitimately have different values in these five columns.

The previous diagnostic incorrectly classified these five columns as deadline-invariant simply because they have the `player_` prefix. The 2,793 groups are consequently **not evidence of an anchor/reconstruction defect**. The candidate values are not being changed by the audit classification correction. The source review also found that the pinned Dastan release's `anchor_to_deadline()` broadcasts all `player_` columns across a player-Gameweek, including these venue-conditioned columns. The independent 2PM reconstruction intentionally does not copy that blanket broadcast for this feature family: each fixture query retains the rolling points from the target fixture's own venue. This is appropriate to the fixture-specific query token, while ordinary player-history columns remain deadline-anchored and invariant across the Gameweek. The new builder regression test exercises a same-deadline home/away pair and checks both venue-conditioned and ordinary rolling values. That test, together with the audit classification regression, passed in the Dastan 286 sequence-contract workflow (`45952310841`, job `140350746274`) and the repository CI test job (`45952310918`, job `140350746466`). Both workflows completed successfully on 2026-11-27.

The structural audit now:
- excludes `player_relevant_fpl_points_{1,3,5,10,38}` from the same-player/Gameweek invariant-history check;
- reports them separately in `venue_conditioned_player_history_check`, including the number of multi-fixture groups with differences and the affected columns;
- records their explicit same-venue rolling semantics in the report;
- adds a regression test proving that different home/away values are classified as venue-conditioned rather than as deadline-anchor violations.

This removes one previously reported admission blocker. The focused Dastan 286 sequence-contract workflow passed on 2026-11-27 (run `45952058128`, job `140350156609`): compilation and the full configured reconstruction-adapter/sequence test command both succeeded, including the new venue-conditioning regression test. The remaining independent feature/source-vintage admission checks still apply. This does **not** establish full point-in-time admission of these or other reconstructed features. No candidate values, tensors, or training authorization are changed by this audit-only correction.


### Market-field parity semantics review (2026-11-27)

The Run 83 market parity output must be interpreted by field semantics rather than treating all three numerical columns as directly comparable:

- `value`: the deadline snapshot uses FPL `now_cost` in tenths of £m, the same unit as the retrospective Vaastav `value` field. The 142,151 paired rows matched exactly. This is a positive unit/parity check, not by itself proof of complete snapshot coverage or source-vintage admission.
- `selected`: the 2PM candidate stores the pre-deadline FPL API `selected_by_percent` percentage in the existing schema column named `selected`. The retrospective Vaastav `selected` field is documented as a count of managers who own the player. These are different units; the scale mismatch is expected and the exact-match/correlation comparison is not a valid parity test. Keep the point-in-time percentage rather than substituting a retrospective count. The feature register now records this explicitly.
- `transfers_balance`: the 2PM candidate stores `transfers_in_event - transfers_out_event` from the accepted pre-deadline snapshot. The retrospective field is also defined as net transfers for the Gameweek, but its exact observation cutoff is not established by the available source documentation. A pre-deadline event-to-date value need not equal a retrospective Gameweek value. The reported difference is therefore a cutoff/parity diagnostic, not evidence that the point-in-time calculation is wrong. Keep the pre-deadline value and retain the feature on HOLD until historical coverage and retrospective timing are documented.

The FPL dataset data dictionary identifies retrospective `selected` as the number of managers owning a player and `transfers_balance` as net transfers (in minus out); the pre-deadline extractor explicitly reads `selected_by_percent`, `transfers_in_event` and `transfers_out_event` from the accepted snapshot. The feature admission register now captures these unit and cutoff distinctions. No candidate or tensor rebuild is required for this interpretation correction.

### Fixture kickoff discrepancy source review (2026-11-27)

The 78 Run 83 kickoff mismatches are counted at player-fixture-row grain, not necessarily 78 distinct fixtures. The pinned Dastan source's `build_canonical_matches()` reads player-fixture `kickoff_time` from Vaastav `gws/merged_gw.csv`. The 2PM availability adapter separately reads the pinned Vaastav `fixtures.csv` calendar, preserves the incoming timestamp for diagnostics, and then makes the fixture-calendar kickoff authoritative. Run 83's sample includes 2021/22 fixture 263, where the merged Gameweek row says 15:00 UTC and the fixture calendar says 15:30 UTC.

The adapter overwrites the candidate timestamp with the fixture-calendar timestamp before computing the completion bound and before player-history/fixture-context reconstruction. The same canonical kickoff is therefore used for target eligibility and post-match availability. This is a source-file disagreement within the same pinned Vaastav release, not evidence that 78 player rows were independently mis-timed. The canonical calendar rule is already enforced; the mismatch remains recorded as a source discrepancy, but is not treated as a separate blocker to the downstream feature calculations. No rebuild is needed unless a later audit shows that the pinned fixture calendar itself is incorrect.

These two reviews remove the earlier interpretation of the five venue-conditioned columns and market fields as straightforward parity failures. They do not admit any features or authorize training. The remaining admission work is focused on source-vintage and temporal validity for reconstructed player/team/opponent/rank features, defensive-stat coverage and semantics, plus complete evidence for the accepted snapshot feature families.


### Scope check for historical source-vintage audit (2026-11-27)

The existing `audit_2pm_point_in_time_source_vintages.py` is not a six-season, 286-feature admission audit. Its season probe explicitly supports only 2025/26 and 2026/27, and its source comparison reads only the four defensive-stat columns (`defensive_contribution`, `clearances_blocks_interceptions`, `recoveries`, `tackles`) plus fixture/player identity and minutes. Its output must not be cited as point-in-time proof for all historical FPL or Understat feature families.

A separate source-history check found GitHub commit histories for the six pinned Vaastav `data/{season}/gws/merged_gw.csv` paths, with 40, 39, 38, 38, 37 and 12 commits respectively for 2020/21 through 2025/26. This establishes that a deadline-specific FPL-file vintage audit is feasible in principle, but commit counts alone do not establish that every target deadline has an eligible prior commit or that the downloaded file contains all required rows. The next audit should select the latest file commit strictly before each official deadline (respecting the five-minute safety cutoff), cache each unique commit once, and compare only the FPL-origin feature inputs and their prior-match availability. It must keep Understat player/team metric vintages as a separate evidence problem; a pinned current Understat extract is not automatically a historical deadline snapshot.

No broad source download or six-season rebuild was started for this scope check. Candidate and tensor artifacts remain unchanged, all features remain HOLD, and training remains unauthorized.


### Archived FPL snapshot coverage boundary (2026-11-27)

The pinned Randdalf/fplcache archive used for the historical snapshot review is commit `6c364bfbd9914649dc5dec016e544be3ae4fe767`. Its Git tree contains 9,740 `cache/YYYY/M/D/HHMM.json.xz` snapshots; the earliest path is `cache/2021/10/1/0113.json.xz` and the latest is `cache/2026/8/8/1302.json.xz`.

Consequences for the six-season 2PM history:
- The archive cannot provide any 2020/21 pre-deadline bootstrap snapshots: that season ended before the archive's first capture.
- It cannot provide pre-deadline bootstrap snapshots for the opening portion of 2021/22 before 2021-10-01.
- Later 2021/22 through 2025/26 deadlines may be auditable only where an archived snapshot exists at least five minutes before the exact official deadline, names the target Gameweek as `is_next`, and reports the matching deadline.
- The archive's existence and date range do not prove coverage of every Gameweek after 2021-10-01. The deadline-by-deadline resolver must report missing, stale, mismatched and accepted snapshots separately.

This is a **source-availability limitation**, not permission to backfill missing historical values from final `merged_gw.csv` rows or season-end player data. For rows without a verified snapshot, `value`, ownership percentage, net transfers, `ar_ep_next` and the three `sig_*` features must remain missing/unsupported under the existing missingness contract; they must not be assigned retrospective values or interpreted as observed zero. The 142,173 accepted market snapshot rows in Run 83 are an aggregate count and do not by themselves establish which six-season Gameweeks or feature families are covered. A season/Gameweek coverage matrix is still required.

The 2020/21 deadline calendar also needs an independent source because this archive cannot supply the season probe used by the current `fplcache.season_deadlines()` implementation. Do not silently infer exact FPL deadlines from kickoff times. Until a defensible official deadline source is pinned for that season, the source-vintage audit must mark those deadlines unavailable rather than claim a pass.

No candidate/tensor values were changed. No source was substituted, no new data were acquired, all 286 feature admissions remain HOLD, and training remains unauthorized.


### Understat source-vintage review (2026-11-27)

A further source review confirms that the six-season Dastan acquisition is not uniformly backed by season-pinned Understat files:

- The pinned Vaastav tree at `8c97b2adb123863c3dd581e730f1360e89815ac2` contains 24 Understat source files for 2020/21, and substantial player/team Understat archives for 2021/22 through 2024/25.
- The same pinned tree contains **no** `data/2025-26/understat/` paths.
- At the pinned Dastan source commit, `dastan/rebuild/sources.py` explicitly calls the live `understatapi` client for missing player histories and missing team-season histories. A live player fallback supersedes a partial pinned CSV for that player; a live team fallback fills a missing team-season.
- The download manifest records the distinction between Vaastav-pinned files and live Understat fallbacks, but a manifest/hash of the current response proves which bytes were used, not that those bytes were the version available at each historical FPL deadline.

This means the 2025/26 Understat feature coverage in Run 83 cannot be described as a historical deadline-vintage archive on the evidence currently available. For 2020/21–2024/25, the presence of per-season Understat files and per-file commit histories makes a source-vintage reconstruction possible in principle, but the latest season-level file is not itself proof that every row/value was available before each target deadline. The live fallback can also contain retrospective corrections to older match records.

The current match-availability adapter assigns a conservative `kickoff_time + 24 hours` availability bound from the FPL fixture calendar. This is an explicit modelling assumption, not a recorded Understat publication timestamp. FPL match-stat availability and Understat metric availability must therefore be audited separately; a 24-hour bound cannot be treated as proof that Understat xG/xA/xGChain/shot/key-pass/team metrics had already been published.

Required next steps:
1. Build a per-season/per-deadline Understat vintage manifest from Vaastav file commit histories for 2020/21–2024/25, separately for player and team sources.
2. Determine which player histories are supplied by pinned Vaastav files versus live fallback in the Run 83 download manifest; do not let a live fallback silently replace a historical pinned version for admission purposes.
3. For 2025/26, retain the current Understat-derived features on HOLD unless a lawful, stable, timestamped historical source archive can be established. Otherwise evaluate an explicit missingness/feature-exclusion policy for this source family without altering the 286-column schema until the decision is reviewed.
4. Establish evidence for Understat publication/availability lag after each match. Until then, the FPL-derived 24-hour completion bound does not independently admit Understat fields.

No model input, candidate or tensor was modified. The finding adds a source-vintage admission requirement; it does not authorize replacing the six-season training pool, mask features by analogy with XGBoost, or start training.


### Defensive-regime feature-group reconciliation and manifest (2026-11-27)

The apparent defensive-feature count discrepancy has been resolved against the pinned 286-column schema, `rebuild_2pm_fixture_context.py`, and the feature admission register:

- The schema-level defensive-regime-dependent group contains **27 columns**: **23 player-history** columns (16 rolling source-stat columns, six hit/near-rate columns, and `ar_dc_ppg_5`) plus **four opponent-context** columns (`ar_opp_dc_allowed_{3,5,10}`, `ar_opp_tackles_allowed_5`).
- The implementation's **26 defensive/player-history** reconstruction count is those 23 player-history columns plus `ar_starts_{3,5,10}`. Starts are history features but are not specific to the defensive-contribution scoring regime.
- The implementation's **six fixture-context** count is `ar_rest_days`, `ar_team_matches_14d`, and the four opponent-context columns. The 26 player-history and six fixture-context reconstruction families are disjoint (32 columns total). The 27-column defensive-regime group cuts across them: 23 player-history columns and four fixture-context columns are regime-dependent.

Added `config/2pm_feature_group_manifest.json` (manifest version 1.0.0), which explicitly partitions the pinned schema into 259 common candidate features and 27 defensive-regime-dependent features. It separately records the 26-column defensive/player-history and six-column fixture-context reconstruction families, source-schema pins, and scoring-regime/source-availability notes. All feature groups remain `HOLD`; manifest membership is not feature admission.

Added `scripts/two_pm_feature_groups.py` to validate the manifest fail-closed against the exact 286-column schema, defensive inventory, group partition, order, and reconstruction-family accounting. Added focused tests for the partition, 27/26/6 count relationship, missing defensive columns, and schema-order drift; wired the test into the focused sequence-contract workflow. The workflow/check status for the latest commit has not yet been confirmed, so these tests must not yet be described as passing.

The official Premier League FPL rules announcement dated 19 July 2025 confirms that defensive-contribution scoring began in 2025/26: defenders earn two points at 10 combined clearances, blocks, interceptions and tackles (CBIT); midfielders and forwards earn two points at 12 combined CBIT plus ball recoveries (CBIRT). This verifies the target-scoring regime boundary. It does not by itself prove the historical point-in-time availability or exact extraction semantics of the four source fields.

No candidate or tensor rebuild was run. No features were admitted, no training was started, and 2026/27 remains sealed as the out-of-time evaluation season.



### Provenance-aware feature masks (2026-11-27)

Implemented the first mask contract for the independent 2PM tensors:

- `source_availability_state` is a three-state uint8 array: 0=UNAVAILABLE, 1=AVAILABLE, 2=UNKNOWN. UNKNOWN is deliberately not treated as AVAILABLE.
- `observed_value_mask` is a binary uint8 array. It excludes NaN/Inf, declared missing-snapshot sentinels, and structurally unavailable cells. Genuine observed zero remains observed.
- Explicit `-1.0` missing-snapshot sentinel columns are `ar_ep_next`, `sig_status_risk`, `sig_chance_playing`, `sig_has_news`, `value`, `selected`, and `transfers_balance`.
- The pinned defensive source policy marks the 27 defensive-regime-dependent features unavailable in 2020/21–2024/25 and available in 2025/26. The 2026/27 state remains UNKNOWN pending inference-source vintage validation. The other 259 features remain UNKNOWN pending feature-level source-vintage review.
- The sequence tensor builder emits both masks; the grouped integrity audit validates their shapes, values, missing-sentinel semantics, structural-absence behavior and padded slots. The observed mask is now required to consume pre-fill raw-source sidecars because Dastan zero-fills some player/team fields before rolling reconstruction.
- Focused unit and integration tests cover the three-state policy, observed zero vs NaN vs -1 sentinel, structural absence despite a finite numeric fill, tensor emission, and mask integrity.

The new workflow checks are still running/queued at the time of this status update; no test result is claimed here. The candidate remains NOT_ADMITTED, no training is authorized, and no existing six-season tensor artifact has yet been rewritten with the new masks.


### CI verification update (2026-11-27)

The full CTA FPL engineering CI completed successfully on commit `07843aae55e1363ea913c3bc8a18e927c59ba6d6` (workflow run `45959619546`): **569 passed, 4 skipped, 3 subtests passed**. This run validated the earlier finite-value mask implementation only; it predates the discovery that upstream zero-fill destroys some raw missingness. It is not evidence that the new pre-fill sidecar extension passes CI.

The focused 2PM sequence-contract workflow for the subsequent manifest evidence commit `3410a79f64825ceb0538d255187960d657dc6609` is queued behind the preceding run at the time of this update. Its result is not yet claimed.

No six-season candidate rebuild or tensor-artifact augmentation has been executed. The cached Run 83 artifact remains unchanged; the next approved candidate build can add the masks by augmenting cached tensor shards, without reacquiring or reconstructing the underlying features. Candidate admission remains NOT_ADMITTED and training remains unauthorized.


### Final mask-contract CI result (2026-11-27)

The focused **2PM Dastan 286 sequence-contract workflow passed** on commit `6da7c2a73f67e873eb8d7dbd89a9774dbde0c814` (run `45959674518`): **106 passed**. This validated the initial mask contract, before pre-fill sidecars were required; it does not validate the current sidecar implementation.

The full CTA FPL engineering CI also passed on `07843aae55e1363ea913c3bc8a18e927c59ba6d6` (run `45959619546`): **569 passed, 4 skipped, 3 subtests passed**.

The subsequent manifest-only commit `3410a79f64825ceb0538d255187960d657dc6609` adds exact pinned-source references for the seven missing-snapshot sentinel fields; it does not change executable behavior. No candidate rebuild, tensor augmentation, feature admission, or model training has been performed.


### Full 286-column feature-family inventory (2026-11-27)

The manifest now includes a feature-family and reconstruction-treatment inventory extracted from the admission register and checked against the pinned 286-column schema. All 286 feature names appear exactly once in each partition; every feature remains HOLD.

| Feature family | Columns |
|---|---:|
| Player rolling | 115 |
| Own-team rolling | 60 |
| Opponent rolling | 60 |
| Flat context | 6 |
| Availability history | 9 |
| Dastan engineered/context | 33 |
| Pre-deadline availability | 3 |
| **Total** | **286** |

The separate reconstruction-treatment partition also covers all 286 columns: 141 player-history rebuild, 60 own-team post-match rebuild, 64 opponent post-match rebuild, 1 fixture-context retained, 2 rank post-match rebuild, 7 historical pre-match snapshot retained, 9 availability-history rebuild, and 2 pre-match fixture-context retained.

These are two orthogonal inventories: semantic feature family and reconstruction treatment. Neither implies point-in-time source availability or admission. The feature-group validator now checks that both partitions cover the schema exactly once and that the register remains ALL_HOLD.


### Manifest 1.1.0 and final CI verification (2026-11-27)

The feature manifest is now version **1.1.0**. It contains:
- the 259/27 scoring-regime partition;
- the independent 26/6 reconstruction-family accounting;
- all 286 feature-family assignments and all 286 reconstruction-treatment assignments, each an exact non-overlapping partition;
- the seven explicit missing-snapshot sentinel columns and pinned source references;
- three-state, season/source-specific availability policy.

Final verification on commit `b99d9bcd2b5b703423ffbee15f5837631c7763cb`:
- **CTA FPL engineering CI** run `45959909648`: 571 passed, 4 skipped, 3 subtests passed.
- **2PM Dastan 286 sequence contract** run `45959909666`: 108 passed.

No six-season tensor rebuild or cached-artifact augmentation has been run. The existing Run 83 artifact is unchanged. The current code now rejects legacy candidate caches without all 286 pre-fill sidecars and rejects tensor shards without both provenance masks. A new candidate build must reconstruct sidecars from the pinned raw source data; source-download cache reuse remains possible. All 286 features remain HOLD; no training is authorized.


### Upstream zero-fill discovery and sidecar correction (2026-11-27)

Source inspection of pinned Dastan `features.py` found that numeric player/team fields are converted to numeric and `fillna(0.0)` before rolling feature output. A finite zero in the final 286 tensor therefore cannot, by itself, prove that the underlying source value was observed.

The first finite-value-only mask implementation is superseded. The production manifest now requires raw-source observation sidecars. Code changes in progress:
- Player-history reconstruction emits per-feature coverage sidecars before its FPL zero-fill semantics; Understat rolling masks use any-valid coverage because the custom 2PM calculation ignores missing Understat rows.
- Team/opponent reconstruction captures source presence before Dastan's `_prepare_team_matches` zero-fill and carries window completeness through the rolling features.
- Fixture-context reconstruction emits masks for schedule and opponent-defensive features.
- Candidate export requires all 286 sidecars; post-match states require and preserve them; the sequence tensor builder consumes them.
- Candidate-cache validation rejects a cached candidate without 286 valid sidecars unless an explicit candidate rebuild is approved. Tensor-cache validation rejects shards without both provenance masks.
- The previous tensor-only backfill path has been removed. Legacy tensors cannot safely recover erased raw missingness.

The pinned raw source-download cache remains eligible for reuse. The derived Run 83 candidate and tensor artifacts do not contain the sidecars and must be regenerated before training. The sidecar implementation and new tests have not yet completed CI; the earlier 569/108 and 571/108 results validate prior revisions only. No rebuild or training has been run.


### Pre-fill sidecar implementation CI passed (2026-11-27)

The production sidecar implementation and manifest 1.3.0 passed both CI workflows on commit `54d76e5dd3f02f2df95ed364553054e753e35ae2`:
- **CTA FPL engineering CI** run `45961116448`: 577 passed, 4 skipped, 3 subtests passed.
- **2PM Dastan 286 sequence contract** run `45961116358`: 114 passed.

These runs include tests for raw FPL zero-fill detection, Understat any-valid rolling coverage, team/opponent source coverage before zero-fill, fixture-context sidecars, candidate/post-match sidecar requirements, sequence tensor consumption, production-manifest fail-closed behavior, and legacy cache rejection.

This closes the code-level sidecar contract. It does not validate the unmodified Run 83 artifact: no candidate rebuild or tensor regeneration has been run. The old candidate cache must be regenerated to include 286 sidecars, and old tensor shards without masks must be rebuilt from the sidecar-bearing states. The pinned raw source-download cache remains reusable. All 286 features remain HOLD; no training is authorized.


### Parity-checked cached-candidate migration (2026-11-27)

Added \`scripts/augment_2pm_candidate_observation_sidecars.py\`. The candidate workflow now attempts to migrate a restored candidate from its cached raw player/team match tables before considering a full rebuild:
- Verifies the checked-out Dastan repository/commit against the manifest.
- Verifies the candidate report's Vaastav and fplcache pins against the manifest.
- Verifies the raw \`downloads.json\` hash against the candidate report.
- Reconstructs all feature families and compares every one of the 286 candidate feature columns at \`rtol=1e-8\`, \`atol=1e-8\`.
- Appends only the 286 binary sidecars if the full feature-value parity check passes; the original feature values are preserved.
- If raw match tables are unavailable, source pins differ, or any feature value changes, migration fails closed and the workflow directs the operator to use \`rebuild_candidate=true\`.

Candidate cache keys now include the migration script, manifest validator and manifest. Grouped tensor cache keys include all source-sidecar reconstruction scripts and mask policy. This permits the Run 83 candidate to be migrated without repeating source acquisition if its cached raw tables and download manifest are intact; the old tensor shards still require regeneration because they do not contain the new masks. The migration has not yet been executed against Run 83.


### Manifest 1.3.0 and candidate-migration CI passed (2026-11-27)

Manifest 1.3.0 pins Dastan, Vaastav and fplcache separately; the Dastan pin is checked against the pinned feature schema, while the candidate migration verifies the candidate report's Vaastav/fplcache pins and exact raw `downloads.json` hash.

Latest CI on commit `e08b9aadce1be35ec76dce7f5d49a6967dd7f5b3`:
- **CTA FPL engineering CI** run `45962494382`: 582 passed, 4 skipped, 18 warnings, 3 subtests passed.
- **2PM Dastan 286 sequence contract** run `45962494399`: 119 passed.

This validates the candidate sidecar migration tests, source-pin checks, feature-value parity gate, sidecar builders, mask integration and legacy tensor cache rejection. It does not execute the migration against Run 83. The manual candidate workflow has not been dispatched; no candidate or tensor rebuild has occurred and no training has started.

The next data operation is to run the candidate workflow with its default `rebuild_candidate=false`: it will attempt parity-checked migration from the cached raw player/team match tables and source manifest, preserving the existing 286 feature values. If those files are absent or parity fails, rerun with `rebuild_candidate=true` for a full rebuild. The grouped tensor cache is version-invalidated and will be regenerated from sidecar-bearing states either way.


### Understat point-in-time findings and conservative mask (2026-11-27)

Pinned Vaastav tree inspection established:
- 2020/21 Understat player data in the season directory is an aggregate table without match dates; there are no individual player match-history files in that season directory.
- 2020/21 team files are match-level and have weekly file histories; they require a separate row-level commit audit.
- 2021/22 individual player files contain earlier seasons' rows and are updated weekly. Example Bruno Fernandes file first commit: 2021-08-24 20:21:52 UTC; the current file includes season values 2021, 2020, 2019, 2016, 2015 and 2014.
- Pinned Dastan selects the latest player file and only checks date coverage; it does not prove first-publication time. Live fallback is a current provider response, not a historical snapshot.

Added manifest 1.5.0 source-vintage HOLD for exactly 100 Understat-derived rolling features. The mask builder forces their observed-value mask to zero until a row-level vintage manifest is verified. A separate structural-availability profile marks the 20 player Understat columns UNAVAILABLE in 2020/21 and the 80 team Understat columns UNKNOWN until their independent audit. The sequence tensor builder converts every unobserved feature value to NaN before persistence; the grouped integrity audit rejects finite values marked unobserved. This avoids leaking current-file retrospective Understat rows while preserving the other historical feature families.

The Understat row-level audit plan is in 2PM_UNDERSTAT_POINT_IN_TIME_AUDIT_PLAN.md. It distinguishes 2020/21 player Understat unavailability from the separately auditable team files; it does not recommend discarding the whole 2020/21 season. No vintage audit manifest has been generated, no candidate/tensor rebuild has been run, and no training has started.


### Official FPL scoring regime contract (2026-11-27)

Feature-group manifest 1.6.0 now encodes and validates the target-scoring regime by season:
- 2020/21–2024/25: legacy scoring without defensive-contribution points.
- 2025/26 and 2026/27: defensive-contribution scoring.
- Defender: CBIT = clearances + blocks + interceptions + tackles; 10 in one match awards two points, capped at two.
- Midfielder/forward: CBIRT = CBIT + recoveries; 12 in one match awards two points, capped at two.

The Premier League's 10 August 2025 announcement establishes the new scoring and thresholds. Its 20 July 2026 explainer confirms the rules remain for 2026/27. This scoring-regime label is separate from raw feature availability: 2026/27 defensive source availability remains UNKNOWN pending its own point-in-time source audit. See 2PM_FEATURE_REGIME_AND_STAGED_TRAINING_DESIGN.md.


### Provenance-aware Transformer input contract (2026-11-27)

The independent PaperTwoComponentPoissonTransformer is now architecture version **0.3.0**. Its forward interface requires:
- 286 preprocessed feature-value channels;
- 286 binary observed-value indicators;
- 858 one-hot source-availability channels (three states per feature: UNAVAILABLE, AVAILABLE, UNKNOWN);
- one season-derived scoring-regime code per sample, represented by a learned embedding.

The numeric input projection is therefore 1,430 channels (5 × 286); the two scoring regimes use a separate embedding. The model rejects invalid masks/codes and rejects a feature marked observed when its source is structurally UNAVAILABLE. The season-to-regime helper maps 2020/21–2024/25 to legacy code 0 and 2025/26–2026/27 to defensive-contribution code 1.

This does **not** complete the training pipeline. Fold-only imputation/scaling, a dedicated expanding-season trainer/evaluator, validation, final refit, and a rebuild/migration of the six-season tensor artifact remain outstanding. The existing Run 83 tensors predate the source-vintage masking changes and do not contain the new mask contract. No training or candidate admission is authorized.


The grouped player-Gameweek forward adapter was also updated to flatten and pass the value, observed-mask, availability-state, and regime inputs together for each target-fixture query. Double-Gameweek aggregation and the single player-Gameweek likelihood remain unchanged.


### Fold-only preprocessing helper (2026-11-27)

Added \`two_pm_fold_preprocessing.py\` with training-partition-only feature medians and a separate frozen transform. It fails closed when a training fold has no observed value for a feature, rejects invalid observed masks/nonfinite observed values, and records its feature order and observed counts. For the grouped player-Gameweek tensor, shared five-match history tokens are counted once per player-Gameweek while every target-fixture query is retained; padded fixture slots are zeroed after transformation.

The helper is tested but is not yet called by a chronological trainer. Scaling remains unresolved and is not silently added. CI at the tested code revision: **599 passed, 4 skipped, 3 subtests passed** in the repository engineering suite; the focused 2PM sequence contract reported **130 passed** and the Poisson-mixture model contract **11 passed**. No training was run.


### Deterministic Stage B replay-plan helper (2026-11-27)

Added \`two_pm_staged_replay.py\`. It accepts only caller-supplied eligible training indices, requires the historical pool to be 2020/21–2024/25 with regime code 0 and the adaptation pool to be 2025/26 with regime code 1, samples the requested replay count with a recorded seed, and emits shuffled sample indices plus per-season/per-regime counts. It fails closed on overlapping pools, invalid seasons/regimes, and insufficient replay rows unless replacement is explicitly enabled.

The replay ratio remains **unselected**; no value was inferred or hard-coded. The helper is tested but not integrated into a trainer. Validation/OOT isolation still depends on the future trainer passing only the pre-registered training partitions. No training was run.


Stage B replay helper tests are included in the latest repository CI revision: **599 passed, 4 skipped, 3 subtests passed**. Focused contracts: **130 passed** (2PM sequence/feature contract) and **11 passed** (Poisson-mixture model contract). These are engineering tests only; no model training or candidate admission occurred.


### Run 85 source-vintage audit correction and Stage-A load safeguards (2026-11-27)

The completed six-season candidate rebuild is Run 85 (workflow run [45979402481](https://github.com/uasir/CTA-FPL-Model/actions/runs/45979402481)); its tensor integrity audit passes, but candidate admission remains NOT_ADMITTED and no model training has run. Inspection of the actual Run 85 tensor masks found that the manifest's previous 100-feature Understat HOLD did not cover 52 additional Understat-derived inputs: player xGChain/xGBuildup (10), team/opponent goals and rolling-rank context (40), and the two direct deadline ranks. The team context builder explicitly reconstructs those fields from Understat team-match histories. Those 52 fields were marked observed in the stored tensors despite unresolved source vintage.

Manifest 1.7.0 expands the Understat HOLD inventory to 152 features and updates structural-availability groups to 30 player-history and 122 team/opponent context fields. The Stage-A loader now reapplies current manifest HOLD policies and reconciles resolved structural availability states when reading existing tensor artifacts, so Run 85 can be reused without rebuilding. The remaining 107 Stage-A common features are still provisional; FPL-native historical source vintages and market-field semantics remain unresolved. Stage-A training remains paused. The follow-up engineering CI initially exposed stale tests that hard-coded the old 100-feature inventory; those contracts are being updated before the candidate is considered safe for research training.


### Understat mask correction verification (2026-11-27)

The expanded 152-feature Understat HOLD and load-time reconciliation are now covered by the shared mask helper and regression tests. The engineering CI run [46002094814](https://github.com/uasir/CTA-FPL-Model/actions/runs/46002094814) passed: **601 passed, 5 skipped, 18 warnings, 3 subtests passed**. The focused 2PM sequence contract [46002094856](https://github.com/uasir/CTA-FPL-Model/actions/runs/46002094856) passed: **132 passed, 18 warnings**. The optional PyTorch-specific Stage-A loader integration module remains skipped by general CI when PyTorch is not installed; its dedicated workflow has not been run. No Stage-A training was started.


### Exact feature-name and source-field contract audit (2026-11-27)

The prior 286-feature coverage gate checked family counts and column presence, but did not prove that each generating expression emitted the exact schema name or that every observation sidecar used the corresponding name. This has been tightened. The rebuild now derives the exact output-name inventory from the pinned Dastan `PLAYER_FEATURES` and `TEAM_FEATURES` maps, plus the explicit availability, defensive-history, direct-rank, fixture-context, market, expected-points and signal builders. It fails on duplicate output assignments, schema names without a builder, builder names outside the schema, missing `__observed__{feature}` columns, non-binary masks, and disagreements between builder-reported counts and the exact inventory.

A second 286-entry map records each output feature's raw source field or explicit calculation. Player/team source-field presence and defensive-source resolution are now reported by the rebuild. The audit also corrected its own signal-source descriptions: the actual FPL payload inputs are `elements[].status`, `elements[].chance_of_playing_next_round`, and `elements[].news`, transformed into `sig_status_risk`, `sig_chance_playing`, and `sig_has_news`. The candidate-generation path already used those correct `sig_*` output fields; the mismatch was in the newly authored audit description, not a discovered misassignment in Run 85's signal values.

Regression verification on the branch:
- Engineering CI [46005712197](https://github.com/uasir/CTA-FPL-Model/actions/runs/46005712197): **604 passed, 5 skipped, 18 warnings, 3 subtests passed**.
- 2PM sequence contract [46005712058](https://github.com/uasir/CTA-FPL-Model/actions/runs/46005712058): **132 passed, 18 warnings**.

These tests validate the exact name-generation contract against the pinned schema and test intentional name/mask mismatches. They do not constitute a new rebuild, source-vintage admission, or training authorization. Run 85 remains the existing candidate; no rebuild or training was started.
