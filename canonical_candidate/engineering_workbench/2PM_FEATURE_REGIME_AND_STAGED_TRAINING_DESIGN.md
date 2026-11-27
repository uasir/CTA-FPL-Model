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

Do not assume the 27 regime-dependent features are the only missing values. Preserve a per-cell observed/missing indicator for all 286 features after source-vintage admission. A separate feature-regime availability mask identifies structural unavailability by season/source regime. The observed mask distinguishes a real zero from a missing value within an otherwise available feature family.

## 3. Fixed-width model input

Keep the ordered 286 value channels. For each token, construct:
1. 286 fold-preprocessed feature values;
2. 286 per-feature observation indicators;
3. a scoring-regime embedding/indicator.

The value and observation channels retain fixed order and are validated against the same schema hash. The model's input projection therefore expands from 286 to 572 numeric channels plus a separately encoded regime indicator (or an equivalently documented appended regime channel). Do not silently change the source schema or feature order.

The regime indicator is:
- `legacy_fpl_scoring`: historical scoring seasons before 2025/26;
- `defensive_contribution_scoring`: 2025/26 and later, subject to official rule verification.

Regime is a known season-level target-scoring policy, not a feature inferred from the target points. For a prediction in 2026/27, set the current defensive-contribution regime.

The feature-availability mask is derived from source/season provenance, not from whether a numeric value happens to be zero. The observation mask is generated before imputation. Fit imputation and scaling only on each training fold; apply those fitted transforms to validation/test data. The masks themselves are never imputed or scaled.

## 4. Staged training schedule

### Stage A — historical common-feature foundation

- Train on eligible historical samples from 2020/21–2024/25 after season/GW and feature-level source-vintage admission.
- Use the common features; mark defensive-regime-dependent channels structurally unavailable.
- Use the legacy scoring-regime indicator because those target labels were produced under the historical scoring rules.
- Fit all preprocessing, target-support decisions, and mixture-head initialization on the training partition only.
- Select architecture and hyperparameters using expanding chronological validation. Do not use 2026/27.

### Stage B — new-regime adaptation with historical replay

- Initialize from the selected Stage A checkpoint.
- Fine-tune using eligible 2025/26 samples with the defensive-contribution features and the new scoring-regime indicator.
- Mix in replay samples from eligible Stage A historical training data. Replay retains its legacy regime indicator and its structural-unavailability masks; it must not be relabelled as new-regime data.
- Use a documented, pre-registered replay ratio/sampling policy and report per-season/per-regime sample counts and loss contributions. Tune that ratio only inside chronological validation.
- Keep the same shared Transformer backbone and two-component Poisson output family. Do not create two unrelated models and average their predictions.
- Compare controlled alternatives (frozen vs partially trainable shared layers, learning-rate schedule, replay ratio) only within the historical validation protocol. Do not choose them using 2026/27 OOT results.

This stage lets the model learn the new scoring relationship while retaining historical football-performance information. Since 2025/26 is currently only one season under the new regime, report that limitation explicitly and avoid letting its smaller regime sample dominate merely through oversampling.

### Stage C — final fit and 2026/27 inference

After feature admission and historical validation:
- refit the selected staged procedure using all eligible historical samples through 2025/26;
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
6. Stage A initialization and Stage B checkpoint loading, replay sampling, and regime-preserving labels.
7. Deterministic replay sampling with recorded seed and per-season/per-regime sample counts.
8. Tests proving that old-regime replay examples remain tagged legacy and 2025/26 examples remain tagged defensive-contribution scoring.
9. OOT isolation: no 2026/27 labels, preprocessing statistics, early stopping, or model selection enter training.
10. A trainer dedicated to `PaperTwoComponentPoissonTransformer`; do not reuse the legacy categorical `evaluate_two_pm_transformer_walk_forward.py`.

## 7. Open decisions (not silently assumed)

- The Premier League's official FPL announcement states that defensive-contribution points were introduced for the 2025/26 season: defenders earn two points at 10 combined clearances, blocks, interceptions and tackles (CBIT); midfielders and forwards earn two points at 12 combined CBIT plus ball recoveries (CBIRT). This establishes the target-scoring regime boundary at the start of 2025/26. The source-field extraction semantics and historical source-vintage availability still require separate verification.
- Whether all 26 engineered features are truly unavailable before 2025/26 or whether some can be reconstructed consistently from an independent historical event source. Until proven, preserve the current structural-missingness classification.
- Exact replay ratio and whether any backbone layers should be frozen during early Stage B steps.
- Whether the regime indicator should be a learned embedding or a simple numeric/categorical channel; choose by chronological validation, not OOT.
- Final season eligibility after the six-season FPL and Understat source-vintage audits. The proposed schedule does not override those admission gates.

## 8. Current status

This is a proposed design only. It does not modify the existing candidate/tensor artifacts, does not admit any of the 286 features, does not settle the open decisions, and does not authorize model training. The current 286-feature candidate remains `NOT_ADMITTED`; 2026/27 remains sealed as the out-of-time evaluation season.

### 2.4 Provenance-aware feature masks (implemented as a candidate contract, 2026-11-27)

The tensor contract now carries two aligned feature-level arrays with the same shape as the feature tensor `[samples, fixtures, 6, 286]`:

1. `source_availability_state` (uint8): `0=UNAVAILABLE`, `1=AVAILABLE`, `2=UNKNOWN`. This is a three-state source-provenance classification, not a binary mask. UNKNOWN must never be silently promoted to AVAILABLE.
2. `observed_value_mask` (uint8): `1` only when the raw tensor cell is finite, is not a declared missing-snapshot sentinel, and is not structurally unavailable; otherwise `0`.

The explicit missing-snapshot sentinel features are `ar_ep_next`, `sig_status_risk`, `sig_chance_playing`, `sig_has_news`, `value`, `selected`, and `transfers_balance`. For these columns, `-1.0` means missing snapshot, not an observed numeric value. A genuine observed zero remains observed. Other NaNs remain missing and are preserved for later fold-only preprocessing.

The pinned source policy currently marks the 27 defensive-regime-dependent features structurally unavailable for 2020/21–2024/25 and available in the pinned 2025/26 source vintage. Their 2026/27 source state remains UNKNOWN until the live inference-source vintage is pinned and audited. The other 259 features remain UNKNOWN pending their own feature-level source-vintage review. This is intentionally conservative: a numeric value may be observed while its source vintage remains UNKNOWN, and UNKNOWN is not training admission.

New tensor shards save both arrays. The grouped-dataset integrity audit checks shape, legal state codes, binary observation values, non-finite/sentinel exclusion, structural-absence exclusion, and zero observations in padded fixture slots. Existing cached tensor shards can be augmented with these masks from their stored feature tensors and season metadata; this avoids repeating expensive acquisition and post-match reconstruction. Cache reuse still requires valid tensor, fixture-mask, label and metadata files.

These masks are a provenance/missingness contract only. They do not admit features, decide imputation, or authorize training. Fold-only preprocessing must use the observed mask, while unresolved source availability remains a separate feature-admission gate.
