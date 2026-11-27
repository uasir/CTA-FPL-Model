# 2PM feature-regime and scoring-regime training design

**Status:** Proposed engineering design; not frozen; no training authorization  
**Branch:** `feat/2pm-defensive-2025-26-train-2026-27-oot`  
**Scope:** Independent PaperTwoComponentPoissonTransformer using the existing 286-feature Dastan candidate foundation

## 1. Problem statement

The 2025/26 FPL season introduced defensive-contribution scoring and the candidate data has four defensive source fields that are structurally absent in the pinned historical source for 2020/21–2024/25 and present in 2025/26. The 286-column candidate schema also contains engineered defensive-contribution history and opponent-context features. Treating these absent historical values as observed zero would be incorrect; dropping all 2025/26 rows would discard the only season currently represented under the new scoring regime.

The design must distinguish:
- a feature not present in the source/regime;
- a feature present and observed as zero;
- an intermittently missing feature;
- a scoring regime that changes the mapping from football events to FPL points.

This design is independent of XGBoost and does not inherit its feature masks or modelling policy.

## 2. Feature groups

Keep the existing 286-column ordered feature contract as the raw candidate foundation. Define a reviewed, versioned feature-group manifest rather than infer groups from column-name prefixes at runtime.

### 2.1 Common candidate features

The common group is the 286-column schema minus the 27 defensive-regime-dependent engineered features listed below. A feature remains subject to its own source-vintage and temporal-admission gate; “common” does not mean “admitted”.

### 2.2 Defensive-regime-dependent engineered features (27)

- `ar_defensive_contribution_{3,5,10,38}`
- `ar_cbit_{3,5,10,38}`
- `ar_recoveries_{3,5,10,38}`
- `ar_tackles_{3,5,10,38}`
- `ar_dc_hit_rate_{3,5,10}`
- `ar_dc_near_rate_{3,5,10}`
- `ar_dc_ppg_5`
- `ar_opp_dc_allowed_{3,5,10}`
- `ar_opp_tackles_allowed_5`

The schema inventory contains 27 such columns. The implementation-status counts can now be reconciled from the reconstruction code and the 286-column register:

- **23 player-history columns** are scoring-regime-dependent: 16 rolling source-stat columns (four metrics × four windows), six hit/near-rate columns (two rates × three windows), and `ar_dc_ppg_5`.
- **Four opponent-context columns** are also scoring-regime-dependent: `ar_opp_dc_allowed_{3,5,10}` and `ar_opp_tackles_allowed_5`.
- The implementation status's **26 defensive/player-history engineered features** counts the 23 columns above plus the three `ar_starts_{3,5,10}` columns. Those starts-rate columns are player-history features, but they are not specific to the defensive-contribution scoring regime.
- The implementation status's **six fixture-context features** comprise two schedule features (`ar_rest_days`, `ar_team_matches_14d`) plus the four opponent-context columns above.

Therefore, the 27 schema-level defensive-regime-dependent columns are **23 player-history + four opponent-context**. The 26 player-history and six fixture-context reconstruction families are disjoint from each other (32 columns in total). The 27-column defensive-regime group cuts across those families: 23 of the 26 player-history columns and four of the six fixture-context columns are regime-dependent. The apparent discrepancy is resolved; retain all three counts with their definitions.

The four upstream FPL defensive source fields (`defensive_contribution`, `clearances_blocks_interceptions`, `recoveries`, `tackles`) are provenance/source fields, not additional columns in the current 286 input schema. Their mapping into engineered features must be documented and tested. Do not count them twice in the 286-feature group manifest.

### 2.3 Other structural and row-level missingness

Do not assume the 27 regime-dependent features are the only missing values. Preserve a per-cell observed/missing indicator for all 286 features after source-vintage admission. A separate three-state source-availability classification identifies verified structural absence (UNAVAILABLE), verified source presence (AVAILABLE), and unresolved provenance (UNKNOWN) by season/source vintage. UNKNOWN is not equivalent to AVAILABLE and cannot be silently promoted. The observed mask distinguishes a real zero from a missing value; it excludes both declared sentinels and structurally unavailable cells.

## 3. Fixed-width model input

Keep the ordered 286 value channels. For each token, construct:
1. 286 fold-preprocessed feature values;
2. 286 per-feature observation indicators;
3. three one-hot source-availability channels per feature (UNAVAILABLE, AVAILABLE, UNKNOWN; 858 channels total);
4. a scoring-regime embedding/indicator.

