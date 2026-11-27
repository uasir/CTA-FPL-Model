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
