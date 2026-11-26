# 2PM — Verified XGBoost Training Artifact Reuse Audit

**Date:** 2026-11-26  
**Branch:** `feat/2pm-defensive-2025-26-train-2026-27-oot`  
**Status:** XGBoost source artifact located and integrity-checked; 2PM data admission and training remain blocked by the existing point-in-time and feature-admission gates.

## 1. Governing decision

The 2PM experiment reuses the extended Dastan-derived feature foundation already used by the CTA-owned XGBoost points model. This is an architecture change, not a provider change.

- Do not acquire a replacement provider or create a new statistics catalogue.
- Do not use XGBoost weights, predictions, or the XGBoost points-per-90 target as 2PM inputs or labels.
- Reuse the same 286 ordered feature definitions and source-data foundation, subject to 2PM-specific point-in-time, semantic, identity, missingness, and sequence validation.
- Train the independent 2PM model on **all eligible historical seasons** available in the extended Dastan dataset, currently 2020/21–2025/26. The previous 2025/26-only defensive candidate cohort is superseded.
- Use chronological validation within the historical training period. Keep 2026/27 separate as the sealed out-of-time evaluation season; its labels must not enter training, tuning, feature selection, or early stopping.
- 2026/27 OOT queries must be reconstructed from the corresponding pre-deadline source vintages. The XGBoost artifact's current GW12–16 forecast matrix is not the historical GW1+ OOT query set.

## 2. Exact XGBoost artifact located

Successful GitHub Actions run:

- Workflow: `CTA five-Gameweek forecast pipeline`
- Run ID: `45401621199`
- Run URL: https://github.com/uasir/CTA-FPL-Model/actions/runs/45401621199
- Source commit: `e44a72d06fbd88d6c94334533aadbce0c4281b26`
- Artifact name: `cta-five-gw-candidate-forecast`
- Artifact ID: `14925035251`
- Artifact size reported by GitHub: 77,663,604 bytes
- Artifact remains available and was downloaded and inspected on 2026-11-26.

The artifact contains the exact XGBoost training source:
`training/features_with_snapshots.parquet`

Verified SHA-256:
`f29ecc45a4fd2b024c5703b32e77a55fafdbc4b7401009f2699d4d0dbb353f1c`

The artifact also contains:
- `training/features.parquet`
- `training/release_manifest.json`
- `training/season_registry.json`
- `training/source_pins.json`
- `training/dastan_release_import_report.json`
- `training/mappings/*`
- `canonical_player_matches.parquet`
- `canonical_team_matches.parquet`
- `source_download_manifest.json`
- `source_preparation_report.json`
- `feature_matrix.csv`
- `feature_matrix_report.json`
- `models/cta_points_model_manifest.json`
- the four trained CTA-owned position-specific XGBoost model files.

The extracted training source hash matches the hash recorded in `models/cta_points_model_manifest.json`. The Dastan release's `training/features.parquet` hash also matches its release manifest.

## 3. Feature-contract identity verified

The XGBoost schema at main commit `125276aba945f97099c5dd7e9e9f8c4bc7910bd7` and the 2PM schema on this branch both declare 286 features.

A direct ordered-list comparison confirms:

- XGBoost feature count: 286
- 2PM candidate feature count: 286
- Ordered feature lists: **identical**
- XGBoost schema blob: `053f499332f7e6eab6e7046bf4f0e847e3b57d1f`
- 2PM schema blob: `a4ead4eb7238a936cc9061e062c64d0d7ae5849a`
- XGBoost model manifest feature-order SHA-256: `9360ada967a808c1a43444a596c9e043970b505fb48a73589c7a533fe3335c0d`

This verifies the 2PM candidate schema is not a new feature catalogue. It is the same ordered 286-feature contract used by the XGBoost candidate.

## 4. Source provenance and coverage recorded by the XGBoost run

The XGBoost artifact reports:

- Feature source mode: `FPL_PLAYER_UNDERSTAT`.
- Historical seasons in the Dastan release: 2020/21–2025/26.
- Dastan reconstruction commit: `758db9247e8b3a9a870c991064f74d8339d61cd0`.
- Historical Vaastav source pin in the Dastan release: `8c97b2adb123863c3dd581e730f1360e89815ac2`.
- Historical FPL-cache pin: `6c364bfbd9914649dc5dec016e544be3ae4fe767`.
- Canonical player-match rows in the current-source preparation report: 170,308.
- Canonical team-match rows: 4,780.
- Historical training rows: 163,072.
- Feature count: 286.
- Understat player metric coverage reported for `us_xG`, `us_xA`, `us_shots`, and `us_key_passes`: approximately 75.27% of appearance rows.
- Understat metrics are zero-filled only for verified FPL non-appearances; appearance/unknown rows remain missing.
- Team/opponent Understat feature families are masked consistently in training and scoring. The XGBoost manifest records 80 masked unavailable columns.

