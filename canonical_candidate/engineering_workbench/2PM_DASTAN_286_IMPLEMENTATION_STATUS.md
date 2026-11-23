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
- Rebuilds the candidate feature frame and pre-deadline `ep_next` / availability snapshot artifacts.
- Attaches the official FPL Gameweek deadline calendar.
- Writes the exact 286 ordered inputs, identity/source hashes, snapshot timestamps and explicit non-admission status.

The output is deliberately labelled `RETROSPECTIVE_SOURCE_VINTAGE_NOT_VERIFIED` and `UPSTREAM_PREFIX_ASSERTION_ONLY_NOT_FULL_FRAME_VERIFIED`. Dastan's upstream anchor/assertion does not independently prove all 286 values were available at the official deadline. In particular, opponent rolling features, direct ranks, and historical `value` / `selected` / `transfers_balance` still need independent reconstruction or timestamp evidence.

### 3. Five-previous-played-fixture sequence builder

`scripts/build_2pm_dastan_sequence_dataset.py`

- Requires five prior player-fixture rows with `minutes > 0`.
- Requires each prior match to have completed strictly before the target Gameweek deadline.
- Selects the five most recent eligible played fixtures by completion/kickoff order.
- Rejects samples with fewer than five prior played fixtures; it does not pad.
- Enforces the paper's 21-day maximum gap between consecutive observation kickoffs, including the target fixture.
- Produces six tokens: five historical Dastan feature snapshots and one target-fixture query snapshot.
- Keeps target points as a separate label, never as an input feature.
- Handles a Double Gameweek by reusing the same deadline-eligible history for both target fixtures; a match completed after the shared deadline cannot enter either target sequence.

The historical token is the Dastan 286-feature snapshot captured before that historical fixture's own deadline. The latest prior match's completed result is represented in the target token through its lagged Dastan history features. This is the current sequence adaptation; it is not the paper's original 116-feature raw-match representation.

The sequence builder requires an input frame carrying `match_completed_at` and `source_as_of_time`. The current corrected-identity candidate rebuild does not yet establish those fields at the required row-level granularity. The source-to-sequence handoff is therefore still open; do not feed the candidate artifact into the sequence builder by fabricating timestamps.

### 4. Focused CI

`.github/workflows/cta-2pm-dastan-sequence-contract.yml`

- Compiles both new scripts.
- Tests the 286-column schema, sequence construction, same-deadline Double Gameweek handling, no-padding rule, 21-day gap, non-finite feature rejection, post-deadline snapshot rejection, and corrected historical identity mapping.

The latest focused run at commit `8fe5d539d11cc5bdd700b23ce617509eb23145a7` completed successfully.

### 5. Candidate rebuild workflow

`.github/workflows/cta-2pm-dastan-286-candidate-rebuild.yml`

- Checks out the pinned Dastan source and rebuilds the six completed seasons (2020/21–2025/26).
- Keeps raw player-level source data and feature artifacts on the ephemeral runner; only aggregate candidate status is written to the workflow summary.
- Does not train the 2PM model or promote data.

The first full rebuild run is being executed separately. Its outcome must be read from the workflow before reporting candidate row coverage or feature-build success.

## Immediate engineering continuation

1. Complete and inspect the six-season corrected-identity candidate rebuild.
2. Add an independent fixture-completion-time adapter and a source-vintage manifest; do not infer or fabricate completion/capture timestamps.
3. Independently reconstruct all 286 feature families at each official Gameweek deadline, not just Dastan's selected prefix anchor.
4. Rebuild opponent rolling values, direct league ranks, team context, defensive-allowance and congestion features from only pre-deadline completed matches.
5. Replace historical market fields with deadline-verified snapshots or hold them out of the admitted schema.
6. Quantify defensive-feature coverage by season and preserve structural missingness.
7. Produce a sequence-ready frame with verified `match_completed_at` and `source_as_of_time`, then run the five-played-match builder on that frame.

## Guardrails

- No feature rows are promoted by this implementation status note.
- No 2PM training or forecast evaluation is authorized by these data-engineering changes.
- The model remains research-only, production weight 0, and `production_eligible=false`.
- M2 forecast evaluation and M4 recommendation-product evaluation remain deferred until the upcoming Gameweek's official scores are available.
- No PR merge is performed without explicit approval.
