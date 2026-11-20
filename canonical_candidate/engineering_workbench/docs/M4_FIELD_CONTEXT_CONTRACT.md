# M4-T2 — Field-context contract v1.0.0

## Purpose

Bind an existing rank-stratified LiveFPL / CTA field-EO artifact to one frozen M3 pre-deadline decision. This is a provenance and compatibility contract, not a new EO estimator.

## Required snapshot envelope

- `snapshot_id`, `season`, `target_gameweek`
- exact `deadline_utc` and `captured_at_utc`, both timezone-aware
- `cohort`: named cohort and rank bounds where applicable
- `sample`: manager count, effective sample size and weighting method
- `coverage`: covered and explicitly missing FPL element IDs
- `source`: source URL and SHA-256 of the exact EO artifact

Each row must identify the same target Gameweek and a unique FPL element ID. EO measures and intervals must be present as numeric values or explicit nulls. Null is never converted to zero.

## Candidate binding

The frozen candidate must carry manager ID, season, target Gameweek, exact deadline, pre-deadline `as_of_utc`, original 15-player squad and frozen decision. For a transfer, the outgoing player must be owned and the incoming player must be identified. The post-decision squad must be covered by the field snapshot.

## Fail-closed rules

Reject:
- post-deadline field capture or decision timestamp;
- season, Gameweek or deadline mismatch;
- missing/invalid provenance hash, cohort or sample metadata;
- duplicate/missing player IDs or cross-Gameweek rows;
- missing candidate squad coverage;
- unsupported decision action or malformed transfer identity.

## Unit and model boundaries

- Expected points remain points.
- Effective ownership remains percentage points.
- These quantities are reported side by side and are never summed or blended.
- Missing EO stays null with provenance/coverage context.
- CoVar remains disabled; covariance artifacts remain research-only.
- Output is not release eligible and cannot alter the frozen M3 decision.

## Implementation

Validator: `scripts/m4_field_context_contract.py`

Tests: `tests/test_m4_field_context_contract.py`

The contract currently validates an in-memory snapshot envelope, row set and frozen candidate. It does not yet ingest the EO workflow artifact or generate candidate comparison reports; those are M4-T3.
