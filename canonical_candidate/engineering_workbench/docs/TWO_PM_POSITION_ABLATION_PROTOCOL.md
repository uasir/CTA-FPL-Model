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

## Point-in-time limitation

The historical source contains retrospective season exports. Position labels are not guaranteed to be frozen as of each historical deadline. This ablation therefore tests whether the position signal is useful under this retrospective panel, not whether the complete feature pipeline has been point-in-time verified.

## Execution

The GitHub Actions `position_ablation_research` job builds the panel locally, trains both arms, writes local prediction files, performs the paired comparison, and retains only aggregate logs. No raw panel, player-level predictions or report artifacts are uploaded.

## Decision gate

Keep the position feature experimental until it demonstrates stable improvements across multiple validation seasons and the point-in-time data-vintage problem is addressed. It must also be evaluated downstream in ranking and decision-value tests before affecting recommendations.