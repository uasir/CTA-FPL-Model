# FPL Decision-Value Evaluation Protocol

Status: **RESEARCH PROTOCOL / NOT A PERFORMANCE CLAIM**

## 1. Purpose

The project's goal is to develop information that helps managers make better FPL decisions and achieve better outcomes. Point prediction is a central input, but point-prediction accuracy alone is not a sufficient evaluation of the complete system.

Evaluation must connect three distinct layers:

1. **Forecast quality** — how well does a model estimate player points and uncertainty?
2. **Opportunity/ranking quality** — does it identify the stronger players and opportunities at the relevant decision horizon?
3. **Decision value** — do decisions made using those outputs outperform credible alternatives under the same information, constraints and scoring rules?

These layers must be reported separately. A gain in one layer must not be presented as proof of a gain in another.

## 2. Three output tracks remain distinct

Evaluate the following as separate systems:

- **Conventional personal-squad recommendations:** use conventional expected-points forecasts and the manager's actual squad/constraints.
- **CTA-informed personal-squad recommendations:** use CTA-informed forecasts/context for the same squad and constraints.
- **General CTA player recommendations:** rank players/opportunities independently of any manager's squad.

The first two must be compared on identical squad snapshots, budgets, free transfers, chips, deadlines, available information and decision constraints. The general CTA ranking must not receive personal squad state.

The standalone CTA predictor, conventional 2PM-Transformer and optional CTA-augmented 2PM-Transformer also remain distinct forecast tracks. The augmented model must be compared against both standalone tracks on the exact same chronological cohort and folds.

## 3. Forecast scorecard

Report, at minimum, on matched player-gameweek observations:

- MAE and RMSE.
- Mean error / signed bias.
- Median absolute error and error quantiles/tails.
- Shares within predeclared error bands (for example ±1 and ±2 points).
- Calibration and predictive-distribution scores when a model emits a distribution.
- Coverage and missing-forecast rate.

Break results down by position, minutes/appearance band, forecast horizon, player availability and relevant opportunity groups where sample sizes permit.

Do not remove exceptional hauls or difficult outcomes from the primary scorecard. Do not compare models on different cohorts without clearly labelling the comparison.

## 4. Ranking and opportunity scorecard

Evaluate player ordering separately from point accuracy:

- Spearman rank correlation and pairwise ordering accuracy.
- NDCG@K or equivalent top-of-ranking quality.
- Precision/recall or hit rate for predeclared opportunity sets where appropriate.
- Top-K realized points and regret against the best K players in the same eligible universe.
- Stability of rankings across adjacent deadlines and sensitivity to forecast uncertainty.

Define the eligible universe before scoring. Apply position, price, availability and other filters consistently. Do not select the cohort after observing outcomes.

A player ranking can be useful even when point estimates are imperfect, but ranking quality does not by itself prove that a feasible squad decision improves.

## 5. Decision-value scorecard

Evaluate recommendations by replaying decisions as they could have been made at each historical deadline.

### Personal-squad decisions

For every test deadline, preserve:

- Exact 15-player squad and purchase prices.
- Bank, free transfers, transfer history and hit cost.
- Active chips and chip availability.
- Legal formations, starting XI and bench order.
- Captain and vice-captain.
- Deadline timestamp and the information actually available at that time.
- Forecast/model version and the recommendation output frozen before the deadline.

Compare strategies under identical initial states and rules. At minimum include:

1. Hold / no-transfer policy.
2. A conventional expected-points policy.
3. CTA-informed policy.
4. Any combined policy, only as a separately labelled experiment.

The policies must share the same decision horizon, transfer budget, hit treatment and chip rules. Use official FPL scoring, autosubs and chip scoring when replaying realized outcomes. Do not credit a strategy with information that arrived after the deadline.

### Core realized-utility measures

Report:

- Realized squad points over the declared horizon.
- Net realized points after transfer hits and applicable chip effects.
- Incremental points versus hold and conventional policies.
- Field-relative realized points when a reliable, deadline-matched field reference exists.
- Decision regret against the best feasible alternative in the defined action set.
- Transfer, captaincy and starting-XI regret as separate diagnostics.
- Outcome dispersion and downside/tail outcomes across deadlines.

Regret must be defined against a clearly stated feasible set. A regret value against a shortlist is **shortlist regret**, not global regret. Global regret requires evaluating the complete feasible action set or a demonstrably exhaustive optimizer.

