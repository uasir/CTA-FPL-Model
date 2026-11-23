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
- Reuses Dastan's public-source acquisition and feature-construction code, not its predictor, weights or model preprocessing.
- Replaces the two known incorrect historical Understat assignments with the evidence-backed corrected mapping while preserving the historical player/Gameweek assignment intervals.
- Uses the Dastan operational mapping resolver only for an explicitly requested active season.
- Rebuilds the candidate feature frame and pre-deadline `ep_next`, availability and market snapshot artifacts.
- Replaces unvintaged historical price, ownership and transfer-balance values with `now_cost / 10`, `selected_by_percent` and `transfers_in_event - transfers_out_event` from snapshots accepted only when the target GW is `is_next`, the deadline matches, and capture is at least five minutes before the deadline.
- Applies the same five-minute safety buffer to the `ep_next` and availability snapshot artifacts; rows inside the buffer are removed and become the explicit `-1` missing-snapshot sentinel.
- Downloads the pinned season fixture calendars and attaches a conservative 24-hour post-kickoff availability upper bound for fixtures marked finished. This is explicitly not an exact finish timestamp and excludes borderline matches rather than guessing.
- Attaches the official FPL Gameweek deadline calendar.
- Writes the exact 286 ordered inputs, identity/source hashes, snapshot timestamps, feature cutoff, fixture-availability quality and explicit non-admission status.

The output is deliberately labelled `RETROSPECTIVE_SOURCE_VINTAGE_NOT_VERIFIED` and `UPSTREAM_PREFIX_ASSERTION_ONLY_NOT_FULL_FRAME_VERIFIED`. Dastan's upstream anchor/assertion does not independently prove all 286 values were available at the official deadline. In particular, opponent rolling features, direct ranks and fixture-specific `ar_opp_*` / rest / congestion context still need independent reconstruction. The historical `value`, `selected` and `transfers_balance` columns are now replaced by accepted pre-deadline fplcache snapshots; unit parity against the released Dastan values still needs checking.

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
- Checks same-player/Gameweek invariance for player/team/availability history and separately diagnoses fixture-context flattening in `opp_*`, opponent defensive allowance, rest, congestion and venue fields.
- Explicitly reports opponent rolling, direct rank, market timestamp and historical source-vintage limitations; it does not label them safe.

### 5. Focused CI

`.github/workflows/cta-2pm-dastan-sequence-contract.yml`

- Compiles all three new scripts.
- Tests the 286-column schema, sequence construction, same-deadline Double Gameweek handling, no-padding rule, 21-day gap, non-finite feature rejection, post-deadline snapshot rejection, corrected historical identity mapping, candidate schema/coverage checks and feature-family count reconciliation.

The focused run at commit `3efe8c56e16bd0f4a69b4959689e4d6e9f7820b5` completed successfully. It includes the pre-deadline market snapshot extractor and five-minute safety-buffer tests.

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
- Runs the 286 structural audit and builds five-played-match candidate tensor shards after reconstruction.
- Keeps raw player-level source data, candidate feature frames and tensor shards on the ephemeral runner; only aggregate candidate status is written to the workflow summary.
- Does not train the 2PM model or promote data.

The first full rebuild run is being executed separately. Its outcome must be read from the workflow before reporting candidate row coverage or feature-build success.

## Immediate engineering continuation

1. Complete and inspect the six-season corrected-identity candidate rebuild.
2. Inspect the conservative fixture-availability calendar coverage and retain its explicit upper-bound quality; obtain exact finish/capture times only where an authoritative source provides them.
3. Independently reconstruct all 286 feature families at each official Gameweek deadline, not just Dastan's selected prefix anchor.
4. Rebuild opponent rolling values, direct league ranks, team context, defensive-allowance and congestion features from only pre-deadline completed matches.
5. Verify historical market snapshot coverage, field-unit parity and capture-vintage quality; exclude unresolved rows/features from admission rather than silently substituting retrospective values.
6. Quantify defensive-feature coverage by season and preserve structural missingness.
7. Run the active-season target query builder for an upcoming, not-yet-started 2026/27 Gameweek; join its current-season history and target queries to the six-season historical candidate before constructing current inference sequences. Keep candidate and admitted sequence artifacts separate.

## Guardrails

- No feature rows are promoted by this implementation status note.
- No 2PM training or forecast evaluation is authorized by these data-engineering changes.
- The model remains research-only, production weight 0, and `production_eligible=false`.
- M2 forecast evaluation and M4 recommendation-product evaluation remain deferred until the upcoming Gameweek's official scores are available.
- No PR merge is performed without explicit approval.