The value, observation and availability channels retain fixed feature order and are validated against the same schema hash. Under this explicit one-hot proposal, the numeric input projection expands from 286 to 1,430 channels (286 values + 286 observation indicators + 858 availability-state indicators), plus a separately encoded scoring-regime indicator. This is a proposed input encoding, not yet implemented or frozen. Do not silently change the source schema or feature order.

The regime indicator is:
- `legacy_fpl_scoring`: historical scoring seasons before 2025/26;
- `defensive_contribution_scoring`: 2025/26 and later, subject to official rule verification.

Regime is a known season-level target-scoring policy, not a feature inferred from the target points. For a prediction in 2026/27, set the current defensive-contribution regime.

The source-availability state is derived from source/season provenance, not from whether a numeric value happens to be zero. UNKNOWN features remain outside feature admission until their provenance is resolved. The observation mask is generated before imputation. Fit imputation and scaling only on each training fold; apply those fitted transforms to validation/test data. The masks themselves are never imputed or scaled.

## 4. Staged training schedule

### Stage A — historical common-feature foundation

- Train on eligible historical samples from 2020/21–2024/25 after season/GW and feature-level source-vintage admission.
- Use the common features; mark defensive-regime-dependent channels structurally unavailable.
- Use legacy scoring-regime code 0 because those target labels were produced under the historical scoring rules.
- Select architecture and hyperparameters with expanding-season walk-forward folds whose validation seasons are 2021/22, 2022/23, 2023/24 and 2024/25. Each fold trains only on earlier eligible seasons.
- After Stage A configuration selection, fit the Stage A initialization on all eligible 2020/21–2024/25 samples. This checkpoint is the starting point for Stage B adaptation.
- Fit all preprocessing, target-support decisions, and mixture-head initialization on each fold's training partition only. Do not use 2026/27.

### Stage B — new-regime adaptation with historical replay

- Initialize from the Stage A checkpoint fitted on eligible 2020/21–2024/25 data.
- Use a contiguous, chronological within-2025/26 split: earlier Gameweeks are the adaptation-training block and later Gameweeks are the validation block. The exact boundary must be selected and pre-registered after the 2025/26 labelled-Gameweek coverage audit, before inspecting validation scores. No random player-Gameweek split is permitted.
- Fine-tune using only the earlier 2025/26 adaptation block with defensive-contribution features and scoring-regime code 1.
- Mix in replay samples from eligible 2020/21–2024/25 Stage A training data. Replay retains its legacy regime code 0 and structural-unavailability masks; it must not be relabelled as new-regime data.
- Use a documented, pre-registered replay ratio/sampling policy and report per-season/per-regime sample counts and loss contributions. Tune that ratio only against the later 2025/26 chronological validation block.
- Keep the same shared Transformer backbone and two-component Poisson output family. Do not create two unrelated models and average their predictions.
- Compare controlled alternatives (frozen vs partially trainable shared layers, learning-rate schedule, replay ratio) only within the historical validation protocol. Do not choose them using 2026/27 OOT results.

This stage lets the model learn the new scoring relationship while retaining historical football-performance information. Since 2025/26 is currently only one season under the new regime, report that limitation explicitly and avoid letting its smaller regime sample dominate merely through oversampling.

### Stage C — final fit and 2026/27 inference

After feature admission and historical validation:
- refit Stage A on all eligible 2020/21–2024/25 samples, then refit Stage B using all eligible 2025/26 samples plus the pre-registered historical replay policy;
- retain season-specific scoring-regime labels and feature-observation masks;
- construct 2026/27 inference tokens with the expanded feature set and current scoring regime;
- keep 2026/27 labels sealed until the pre-registered OOT evaluation;
- report expected points, predictive variance, and calibration by scoring regime where the evaluation design permits.

## 5. Target semantics

The target remains the actual official FPL points for each player-fixture, aggregated once to player-Gameweek under the existing DGW contract. Do not retroactively add defensive points to pre-2025/26 targets, and do not subtract them from 2025/26. The regime indicator tells the model which scoring policy generated each target.

If historical event data is later used to create a counterfactual common-scoring target, that is a separate target definition and experiment. It must not silently replace official FPL points in this model.

