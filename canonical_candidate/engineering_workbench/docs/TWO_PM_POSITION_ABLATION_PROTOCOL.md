# 2PM position-aware feature ablation

Status: **PRE-REGISTERED RESEARCH EXPERIMENT / NO MODEL PROMOTION**

## Question

Does adding the player position as a four-way one-hot feature improve the standalone conventional FPL 2PM Transformer on the same chronological player-gameweek validation cohort?

## Arms

- **Base:** existing conventional FPL feature set, including lagged points, minutes, appearance and xG/xA aggregates.
- **Position:** identical feature set plus `position_gkp`, `position_def`, `position_mid`, and `position_fwd`.

No CTA, Opta, Wyscout, StatsBomb, LiveFPL EO, ownership, transfer, xP, target-fixture statistics or post-match features are introduced by this experiment.

## Design controls

- Same pinned multi-season source revision and same panel rows.
- Same expanding-season folds, training/calibration/validation split, sequence length, architecture, optimizer, epoch count and random seed.
- The only intended change between arms is the four position indicators.
- Each fold selects features only from its training block.
- Each model writes player-gameweek predictions to runner-local CSVs; exact key and target matching is enforced before comparison.
- Position and base results are paired on identical player-gameweek rows.
- Player-season cluster bootstrap intervals are reported for paired MAE/MSE differences.
- Point-error and ranking metrics are reported separately.

## Outcomes

Primary forecast diagnostics: MAE, RMSE, signed bias and error-band/tail diagnostics.

Ranking diagnostics: Spearman and top-100 realized points are computed separately within each season-gameweek deadline, then macro-averaged across deadlines. A pooled top-K across different Gameweeks is not a valid FPL selection metric. Paired ranking deltas use season-clustered bootstrap intervals.

Uncertainty: player-season-clustered bootstrap intervals for position-minus-base absolute and squared error differences.

## Interpretation

- Negative paired MAE/MSE deltas favor the position-aware model.
- Ranking improvement is a separate finding; it must not be inferred from lower MAE.
- One retrospective source-vintage experiment cannot establish prospective or decision-value improvement.
- A result is not promoted on a single pooled metric; inspect fold-by-fold stability and coverage first.

## Gameweek chronology validation

The panel builder reads the merged source's explicit `GW` field when present and falls back to `round`. The 2019/20 COVID-interrupted season requires a known source-specific normalization: labels 39–47 map to FPL gameweeks 30–38 (subtract nine); this is a source-label offset, not nine additional FPL deadlines. The builder now applies that mapping only to 2019/20, records the number of normalized rows, compares `GW` and `round` after normalization, and rejects any remaining labels outside 1–38. This mapping is consistent with published handling of the Vaastav 2019/20 export ([example normalization](https://github.com/saheedniyi02/fpl-ai/blob/master/fpl/process.py)). The first ablation's metrics are preliminary until the model is rerun on the corrected panel.
## Point-in-time limitation

The historical source contains retrospective season exports. Position labels are not guaranteed to be frozen as of each historical deadline. This ablation therefore tests whether the position signal is useful under this retrospective panel, not whether the complete feature pipeline has been point-in-time verified.

## Execution

The GitHub Actions `position_ablation_research` job builds the panel locally, trains both arms, writes local prediction files, performs the paired comparison, and retains only aggregate logs. No raw panel, player-level predictions or report artifacts are uploaded.

## Decision gate

Keep the position feature experimental until it demonstrates stable improvements across multiple validation seasons and the point-in-time data-vintage problem is addressed. It must also be evaluated downstream in ranking and decision-value tests before affecting recommendations.

## Corrected rerun gate — 2026-11-20

The earlier completed run (workflow run 44604401009) is retained as a preliminary diagnostic only. It used the panel builder before the explicit-GW chronology correction, so its metrics are not the accepted ablation result. Its within-deadline ranking comparator was corrected, but that does not repair the panel chronology.

The panel-builder correction passed the engineering test suite (workflow run 44604839346; 391 passed, 1 skipped, 3 subtests passed). The accepted rerun must rebuild the panel from the corrected builder in the same job as both training arms and the paired comparator. Before interpreting any model metrics, verify the emitted per-season panel audit: each season's gameweek labels must be within 1–38, and all explicit-GW/round disagreements must be reported. If any season has an invalid label or unexplained chronology issue, stop interpretation and fix the source mapping.

No feature promotion is permitted from the old run. The rerun must report:
- paired raw and calibrated MAE/RMSE differences with player-season-clustered intervals;
- within-deadline macro Spearman and top-100 realized points, with season-clustered paired intervals;
- per-season and per-deadline coverage / stability;
- the exact number of matched player-gameweeks and deadlines.

This remains a forecast-and-ranking ablation, not a squad-decision-value test. It cannot establish that position features improve manager decisions or rank outcomes in an actual season.