The source manifest and individual source pins must travel with any reused data artifact. A matching column name alone is not proof that the underlying source value or missingness state is identical.

## 5. Important differences that must not be hidden

### XGBoost target versus 2PM target

The XGBoost trainer learns conditional non-appearance points per 90 minutes. Its target removes the FPL appearance point(s), scales to 90 minutes, and trains only on appearances of at least 30 minutes.

2PM instead models the player-points outcome distribution using its two-component Poisson-mixture objective. The 2PM label must be constructed from observed FPL points under the approved 2PM target policy. Do not substitute XGBoost's transformed `target_points` or XGBoost predictions.

### Historical training coverage and OOT boundary

The verified extended Dastan release contains six historical seasons, 2020/21–2025/26. The governing 2PM decision is to use all eligible seasons in that historical range for training and chronological validation, subject to 2PM-specific feature, target, identity, and point-in-time admission gates. The earlier 2025/26-only defensive candidate cohort is superseded. The 2026/27 season remains a separate sealed OOT evaluation period.

### Point-in-time limitation

The XGBoost training artifact is verified as the historical XGBoost training input. It is **not automatically certified as a point-in-time-safe 2PM training frame**.

The 2PM source-vintage audit found that final-snapshot historical player-fixture files can contain rows absent from the latest source version available before an earlier target deadline. The current 2PM defensive protocol therefore requires target-GW-specific source vintages and matching archived pre-deadline snapshots. The final XGBoost frame may be used as a parity/reference artifact, but its feature values must not be admitted into 2PM training until the row-level source-vintage and value-parity checks pass.

Understat history in the XGBoost release is also a frozen historical source. Its publication/update vintages are not proven for every target deadline by the XGBoost manifest alone. Preserve that as an explicit feature-family provenance gate; do not infer deadline availability from the fact that a metric appears in the final frame.

## 6. Current 2PM pipeline mismatch identified

The current branch's `cta-2pm-dastan-286-candidate-rebuild.yml` and defensive audit workflow use a separate four-season 2PM candidate/run-80 artifact path. That path is useful for the existing sequence, identity, and defensive-source audits, but it is not the exact XGBoost training artifact located above.

Do not silently describe those two artifacts as byte-identical or as the same row population.

The next integration should:
1. Download the immutable XGBoost run artifact by its known run ID and artifact name (no new source acquisition).
2. Verify `training/features_with_snapshots.parquet`, its SHA-256, release manifest, source pins, and the exact 286-feature order before use.
3. Isolate the authorized 2025/26 rows and compare keys, feature values, and missingness against the current 2PM point-in-time candidate.
4. Use the XGBoost artifact as the parity/reference baseline while reconstructing any values that require target-deadline source vintages.
5. Build 2PM sequence tensors from validated historical played-match states plus target pre-deadline query tokens; do not flatten the XGBoost frame and assume it already contains paper-compliant sequence observations.
6. Keep 2026/27 OOT labels sealed until the frozen final evaluation step.

## 7. Training status

- XGBoost artifact located: **PASS**.
- XGBoost training-frame checksum verified: **PASS**.
- XGBoost and 2PM 286-feature ordered schemas identical: **PASS**.
- 2PM feature admission: **HOLD**.
- 2PM target-GW source-vintage/value parity: **NOT YET PASSED**.
- 2PM sequence adaptation: **NOT YET PASSED**.
- 2PM training authorization: **NOT GRANTED**.

No training was started and no external source was reacquired during this audit.


## 8. Updated 2PM training-scope decision (2026-11-26)

The user has explicitly confirmed that 2PM must be developed independently using the extended Dastan dataset adapted to the Transformer architecture, and must train on all eligible historical seasons rather than only two seasons. The verified historical coverage is 2020/21–2025/26. The prior 2025/26-only candidate cohort is superseded. Keep 2026/27 sealed for out-of-time evaluation. This is an independent 2PM modelling decision; XGBoost is only a provenance clue for the existing data foundation and does not prescribe feature masks, architecture, or training policy.