## 6. Required implementation and test gates

Before training is authorized, implement and test:
1. A versioned 286-feature group manifest with exactly 27 defensive-regime-dependent engineered columns and no duplicate/missing names.
2. Structural feature-availability masks that are season/source-vintage driven and distinct from observed-value masks.
3. Tests proving that an observed zero has mask 1, a structurally unavailable historical value has availability mask 0, and a sporadic missing value is not converted into an observed zero.
4. Fixed-width tensor contract and schema/order/hash validation for values, observation masks, and regime identifiers.
5. Fold-only preprocessing; no validation or OOT fit leakage.
6. Stage A initialization and Stage B checkpoint loading, the pre-registered within-2025/26 chronological split, replay sampling, and regime-preserving labels.
7. Deterministic replay sampling with recorded seed and per-season/per-regime sample counts.
8. Tests proving that old-regime replay examples remain tagged legacy and 2025/26 examples remain tagged defensive-contribution scoring.
9. OOT isolation: no 2026/27 labels, preprocessing statistics, early stopping, or model selection enter training.
10. A trainer dedicated to `PaperTwoComponentPoissonTransformer`; do not reuse the legacy categorical `evaluate_two_pm_transformer_walk_forward.py`.

## 7. Open decisions (not silently assumed)

- The Premier League's official FPL announcement states that defensive-contribution points were introduced for the 2025/26 season: defenders earn two points at 10 combined clearances, blocks, interceptions and tackles (CBIT); midfielders and forwards earn two points at 12 combined CBIT plus ball recoveries (CBIRT). This establishes the target-scoring regime boundary at the start of 2025/26. The source-field extraction semantics and historical source-vintage availability still require separate verification.
- Whether any of the 27 defensive-regime-dependent engineered features can be reconstructed consistently from an independent historical event source. Until proven, preserve the current structural-missingness classification.
- Exact replay ratio and whether any backbone layers should be frozen during early Stage B steps.
- Exact 2025/26 Stage B adaptation/validation Gameweek boundary; select only after the labelled-Gameweek coverage audit and pre-register before evaluating validation performance.
- Final season eligibility after the six-season FPL and Understat source-vintage audits. The proposed schedule does not override those admission gates.

## 8. Current status

This remains a proposed training protocol; it does not modify the existing candidate/tensor artifacts, admit any of the 286 features, settle the remaining replay/split decisions, or authorize model training. The feature masks, scoring-regime contract, model input interface and fold-only imputer helper have been implemented and tested, but the dedicated chronological trainer and final tensor migration/rebuild remain outstanding. The current 286-feature candidate remains `NOT_ADMITTED`; 2026/27 remains sealed as the out-of-time evaluation season.

### 2.4 Provenance-aware feature masks (implemented as a candidate contract, 2026-11-27)

The tensor contract now carries two aligned feature-level arrays with the same shape as the feature tensor `[samples, fixtures, 6, 286]`:

1. `source_availability_state` (uint8): `0=UNAVAILABLE`, `1=AVAILABLE`, `2=UNKNOWN`. This is a three-state source-provenance classification, not a binary mask. UNKNOWN must never be silently promoted to AVAILABLE.
2. `observed_value_mask` (uint8): `1` only when the raw tensor cell is finite, is not a declared missing-snapshot sentinel, and is not structurally unavailable; otherwise `0`.

The explicit missing-snapshot sentinel features are `ar_ep_next`, `sig_status_risk`, `sig_chance_playing`, `sig_has_news`, `value`, `selected`, and `transfers_balance`. For these columns, `-1.0` means missing snapshot, not an observed numeric value. A genuine observed zero remains observed. Other NaNs remain missing and are preserved for later fold-only preprocessing.

The pinned source policy currently marks the 27 defensive-regime-dependent features structurally unavailable for 2020/21–2024/25 and available in the pinned 2025/26 source vintage. Their 2026/27 source state remains UNKNOWN until the live inference-source vintage is pinned and audited. The other 259 features remain UNKNOWN pending their own feature-level source-vintage review. This is intentionally conservative: a numeric value may be observed while its source vintage remains UNKNOWN, and UNKNOWN is not training admission.

