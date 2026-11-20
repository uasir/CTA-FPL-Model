# CoVar Methodology Specification

**Status:** Research specification — proposed for review  
**Branch:** `feat/m4-field-portfolio-intelligence`  
**Scope:** Strategic FPL portfolio dependence, upside/downside concentration, and field-relative outcomes.  
**Production status:** Disabled. Decision weight remains 0; production eligibility remains false.

## 1. Purpose and interpretation

CoVar is the strategic assessment of how a manager's selected FPL assets interact through shared football outcomes and how those interactions shape the distribution of gameweek results relative to the field.

It is broader than a historical player covariance matrix. The model must distinguish:

1. **Defensive CoVar:** shared defensive outcomes among a goalkeeper and/or defenders from the same team.
2. **Offensive CoVar:** shared attacking outcomes among teammates, including scorer-assister combinations and multi-goal team performances.
3. **Field CoVar:** how the manager's correlated exposures compare with the ownership, effective ownership, captaincy and (where available) lineup composition of a defined rival-manager cohort.

The strategic question is not simply whether covariance is positive or negative. It is whether the resulting joint outcome distribution creates a desirable balance of expected points, ceiling, floor, downside concentration and probability of outperforming the relevant field.

## 2. Upside, downside and opposing exposure

### 2.1 Concentrated upside and downside

A same-team defensive stack can multiply the value of a clean sheet: the goalkeeper and defenders may all receive clean-sheet points, with additional save, appearance, bonus or defensive-contribution points where applicable. The same stack concentrates downside when the team concedes; a single goal can remove clean-sheet points from several slots at once.

A same-team attacking stack can benefit from a strong team performance. A goal may reward the scorer and assister, while a multi-goal performance can create multiple return opportunities. A poor attacking performance, low team-goal total or unexpected role/minutes outcome can affect several selected attackers together.

Therefore:
- **Boom:** favourable shared team outcomes lift multiple squad slots together.
- **Bust:** adverse shared outcomes damage multiple slots together.
- High dependence is not intrinsically good or bad; its value depends on the objective, marginal expected points, the shape of the tails and the field's corresponding exposure.

### 2.2 Opposing exposure / internal opposition

An attacker facing a manager's own defender or goalkeeper creates opposing fixture exposure. A goal conceded can help the attacker while harming the defender's clean-sheet outcome. This can reduce the portfolio's sensitivity to one match outcome and may cap the ceiling compared with a same-direction stack.

Do not hard-code this pairing as always negatively correlated or as a guaranteed hedge. The defender may still score appearance, save, tackle, interception or bonus points; the attacker may blank; and the relationship depends on minutes, role, scoring events and match state. Model the joint distribution and report the hedge effect empirically.

## 3. Statistical objects — keep separate

The implementation must report distinct quantities rather than one overloaded CoVar score.

### 3.1 Player outcome covariance

Let (X_i) be the FPL points scored by player (i) in a specified gameweek and (w_i) the applicable scoring multiplier/exposure. For a fixed portfolio:

`Var(S) = sum_i(w_i^2 Var(X_i)) + 2 sum_{i<j}(w_i w_j Cov(X_i,X_j))`

This is the variance of the selected player-points portfolio. It is useful for describing aggregate dispersion but does not by itself identify whether variance is desirable or whether the portfolio beats the field.

### 3.2 Relative-to-field variance

Let (S_u) be the user's score and (S_f) the score of a clearly defined field benchmark or sampled rival manager:

`Var(S_u - S_f) = Var(S_u) + Var(S_f) - 2 Cov(S_u,S_f)`

This measures dispersion in the user's score relative to the benchmark. It is one Field CoVar diagnostic, not the definition of all CoVar. Report the distribution of (S_u-S_f), not variance alone.

### 3.3 Joint-event / scenario distribution

Where possible, estimate player outcomes through shared match and team events, then derive player points from those events. This preserves dependencies that a player-by-player independent model would miss. Historical covariance remains a diagnostic, prior or fallback research input; it is not sufficient as the sole forward-looking model.

### 3.4 Do not collapse metrics prematurely

