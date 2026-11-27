# 2PM Stage-A experimental trainer

The first dedicated trainer is `scripts/train_two_pm_poisson_transformer.py`.
It trains the independent `PaperTwoComponentPoissonTransformer` through the
existing player-Gameweek adapter and exact independent-fixture mixture NLL.

## Scope and safeguards

- Loads the Run 83 grouped tensor shards; it does not reconstruct or download source data.
- Uses the 259 `common_candidate` features only. The 27 scoring-regime-dependent
  defensive features are excluded from Stage A.
- All common-feature source-availability states are explicitly encoded as
  `UNKNOWN` (2). This does not confer source-vintage admission.
- Missing numeric values are imputed from training-fold medians only; scaling
  statistics are also fitted on training data only.
- Uses expanding-season folds: train 2020/21, validate 2021/22; then add each
  completed historical season through the 2024/25 validation fold.
- 2025/26 is reserved for the separate defensive-scoring Stage-B adaptation.
  2026/27 remains sealed OOT and is never loaded by this trainer.
- The grouped-label support shift is fixed at 20, because Run 83 stores
  player-Gameweek labels rather than fixture-level labels for fitting a
  fixture-level support floor. Every validation label is checked against the
  corresponding aggregate support.
- Outputs are explicitly experimental and `NOT_ADMITTED`; no production
  weight or recommendation path is changed.

## Run

Extract the Run 83 artifact so that the extracted directory contains
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
