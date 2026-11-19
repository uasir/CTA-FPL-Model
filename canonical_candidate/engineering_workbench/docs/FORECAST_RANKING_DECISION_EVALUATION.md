# FPL Forecast, Ranking and Decision Evaluation

This document formalises the project's existing four evaluation dimensions. It does not replace the model architecture or create a new model-selection objective.

## 1. Point-prediction accuracy

Evaluate numerical expected-points forecasts against official realised FPL points.

- **MAE:** mean absolute error; typical point miss.
- **RMSE:** root mean squared error; gives larger misses greater influence.
- **ME:** mean error, defined here as actual minus predicted. Positive values indicate underprediction; negative values indicate overprediction.
- **Within ±1 (Plus One):** share of forecasts with absolute error less than or equal to one point.
- **Within ±2 (Plus Two):** share of forecasts with absolute error less than or equal to two points.
- **Error distribution and tails:** report quantiles and large-error rates; retain genuine high-scoring outcomes.
- **Calibration diagnostics:** compare predicted and realised means across forecast ranges.

RMSE is diagnostic, not the sole promotion gate. Do not remove or winsorise genuine hauls merely to improve a metric.

## 2. Probability and distribution quality

Where the model emits probabilities, evaluate them with proper scoring rules and reliability diagnostics:

- Brier score and log loss for binary outcomes such as 6+, 8+ and 10+.
- Reliability bins comparing predicted probabilities with observed frequencies.
- Scoring-band performance for the model's declared outcome bands.
- Tail and haul-rate diagnostics, including whether the model systematically compresses high-end outcomes.

Do not invent probability metrics from a single expected-points value. An xP forecast alone is not a probability distribution.

## 3. Ranking quality

Evaluate whether the model orders players usefully, separately from the accuracy of the numerical point estimates.

- Spearman rank correlation.
- NDCG@10 and NDCG@15.
- Per-gameweek top-K overlap and selection performance.
- Mean realised points among selected top-K players, compared with the candidate universe and a retrospective oracle reference.

Compute top-K overlap per gameweek; do not pool player selections across gameweeks into one misleading overlap count.

## 4. Decision performance

Evaluate the recommendation actually made by the model against the alternatives that were genuinely feasible when the decision was made.

**Core distinction:** forecast accuracy and decision correctness are separate outcomes. A model can underpredict a player's points and still correctly recommend that player over an alternative. Conversely, an accurate point forecast does not guarantee that the resulting FPL decision was good.

For each decision, preserve:

- Decision identifier and decision type (player pick, transfer, captain, starting XI, or full squad).
- The recommendation chosen by the model before the deadline.
- The alternatives considered and whether each was feasible under the same pre-deadline constraints.
- The model's point forecast and/or separate recommendation score, without conflating them.
- The realised utility of each feasible option, calculated after the relevant official FPL rules.

Report:

- **Selected realised utility:** outcome of the recommendation.
- **Best-feasible realised utility:** retrospective reference among the recorded feasible alternatives.
- **Regret:** best-feasible realised utility minus selected realised utility, floored at zero.
- **Zero-regret / recommendation-optimal rate:** share of decisions that selected an option tied for the best realised feasible outcome.
- **Pairwise wins, ties and losses:** how the selected option actually performed against the other feasible options.

The best-feasible realised outcome is an oracle reference for regret, not an achievable forecast or a fair prospective baseline by itself.

### Utility and FPL constraints

For an isolated player choice, utility may be the player's official points. For a transfer, include transfer-hit costs where relevant. For captaincy, apply the official captain multiplier. For a starting XI or full squad, evaluate the realised team score with formation, bench substitutions, captaincy and applicable transfer costs. Do not compare isolated player points when the actual decision concerns a complete squad outcome.

Feasibility must be determined using information available at the decision deadline: budget, positions, club limits, squad composition, free transfers, hit costs and any other applicable constraints. An infeasible option must never be treated as an available alternative.

## Evaluation safeguards

1. Freeze forecasts, rankings and recommendations before the deadline.
2. Keep forecast, ranking and decision scorecards separate, then interpret them together.
3. Compare models on the same player-GW cohorts, decision opportunities, feasible alternatives and utility definitions.
4. Use chronological evaluation and clustered uncertainty estimates where appropriate.
5. Keep retrospective oracle outcomes separate from deployable model performance.
6. Do not declare a universal winner from one metric. Report trade-offs and evidence across all four dimensions.

## Example

| Player | Predicted points | Actual points |
|---|---:|---:|
| A | 2 | 2 |
| B | 8 | 15 |

If the model recommended B over A, B's forecast has an absolute error of 7 points, while the recommendation is the better decision: it selected the player who scored 13 more points. The report must preserve both results rather than marking the recommendation wrong because the point estimate was inaccurate.
