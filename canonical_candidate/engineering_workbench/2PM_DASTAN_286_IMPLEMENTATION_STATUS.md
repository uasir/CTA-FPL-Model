# 2PM — Dastan 286 Implementation Status

**Updated:** 2026-11-23  
**Branch:** `feat/four-layer-2pm-transformer-evaluation`  
**State:** Implementation underway; candidate data not admitted; no model training

## Confirmed implementation direction

- Use the exact ordered 286-column Dastan input inventory as the candidate 2PM feature foundation.
- Preserve the paper's encoder-only Transformer and two-component Poisson-mixture forecasting objective.
- Build samples around five previous fixtures actually played, plus a target-fixture query token.
- Keep the 2PM scope to player FPL-point prediction. No transfer, squad, captaincy, ownership, EO, CoVar or recommendation logic is placed inside the forecaster.
- The 286-column schema remains a candidate contract until feature-level admission is complete.

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

The first full rebuild run is being executed separately. Its outcome must be read from the workflow before reporting candidate row coverage or feature-build success.

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

**Not yet complete:** this is the post-match state-vector reconstruction layer, not the final sequence tensor or training implementation. The downstream sequence builder still needs to consume these post-match vectors, enforce the agreed five-previous-played-match and 21-day rules, prevent unverified cross-season history, and emit one target Gameweek training sample rather than duplicate a full Gameweek label across DGW fixture rows. The current target-query inference path also still emits fixture-level queries; DGW training must aggregate fixture distributions against one player-Gameweek label.

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

For a Double Gameweek, the dataset now represents **one player-Gameweek sample with two fixture queries and one Gameweek label**. The training label grain must be supplied explicitly:
- `player_fixture`: sum the verified fixture-level points once to form the Gameweek total;
- `player_gameweek`: require the same Gameweek total on every fixture row and deduplicate it, never sum duplicates.

The builder preserves negative integer points. It does not clip or reclassify them. Inference mode emits the same grouped fixture-query structure with no realized target label.

The intended model call is to flatten the player-Gameweek and fixture axes, run the existing six-token encoder independently for each fixture query, reshape the per-fixture mixture outputs, then aggregate them to one Gameweek distribution before computing one player-Gameweek loss. This prevents training the same full-GW label twice for a Double Gameweek. The exact generalized-mixture likelihood and cross-fixture dependence treatment remain to be implemented and validated.

The focused workflow now includes the post-match state and grouped player-Gameweek sequence contracts. Its latest status has not yet been independently verified; no test-pass claim is made.


## 2026-11-23 continuation — preserve negative FPL points with a shifted mixture

The primary research candidate no longer clips negative player points to zero. A signed-score adaptation has been added to `two_component_poisson_transformer.py`:

- the model retains the two-component Poisson mixture and predicts a non-negative latent count;
- the observed FPL point value is represented as `count - support_shift`;
- fixture expected points are `p*lambda_1 + (1-p)*lambda_2 - support_shift`;
- the constant shift leaves the mixture variance unchanged;
- the likelihood uses `observed_points + support_shift`, and rejects labels below the configured support floor;
- the original `prepare_paper_targets` negative-to-zero transformation remains available only as a paper-faithful benchmark, not the primary signed-score path.

The support offset is not selected from validation or test data. The candidate policy chooses it from each training fold only: at least 20 points, or five points below the most negative training label if that requires a larger offset. Any validation/test label below the frozen floor fails closed and requires a new training-fold configuration; it is not clipped.

The fixture forecast adapter and player-Gameweek aggregator now carry the offset. Under the explicit independent-fixture assumption, a Gameweek with F fixtures has aggregate lower support `-F * support_shift`, a `2^F)-component Poisson mixture, and one signed Gameweek forecast.

A differentiable `independent_fixture_gameweek_negative_log_likelihood` now expands the fixture mixtures and computes one loss per player-Gameweek. This is the training-loss contract needed by the grouped DGW tensor format. The tests cover negative values, shifted moments/tails, training-only support selection, exact two-fixture mixture likelihood and gradients.

This is a clearly labelled distributional adaptation, not the paper's original non-negative Poisson target. It remains research-only until chronological out-of-sample calibration and predictive performance can be compared against (a) the paper-faithful clipped baseline and (b) alternative signed discrete distributions. The 20-point minimum is a provisional floor policy, not a claim that the theoretical FPL lower bound is exactly -20.