New tensor shards save both arrays. The grouped-dataset integrity audit checks shape, legal state codes, binary observation values, non-finite/sentinel exclusion, structural-absence exclusion, and zero masks in padded fixture slots. The pinned Dastan builder zero-fills some raw player/team fields before producing rolling features; finite tensor values alone therefore cannot recover whether a zero was genuine. The observed-value mask must be derived from pre-fill source-observation sidecars. Legacy tensor shards without those sidecars are not safe to backfill and must be regenerated from candidate/post-match states carrying the sidecars. The raw source-download cache can still be reused; the candidate/tensor cache must be invalidated when the sidecar contract changes.

These masks are a provenance/missingness contract only. They do not admit features, decide imputation, or authorize training. Fold-only preprocessing must use the observed mask, while unresolved source availability remains a separate feature-admission gate.


### 2.5 Pre-fill observation provenance (required before training)

The pinned Dastan implementation (`qazybekb/smartplayfpl-dastan`, commit `758db9247e8b3a9a870c991064f74d8339d61cd0`) zero-fills numeric player and team source columns in `dastan/rebuild/features.py` before producing some rolling features. The 2PM pipeline therefore cannot infer observation from `isfinite(final_tensor_value)` alone.

The candidate now carries one `__observed__{feature}` uint8 sidecar for each of the 286 input columns. Sidecars are generated at the raw-source/reconstruction boundary:
- Player FPL rolling features: require every source value contributing to the rolling window to be present, because the existing value calculation retains zero-fill semantics.
- Player Understat rolling features: require at least one valid source value in the window, because the 2PM rolling reconstruction explicitly ignores missing Understat rows rather than treating them as zero.
- Defensive/rate rolling features: require at least one valid source value in the window; structural regime availability remains a separate three-state mask.
- Availability history: marks the documented position-prior fallback as an available engineered value when no history exists; otherwise requires the contributing minutes observations.
- Team/opponent rolling features: capture raw source presence before Dastan's team preparation zero-fill; require complete raw coverage across the contributing window.
- League ranks: require complete prior score/conceded/points inputs for the rank state; opponent rank also requires a resolved opponent.
- Fixture-context schedule features are deterministic from the fixture calendar; opponent defensive-allowance masks follow the finite reconstructed source values.
- Retained fixture and pre-deadline snapshot features use their source value/sentinel contract.

The sequence builder now requires these sidecars under the production manifest and combines them with finite-value, sentinel and structural-availability checks. Legacy Run 83 candidate/tensor artifacts do not contain the new pre-fill sidecars and cannot be safely repaired from final tensor values. They are rejected for reuse. The cached candidate can first be migrated from its saved `player_matches_with_availability.parquet` and `team_matches.parquet` using a parity-checked sidecar augmentation: all 286 feature values must match the existing candidate before sidecars are written. If those raw match tables are missing or parity fails, a full candidate rebuild is required. Grouped tensor shards must be rebuilt from the resulting sidecar-bearing states. The pinned raw download cache remains reusable.

This sidecar extension is under implementation and test; the earlier CI results above predate it. Do not train or admit features until the focused CI passes and the regenerated tensor artifact audit verifies the sidecars end to end.


### 2.6 Pre-fill sidecar implementation and verification

The 286 pre-fill sidecars are now emitted by player-history, team/opponent-context, fixture-context and retained snapshot reconstruction. The candidate builder fails closed unless all 286 are present. Post-match states validate and preserve them. The sequence builder requires them under manifest 1.3.0 and combines them with the tri-state availability, finite-value and sentinel checks.

Window policy is explicit: FPL rolling fields that retain zero-fill semantics require complete raw-source coverage across the contributing window; Understat rolling fields use any-valid coverage because the custom 2PM calculation ignores missing Understat rows; defensive/rate rolling fields use any-valid source coverage; team/opponent rolling fields require complete raw-source coverage; ranks require complete prior score/conceded/points inputs; deterministic schedule context is marked available; snapshots retain their sentinel contract.

CI now passes with this sidecar contract. This verifies code and tests, not the contents of the still-unrebuilt Run 83 artifact. Candidate/tensor regeneration and artifact-level mask audit remain outstanding before training.


The current production contract is manifest **1.3.0**. Its source pins distinguish the Dastan feature-schema repository from the upstream Vaastav and fplcache datasets. The candidate migration verifies all three against the cached candidate report and verifies the raw download-manifest hash before deriving sidecars. Code and focused CI are passing; the cached Run 83 candidate migration itself remains unexecuted.


