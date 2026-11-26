# 2PM — Reuse the Extended Dastan Dataset Used by the XGBoost Baseline

**Decision date:** 2026-11-26  
**Status:** Governing data-source decision for the current 2PM experiment

## Decision

The existing extended Dastan football dataset used by the project's XGBoost points-model work is the data foundation for 2PM as well.

This is a model-architecture change, not a provider or data-foundation replacement.

- Retain the existing extended Dastan source data, statistics, identities, feature definitions, historical coverage and point-in-time construction.
- Do not procure Sportmonks or another provider for this experiment.
- Do not create a new statistics catalogue or rebuild the dataset from a different provider.
- Do not discard the extended feature set in favour of the paper's original 116-feature representation.
- The 286-feature Dastan contract remains the current candidate feature foundation, subject to the existing 2PM-specific semantic, temporal, leakage, missingness and sequence-compatibility checks.
- Preserve the existing 2PM experiment's agreed chronological training and out-of-time evaluation design unless a separate decision explicitly changes it.

## What changes

The XGBoost points-model architecture is replaced by the 2PM paper's encoder-only Transformer:
- player-match sequence encoder;
- two-component Poisson-mixture output (p, lambda_1, lambda_2);
- analytic mixture expectation and variance;
- mixture negative log-likelihood objective;
- paper-aligned chronological training and evaluation.

The 2PM model remains an independent player-points forecaster. It does not become a minutes model and does not inherit XGBoost or Dastan prediction heads.

## What does not change

The following are retained from the extended data foundation:
- the underlying acquired football/FPL source data and source pins;
- the expanded player, own-team and opponent statistics;
- player and team identity mappings, with existing audit requirements;
- fixture/player-match data and deadline snapshots;
- source-specific missing-value semantics;
- the existing feature definitions and feature ordering, subject to the 2PM admission audit;
- the point-in-time and no-leakage requirements.

The existing XGBoost model's learned weights and predictions are not inputs to 2PM. 2PM trains from observed FPL target labels using its own objective.

## Transformer input adaptation

Reusing the same data does not mean passing a flattened XGBoost matrix directly into a Transformer without checking sequence semantics.

The data adapter should construct the 2PM samples from the same canonical player-match and deadline-safe feature records. The intended paper-aligned representation is:
1. up to five previous played-match state tokens for the player;
2. one target-fixture query token containing only information available before the target deadline;
3. an explicit mask/padding policy for shorter histories;
4. strict chronological ordering and a maximum inter-observation gap consistent with the paper, with any adaptation documented.

Rolling features that are already deadline-anchored in the extended dataset must not be recomputed from target or future fixtures. In particular, all target fixtures in one Gameweek must use the same deadline-safe historical state where required; an earlier double-Gameweek fixture must not update a later fixture's target input.

The exact sequence-token schema and the mapping of flat features into historical-state versus target-query tokens remain subject to the existing 2PM sequence audit. This is a representation adaptation, not permission to change the underlying source statistics.

## Fair model comparison

For an architecture comparison, retain the same eligible player-fixture population, source vintages, feature information, chronological boundaries and observed FPL outcomes wherever the target definitions permit.

Record any unavoidable difference between the existing XGBoost target formulation and the 2PM paper's point-distribution target explicitly. Do not claim a pure architecture comparison if sample eligibility, target transformation, or evaluation periods differ.

Do not leak observed target points, target minutes or post-deadline values into input tokens. Target labels remain sealed until predictions are produced for the relevant evaluation partition.

## Existing provider-reset changes retracted

The temporary 2026-11-26 Sportmonks/provider-reset direction was based on a misunderstanding and has been removed. The Dastan 286-feature adaptation decision and admission register have been restored as active 2PM candidate documents. Their feature-level HOLD statuses still apply; restoring the data foundation does not mean every column is automatically admitted.

## Immediate implementation direction

1. Locate and reuse the existing extended Dastan-derived canonical data and/or the exact source-preparation artifacts already used by the XGBoost pipeline.
2. Identify the exact XGBoost training-frame artifact, source manifest, feature-order hash, row keys and feature-source mode.
3. Verify that the 2PM branch consumes the same source vintages and values; do not trigger another full source acquisition if valid artifacts already exist.
4. Adapt the existing canonical records into the 2PM sequence representation.
5. Preserve the 2PM model architecture, target protocol and out-of-time evaluation safeguards.
6. Compare data hashes, row coverage, feature values and temporal eligibility before training.

All expensive data work must remain resumable: restore and validate existing downloaded/derived artifacts first, checkpoint successful work, and fetch or rebuild only missing, corrupt, or version-mismatched items.


## Verified XGBoost artifact follow-up

The exact successful XGBoost training artifact has now been located and checksum-verified. Its 286-feature ordered list is identical to the 2PM candidate schema. The artifact is a reusable provenance/parity reference, but its final-snapshot historical values are not automatically admitted as point-in-time-safe 2PM inputs. The current defensive experiment remains 2025/26 train and sealed 2026/27 OOT; do not change that cohort or target definition. See [`2PM_XGBOOST_TRAINING_ARTIFACT_REUSE_AUDIT.md`](2PM_XGBOOST_TRAINING_ARTIFACT_REUSE_AUDIT.md) for the exact run, artifact, hashes, source pins, and remaining gates.