Keep expected points, variance, covariance contribution, downside probability, upper-tail outcomes, probability of beating the field and relative-score quantiles as separate outputs. Do not combine EV, EO, covariance or rank into an arbitrary synthetic score without a separately specified and validated objective.

## 4. Dependency mechanisms to model

### 4.1 Defensive layer

Represent, at minimum:
- Team clean-sheet / goals-conceded outcome.
- Goalkeeper and defender exposure to that shared team outcome.
- Player-specific minutes and start/substitution probabilities.
- Saves, goals prevented where supported, defensive contributions, goals/assists and bonus mechanisms where supported.
- Opponent strength, venue and relevant pre-deadline team context.

A shared team defensive event is the common cause. Do not assume every defender has identical points conditional on a clean sheet.

### 4.2 Offensive layer

Represent, at minimum:
- Team goals and attacking-event volume.
- Goal scorer and assist allocation, including the possibility of unassisted goals.
- Player roles, expected minutes, penalty/set-piece responsibility and substitution risk where supported.
- Bonus-point interactions and the fact that one event can create points for more than one player.
- Opponent and match context known at the decision timestamp.

Do not assume all same-team attackers are positively correlated in every scenario. They may compete for a limited number of goals, minutes or bonus points even while benefiting from a common team-goal environment.

### 4.3 Cross-fixture and opposing layer

