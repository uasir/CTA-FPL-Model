# 2PM Defensive-Feature Experiment: 2025/26 Train, 2026/27 OOT

## Status

**DESIGN APPROVED — DATA AUDIT REQUIRED — TRAINING NOT AUTHORIZED**

This is an isolated research experiment. It does not change, replace, or admit features into the main four-season 286-feature experiment. The 2026/27 target labels are sealed until the experiment manifest, feature pipeline, preprocessing, model configuration, and evaluation code are frozen.

## Question

Do the 27 existing defensive-history features add out-of-time player-Gameweek expected-points forecasting value when trained on a season in which the four underlying defensive source fields are available?

## Source fields and feature groups

The pinned 286-feature schema contains 27 defensive-history columns derived from:

- `defensive_contribution`
- `clearances_blocks_interceptions` (CBIT)
- `recoveries`
- `tackles`

The 27 columns are the exact schema entries prefixed by `ar_defensive_contribution_`, `ar_cbit_`, `ar_recoveries_`, `ar_tackles_`, `ar_dc_hit_rate_`, `ar_dc_near_rate_`, `ar_dc_ppg_`, `ar_opp_dc_allowed_`, and `ar_opp_tackles_allowed_`. The experiment must derive and record the exact list from the pinned schema at runtime and assert its count is 27. No manually maintained substitute list.

## Temporal design

1. **Development/training season:** 2025/26 only.
2. **Validation:** a strictly chronological, season-internal 2025/26 split. Choose the cutoff only after auditing the available labelled player-Gameweek counts by GW. Earlier GWs train; later GWs validate. The cutoff and sample counts must be recorded before fitting.
3. **Held-out OOT:** completed 2026/27 Gameweeks only. Determine completion from the official fixture calendar and conservative completion-time rules. Do not inspect 2026/27 target points, score distributions, losses, or metrics during data preparation, feature selection, preprocessing, model selection, or hyperparameter tuning.
4. **No random row split.** All player-Gameweek rows from a GW remain in the same temporal partition.
5. **No training starts** until the source, identity, deadline, sample, and tensor-integrity gates below pass and the training authorization flag is explicitly changed in a reviewed commit.

## Matched comparison

Train two otherwise matched models on the same 2025/26 rows, labels, split, architecture, optimization budget, random seeds, and preprocessing policy:

- **Baseline:** the pinned 286-feature schema with the 27 defensive-history columns removed.
- **Enhanced:** the same schema and pipeline with all 27 defensive-history columns included.

The primary comparison is the incremental value of the defensive feature block, not a comparison between unrelated model runs. Report sample intersection and any exclusions. Fit imputers, scalers, feature transforms, and all learned preprocessing on the training partition only; apply unchanged to validation and OOT.

## Critical early-season history issue

Although the 2025/26 source has all four defensive fields, rolling windows for the earliest 2025/26 targets may reach into 2024/25, where the audited source columns are structurally absent. This must remain missing, never be rewritten as zero. Audit missingness by feature, GW, player, and history depth. Quantify the first GW at which each rolling window has a fully in-season history opportunity. Decide and document whether the fair comparison uses:
- all eligible 2025/26 samples with explicit missingness indicators and train-only imputation; or
- a predeclared common warm-up cutoff applied identically to baseline and enhanced arms.

Do not choose the policy by looking at 2026/27 outcomes. Do not drop rows selectively from only one arm.

## Implemented audit utilities

- `scripts/prepare_2pm_defensive_feature_arms.py` derives the exact 27 defensive columns from the pinned 286-feature schema and emits matched 259-feature baseline / 286-feature enhanced manifests. It fails closed if the schema or defensive count changes.
- `scripts/audit_2pm_defensive_warmup.py` reads only 2025/26 identity and defensive-feature columns from a candidate Parquet file. It reports missingness, zeros, nonzeros, first finite Gameweeks, and complete-block coverage by GW. It does not read target labels and does not choose a warm-up cutoff.
- `scripts/audit_2pm_2025_26_labelled_gw_coverage.py` reads only 2025/26 player-Gameweek metadata and target labels to validate finite integer labels and report sample counts by GW plus possible chronological cutoffs. It does not compute score distributions or select a cutoff. Its candidate cutoffs are descriptive; the final split remains a documented decision after reviewing the counts.
- Unit tests for these utilities are included in the defensive audit workflow. Passing unit tests do not substitute for running the source audit or inspecting the real candidate artifact.

## Required gates before training

### A. Source coverage and vintage
- Verify all four raw fields in 2025/26 and 2026/27 source files; report column presence separately from finite, missing, true-zero, and nonzero row counts.
- Record exact upstream repository commit, file path, file SHA-256, retrieval time, and any available publication/update timestamp.
- Distinguish source-column existence from evidence that the value was available by the relevant historical FPL deadline. A retrospective current file is not automatically a point-in-time archive.
- For 2026/27, establish which completed GWs have source records and labels without exposing labels to the development pipeline.

### B. Identity and target integrity
- Enforce unique player-fixture and player-Gameweek keys.
- Audit FPL player identity continuity and transfers across season boundaries.
- Preserve the existing player-Gameweek target grain, including double Gameweeks aggregated exactly once.
- Retain negative target points; do not clip labels.

### C. Point-in-time and history integrity
- Every rolling defensive input must use only matches completed and available strictly before the target deadline.
- Validate match-availability timestamps and source-vintage provenance. A kickoff + 24-hour conservative upper bound may be used only where justified and must be recorded as such.
- No target match statistics, post-deadline snapshots, or future opponent/team information may enter features.
- Audit the 2024/25-to-2025/26 boundary explicitly; structural absence is missing, not zero.

### D. Tensor and split integrity
- Assert chronological partitions by GW and no player-GW leakage across partitions.
- Assert all target labels are finite integer FPL points and sample keys unique.
- Preserve NaNs for fold-only preprocessing; fail on infinities and all-missing training-fold columns unless a documented policy handles them.
- Compare baseline and enhanced arms on an identical sample intersection.
- Produce checksums for source files, feature order, split manifest, tensors, and final config.

### E. Holdout protection
- Build 2026/27 feature tensors without loading or joining target labels into the training/selection process.
- Keep labels and OOT evaluation artifacts in a separately gated evaluation step.
- Freeze the code/config and record commit SHA before opening the OOT labels.
- Open the holdout once for final evaluation; any subsequent tuning using its results invalidates its status as an untouched OOT test.

## Scope boundary

This experiment produces player-level expected-points forecasts/distributions only. It must not implement squad selection, transfers, captaincy, ownership, effective ownership, variance/CoVar portfolio logic, or recommendations.

## Relationship to main experiment

The original four-season experiment remains unchanged:
- train: 2022/23 and 2023/24
- validation: 2024/25
- OOT: 2025/26
- original 286-feature candidate remains unadmitted pending its own feature-admission decision.

Do not rerun its expensive candidate rebuild as part of this experiment. Reuse already completed artifacts where appropriate, or build only a narrowly scoped 2025/26 + 2026/27 dataset on this branch.

## Current decision

- Separate branch created from `33f1133efd288b28d38211ed8124e6f1e4ca13da`.
- User approved the experiment design.
- Data audit and pipeline implementation are pending.
- `training_authorized` remains `false`.
- No model training or OOT scoring is authorized by this document.
