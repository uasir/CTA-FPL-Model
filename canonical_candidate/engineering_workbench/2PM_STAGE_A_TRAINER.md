# 2PM Stage-A experimental trainer

The first dedicated trainer is `scripts/train_two_pm_poisson_transformer.py`.
It trains the independent `PaperTwoComponentPoissonTransformer` through the
existing player-Gameweek adapter and exact independent-fixture mixture NLL.

## Scope and safeguards

- Loads the corrected six-season grouped tensor artifact (Run 85 or a later audited replacement); it does not reconstruct or download source data. Run 83 is prohibited.
- Uses the 259 `common_candidate` features only. The 27 scoring-regime-dependent
  defensive features are excluded from Stage A.
- Common-feature source-availability states may remain `UNKNOWN` (2); this does not confer source-vintage admission.
- The training loader re-enforces the current manifest's `HOLD` / `FORCE_UNOBSERVED`
  policies even when an older tensor sidecar says a value is observed. Manifest 1.7.0
  holds all 152 Understat-derived features (30 player-history, 120 own/opponent
  rolling, and two direct rank fields) unobserved pending row-level vintage proof.
- The remaining 107 common features are still provisional: FPL-native historical
  source vintages and some market-field semantics remain unresolved. A successful
  Stage-A run would be research-only, not evidence of source admission; keep training
  paused until those remaining checks are completed or a separate research decision is recorded.
- Missing numeric values are imputed from training-fold medians only; scaling
  statistics are also fitted on training data only.
- Uses expanding-season folds: train 2020/21, validate 2021/22; then add each
  completed historical season through the 2024/25 validation fold.
- 2025/26 is reserved for the separate defensive-scoring Stage-B adaptation.
  2026/27 remains sealed OOT and is never loaded by this trainer.
- The grouped-label support shift is fixed at 20, because the grouped tensor artifact stores
  player-Gameweek labels rather than fixture-level labels for fitting a
  fixture-level support floor. Every validation label is checked against the
  corresponding aggregate support.
- Outputs are explicitly experimental and `NOT_ADMITTED`; no production
  weight or recommendation path is changed.

## Run

Extract the corrected Run 85 artifact (or a later audited replacement) so that the extracted directory contains
`postmatch-grouped-dataset/player_gameweek_tensors`, then run from the
engineering workbench directory:

```bash
python scripts/train_two_pm_poisson_transformer.py \
  --artifact-root /path/to/extracted/2pm-dastan-candidate \
  --schema config/2pm_dastan_286_schema.json \
  --manifest config/2pm_feature_group_manifest.json \
  --output artifacts/2pm-stage-a-experiment \
  --allow-provisional-common-features
```

The explicit provisional flag is required because the current feature manifest
does not admit the common feature families for production use. It authorizes
only this research experiment; it does not alter the manifest or candidate
admission status.

Each fold writes its best checkpoint, fold-only preprocessing state, training
history and player-Gameweek OOF point predictions. The root summary records
fold metrics and the experimental status. Stage B, final six-season refit and
the 2026/27 OOT evaluation are intentionally not implemented by this Stage-A
entry point.