Include opponent-facing pairs (for example, a user's attacker against their own defender/goalkeeper) and cross-team match dependencies where the data and model support them. Label these as opposing exposures, not guaranteed hedges.

### 4.4 FPL scoring and squad mechanics

The scenario engine must account for applicable:
- Appearance and minutes outcomes.
- Goal, assist, clean-sheet, save, penalty, card and bonus scoring.
- Captain and vice-captain multipliers; Triple Captain as an additional multiplier.
- Bench order, autosubs and formation legality when calculating actual squad score.
- Double gameweeks, blanks, chips and any rule changes for the season being evaluated.

Player-points covariance should not be mistaken for final squad-score covariance when captaincy, bench substitution or chip mechanics alter the weights and inclusion of player outcomes.

## 5. Field CoVar

The field comparison must define its population and time boundary explicitly.

Required dimensions, where available:
- Selected-by ownership (distinct from EO).
- Effective ownership, with captaincy and Triple Captain treatment documented.
- Starting-lineup / squad exposure and captain share.
- Rank-stratified or otherwise explicitly defined manager cohort.
- Sample size, effective sample size, coverage, missingness and uncertainty.
- User's own portfolio exposure on the same player universe and the same deadline snapshot.

Use the existing LiveFPL / rank-stratified EO pipeline as the field reference. Do not create a competing ownership estimator inside CoVar. A poll-implied pre-deadline EO estimate must remain separately labelled as an estimate and must not be silently substituted for observed EO.

For each scenario, compare the user's actual squad score with either:
1. individual sampled rival-manager scores, where complete squad/lineup data are available; or
2. a clearly defined field portfolio benchmark, with its limitations stated.

Do not treat a simple sum of player EO as a complete field portfolio: it does not encode which players are held together by the same managers. Manager-level joint squad samples are required to estimate the field's own portfolio covariance faithfully.

## 6. Objectives and decision interpretation

The model must support at least three distinct decision lenses:

1. **Mean-preserving risk comparison:** compare portfolios with similar expected points and show how their outcome distributions differ.
2. **Ceiling-seeking / rank-upside analysis:** estimate upper-tail outcomes and probability of materially outperforming the selected field cohort.
3. **Downside protection analysis:** estimate lower-tail outcomes and probability/magnitude of underperforming the field.

Do not maximize variance as a universal objective. Higher variance can increase both boom and bust. A recommendation must state which objective it serves and quantify the associated cost in expected points or downside risk.

Free Hit and regular-gameweek decisions must be evaluated separately. A Free Hit permits a temporary, highly correlated portfolio that may be inappropriate for a persistent squad. Regular-GW analysis must respect the user's stated squad construction and transfer constraints; CoVar must not create routine rotation or low-value bench transfers.

## 7. Field-targeting decision hierarchy

Field CoVar is a deliberate portfolio choice relative to a defined field cohort, not a synonym for selecting low-owned players. The model must estimate both the user's absolute outcome distribution and the relative distribution against the field. A low-EO pick is useful only when its projected points, role, fixture and joint-outcome profile justify the opportunity cost.

Use the following hierarchy as a research and recommendation ordering, not as unconditional rules:

1. **Lower-owned captaincy with little or no EV sacrifice.** First identify captaincy alternatives whose projected points remain competitive while their effective captaincy exposure is materially lower than the field's. Quantify the captaincy multiplier and the resulting relative upside/downside. Do not recommend a low-owned captain solely because ownership is low.
2. **Multiple defenders from the same team.** Assess goalkeeper/defender and defender/defender combinations for shared clean-sheet upside and concentrated goals-conceded downside. Compare the stack's expected points with the best alternative use of those squad slots.
3. **Avoiding opposing attackers and defenders within the user's portfolio.** Evaluate whether removing an internal opposing fixture exposure increases the portfolio's directional sensitivity to a desired match outcome. Treat this as a possible ceiling-concentration choice, not a universal prohibition: an opposing attacker may still have superior EV or provide useful downside protection.
4. **Combining attackers and defenders from the same team.** Evaluate mixed stacks, especially set-piece takers paired with credible set-piece targets, using event-level probabilities. A goal can create both attacking and defensive returns, but the combination is not automatically synergistic and must be assessed against role, minutes, event allocation and alternative players.

These approaches are generally more useful when the relevant exposure is low in the selected field cohort. However, ownership is a relative context variable, not a direct measure of player quality or a standalone objective.

### 7.1 EV opportunity-cost test

Every field-targeting recommendation must be compared with a conventional EV-oriented alternative under the same budget, squad legality, player availability and decision-time information.

Report at minimum:
- Expected-points difference versus the EV-oriented alternative.
- Difference in captaincy/EO exposure and, where available, manager-level joint exposure.
- Change in probability of beating the chosen field cohort and in the upper/lower tails of relative score.
- The scenarios that create the upside and the scenarios that create the downside.
- Sensitivity to uncertain minutes, role, team goals and ownership estimates.

A field-CoVar alternative should not be preferred merely because it has greater variance or lower ownership. Its additional rank-upside probability must be shown alongside its EV sacrifice and downside cost. Some high-EV, highly owned players may remain essential when the projected points advantage is too large to justify fading them.

### 7.2 Rank and risk-appetite dependence

The objective and acceptable EV trade-off must be declared for the decision. It may depend on current rank, distance to the target rank, remaining gameweeks, risk appetite and downside tolerance. Do not infer a universal risk preference from rank alone. Show alternative objective profiles where the appropriate trade-off is uncertain, and keep the user's selected objective explicit.

### 7.3 Free Hit versus regular-GW field populations

For Free Hit analysis, distinguish at least:
- Managers using Free Hit, whose temporary squad construction can create concentrated one-week exposures.
- Managers not using Free Hit, whose squads may be constrained by longer-term structure and transfers.
- The combined overall field, if that is the rank comparison the user wants to optimize.

Use the most relevant cohort for the decision and report cohort sample sizes and uncertainty. Do not assume that overall EO alone describes the Free Hit population or its joint squad combinations.

For regular-GW analysis, use the relevant overall/rank-stratified field cohort and preserve the user's persistent squad constraints. Free Hit-specific portfolio logic must not be transferred automatically to regular-GW squad construction.

### 7.4 Stack opportunity-cost examples

The framework must be able to reject an intuitively attractive stack when its opportunity cost is too high. For example, triple-defence exposure should be compared with stronger projected attacking options from the same club; a mixed team stack should account for a high-EV striker or attacker whose presence changes the portfolio's directional exposure. The output should explain why a proposed stack is or is not justified, rather than label a team stack as inherently CoVar-positive.

## 8. Estimation and simulation approach

Preferred forward-looking architecture:
1. Generate shared team/match scenarios from information available before the deadline.
2. Generate player minutes, roles and event participation conditional on those scenarios.
3. Allocate goals, assists, clean sheets and other scoring events consistently.
4. Convert events to FPL player points using the season's scoring rules.
5. Apply captaincy, chips, bench order and autosub rules to obtain the user's final squad score.
6. Apply the same scenario framework to sampled field managers or a clearly specified benchmark.
7. Summarize the distribution of user score, field score and relative score.

Historical player covariance may be used for descriptive diagnostics, shrinkage priors or model checks. It must not replace event-level causal structure where that structure is available. Do not zero-fill missing covariance cells. Do not infer zero covariance from absent data.

All inputs must be point-in-time valid. No post-deadline lineups, actual points, retrospective revisions or future information may enter a pre-deadline simulation.

## 9. Required outputs

For each candidate portfolio, report where estimable:
- Expected squad points and expected relative points.
- Portfolio variance and standard deviation.
- Pairwise and grouped covariance contributions (defensive, offensive, opposing and cross-team).
- Probability of beating the selected field benchmark.
- Probability of beating the field by defined thresholds.
- Lower-tail and upper-tail quantiles; downside and boom probabilities.
- Expected shortfall / conditional tail summaries where sample size supports them.
- User and field exposure to relevant team/player outcomes.
- Sensitivity to minutes, lineup, team-goal, clean-sheet, event-allocation and covariance assumptions.
- Coverage, uncertainty and explicit reasons for unavailable metrics.
- EV opportunity cost against the conventional alternative and the field cohort used for the comparison.

A single CoVar number may be displayed only as a clearly labelled summary of a specified objective; it must not hide the underlying dimensions.

## 10. Validation protocol

Before any decision use:
- Point-in-time source provenance, retrieval timestamps and immutable source hashes.
- Explicit season, deadline, cohort, window and coverage policy.
- Player identity and fixture identity reconciliation.
- Complete-panel / missingness diagnostics; no silent imputation.
- Rolling-window stability and sensitivity to window selection.
- Shrinkage and model-assumption sensitivity.
- Independent uncertainty assessment, including simulation error and parameter uncertainty.
- Time-ordered out-of-sample backtests over multiple gameweeks and, where feasible, multiple seasons.
- Comparison against independent-player simulation and simpler baseline portfolios.
- Incremental utility evaluation against a predeclared objective, with uncertainty intervals.
- Calibration of marginal player outcomes and joint outcomes, including clean-sheet, team-goal and scorer-assister event frequencies where observable.
- Separate evaluation of Free Hit and regular-GW decisions, and cohort-specific calibration where field samples permit.

The current M4-T6 fail-closed eligibility gate remains mandatory. Its current checks are necessary but not sufficient for this broader methodology; the gate must eventually be extended to test joint-event calibration, field-manager joint composition and objective-specific out-of-sample utility. Passing any gate permits explicit review only, not automatic activation.

## 11. Release and integration safeguards

Until a separately reviewed implementation and validation pass:
- CoVar remains exploratory and descriptive.
- `decision_weight = 0`.
- `production_eligible = false`.
- CoVar cannot change M3 expected points, legality, transfer choice, frozen decision or decision hash.
- CoVar cannot change the conventional M5 recommendation output.
- Missing or invalid CoVar evidence must fail closed and leave existing recommendations unchanged.
- M3 post-Gameweek validation remains independent.
- No PR is merged without explicit user approval.

## 12. Proposed implementation sequence

1. Review and accept this methodology and terminology.
2. Audit current covariance artifacts and map each to the concepts above; identify what they can and cannot measure.
3. Define a versioned scenario/event data contract and point-in-time source requirements.
4. Build a small, deterministic joint-event prototype for one fixture and a few player archetypes.
5. Add defensive-stack, attacking-stack and opposing-exposure test scenarios, including boom/bust cases.
6. Add manager-level field portfolio sampling and relative-score evaluation.
7. Backtest against independent-player and non-CoVar baselines.
8. Extend the fail-closed gate with joint-event and field-composition evidence.
9. Only after independent validation, request explicit review for any proposed production use.

This specification creates no production behavior and does not authorize a change to any existing recommendation.