Rank gain is a useful outcome in a prospective manager simulation, but it is not a substitute for these measures. Report absolute points and rank/field-relative outcomes together; rank is cohort-dependent and can be noisy.

### General player recommendations

Because this output is independent of a personal squad, evaluate it with ranking and opportunity measures first. A separate portfolio simulation may test how the rankings perform when applied to a declared generic strategy, but must not be presented as a personal-squad result.

## 6. Counterfactual and hindsight controls

A historical replay must only use data available at the decision deadline. Freeze and archive each model output before outcomes are known.

The realized best feasible action is a hindsight oracle and may be used to calculate regret, but it must never be treated as a deployable recommendation or as a fair strategy baseline.

Use the same starting squad, budget, transfer/chip constraints, target horizon and scoring engine for every policy. When a policy changes future squad state, replay the full sequence rather than independently optimizing each gameweek from a fresh squad.

Report both:
- **One-step decision value:** outcome of the immediate decision over a predeclared horizon.
- **Sequential policy value:** outcome of the full sequence of decisions with evolving squad state.

Do not mix these estimands.

## 7. Statistical design

- Use chronological walk-forward evaluation; never random-split player-gameweek rows across time.
- Freeze model selection and policy parameters using training/validation periods only.
- Reserve later seasons or deadlines for untouched evaluation where data permits.
- Use paired comparisons on the same deadlines and starting states.
- Quantify uncertainty with deadline- or manager-season-clustered bootstrap intervals; do not treat correlated player rows as independent samples.
- Report sample size, coverage, missingness and the number of evaluated deadlines for every result.
- Test robustness across seasons, rank cohorts and risk/decision profiles when the required data exists.
- Correct for repeated policy/model selection and disclose exploratory analyses.

## 8. Field-relative risk and EO

LiveFPL EO is contextual field information, not a prerequisite for forecasting player points. Use it only in field-relative or manager-decision analyses, with cohort, sample size, timestamp, target deadline and post-lock verification recorded.

CoVar is a separate portfolio-risk diagnostic. It must not silently alter forecast scores or player rankings. Promote it into a decision policy only after:
1. covariance forecasts are stable across rolling windows and shrinkage choices;
2. predicted covariance is tested against subsequent realized covariance;
3. uncertainty is quantified; and
4. a CoVar-aware policy demonstrates out-of-sample decision-value improvement over the same EV-only policy on matched chronological tests.

Until then, CoVar remains zero-weight and research-only.

## 9. Promotion and reporting rules

A model or policy is not promoted on one attractive metric or one favorable gameweek.

Every comparison must state:
- what changed (forecast, ranking, decision policy, or multiple layers);
- the exact matched cohort and time period;
- the baseline and comparator;
- the metric and uncertainty interval;
- coverage and missingness;
- whether the result is retrospective, prospective or exploratory;
- whether the result is statistically and practically meaningful.

A model may have worse MAE/RMSE but better ranking or decision value. That is a valid finding if demonstrated on matched out-of-sample data. Conversely, improved prediction accuracy does not establish decision value unless the downstream policy benefits too.

No arbitrary target rank or unattainable prediction benchmark should be used as a promotion gate. Establish realistic competitive baselines from actual external outputs and reproducible internal policies.

## 10. Immediate implementation sequence

1. Keep the existing forecast scorecards and standalone model tracks running independently.
2. **In progress:** build a frozen-deadline decision replay dataset with official outcomes and exact starting squad state; no historical replay cohort has been assembled yet.
3. **Exploratory v0.1 implemented:** a deterministic one-gameweek scorer handles legal XI/bench structure, formation-aware autosubs, captain/vice, Triple Captain, Bench Boost and transfer hits. It requires externally verified action/chip legality and does not yet transition squad or budget state. See [FPL_ONE_GAMEWEEK_REPLAY_INPUT_CONTRACT.md](FPL_ONE_GAMEWEEK_REPLAY_INPUT_CONTRACT.md).
4. **Implemented, not yet empirically validated:** paired policy comparison enforces identical starting-state IDs, identical policy sets across deadlines and pre-deadline decision freeze timestamps.
5. Add complete feasible-set regret and distinguish shortlist regret from exhaustive global regret.
6. Validate the replay scorer against known official FPL team histories and edge cases, then assemble a point-in-time historical decision archive.
7. Add sequential multi-gameweek state transitions after one-step replay is verified.
8. Integrate LiveFPL field context and CoVar only in their separate downstream evaluation layers.

This protocol defines what must be measured. It does not claim that any current model or optimizer has already demonstrated decision-value improvement.