### 2.7 Understat vintage HOLD is now enforced in the tensor path

Pinned-source inspection shows that current Understat player histories are selected from the latest season-path and may contain earlier-season rows; live fallback JSON can supersede partial pinned data. 2020/21 has only aggregate player totals (no match dates) in the pinned season directory, while its team files are match-level and have weekly commit histories. The detailed audit is recorded in 2PM_UNDERSTAT_POINT_IN_TIME_AUDIT_PLAN.md.

Manifest **1.4.0** adds an orthogonal source-vintage policy for exactly 100 Understat-derived player/team rolling columns. Until the row-level Git-commit vintage audit passes, the observed-value mask forces all 100 to zero. The sequence builder now writes NaN into every feature value whose observed-value mask is zero, so a finite retrospective value cannot leak into X while the audit is pending. The grouped tensor integrity audit now enforces this invariant.

This is an Understat-feature exclusion, not a season exclusion. 2020/21 FPL-native player features and separately audited team-context sources remain eligible for future admission; 2020/21 player Understat histories are not. No feature is admitted and no training is authorized.


## 2.8 Explicit scoring-regime contract (official boundary verified)

The feature manifest now carries a machine-validated scoring-regime contract, separate from source availability:

- **2020/21–2024/25:** legacy FPL target scoring without defensive-contribution points.
- **2025/26 onward:** defensive-contribution scoring; the same regime is confirmed to remain in force for 2026/27.
- **Defenders:** 10 combined clearances, blocks, interceptions and tackles (CBIT) in one match earns two FPL points, capped at two points per match.
- **Midfielders and forwards:** the same CBIT actions plus ball recoveries (CBIRT) require 12 total actions for two FPL points, also capped at two points per match.
- The \`defensive_contribution\` source field is recorded as the award/outcome field, not another action to add to the CBIT/CBIRT count.

The official Premier League announcement dated 10 August 2025 establishes the introduction and thresholds; its 20 July 2026 explainer explicitly says the rules remain for 2026/27 and confirms the same thresholds. Sources:
- https://www.premierleague.com/en/news/4373187
- https://www.premierleague.com/en/news/4361991/whats-new-in-202526-fantasy-defensive-contributions

**Important distinction:** knowing the scoring regime for 2026/27 does not prove that the 2026/27 feature source is point-in-time verified. The defensive feature-source availability state therefore remains UNKNOWN until its separate source-vintage audit passes. Do not use the scoring-regime code to promote feature availability.


### 2.9 Model-interface implementation status

Architecture version 0.3.0 now requires four aligned inputs: feature values, binary observed-value masks, three-state source-availability codes, and one scoring-regime code per sample. It concatenates the 286 values, 286 observation indicators, and 858 one-hot availability channels, then adds the learned scoring-regime embedding to each token before positional encoding.

The model rejects malformed masks, invalid availability/regime codes, and any feature marked observed while structurally UNAVAILABLE. The manifest helper maps the target season to the official scoring-regime code and fails closed for unmapped seasons.

This is an architecture/input-contract implementation only. It does not implement fold-only imputation, a chronological trainer, walk-forward validation, model selection, or final refit. The six-season tensor artifact predates the new source-vintage masks and scoring-regime input contract; it must be rebuilt or explicitly migrated only after the feature/source admission gates are settled. No training is authorized.


The grouped player-Gameweek forward adapter now carries the same masks and target-season scoring-regime code through its fixture-query flattening. It still aggregates fixture distributions to one player-Gameweek prediction and one likelihood; the independent-fixture assumption is unchanged.


### Fold-only imputation helper (implemented, not trainer-integrated)

The \`two_pm_fold_preprocessing.py\` helper now fits per-feature medians only from the supplied training partition and applies the frozen medians to later partitions. For \`[sample, fixture, sequence, feature]\` grouped tensors, it deduplicates the shared five historical tokens across target fixtures while retaining each target query. A feature with no observed training values causes a hard failure. This helper does not fit on validation/test/OOT data and does not introduce feature scaling.

CI at the tested code revision: repository suite 595 passed, 4 skipped, 3 subtests passed; 2PM sequence contract 130 passed; Poisson-mixture model contract 11 passed. The chronological trainer is still absent, so this helper is not yet integrated into a training run.
