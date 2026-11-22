# M3 — Multi-Gameweek Transfer Decision Policy

**Status:** Project-owner requirement recorded; implementation and validation pending.
**Applies to:** Conventional personal-squad recommendations and, after M2 promotion, CTA-informed personal-squad recommendations.
**Default decision horizon:** At least five consecutive Gameweeks, beginning with the target Gameweek.

## 1. Decision principle

A transfer is a portfolio decision over a planning horizon, not a one-Gameweek player swap. The engine must not recommend an incoming player merely because that player's expected points exceed the outgoing player's expected points in the immediate Gameweek. Likewise, it must not sell an owned player solely because that player's immediate-Gameweek expected points are low.

The primary comparison is the expected value of the manager's squad under **TRANSFER** versus **HOLD**, accumulated over a common horizon of at least five Gameweeks. The report must explain the value added or lost beyond the first Gameweek.

## 2. Minimum horizon and data admission

- Require forecasts for every Gameweek in the selected horizon, for both the incoming and outgoing players, and for the relevant existing squad players needed to assess the starting XI.
- The default horizon is five consecutive Gameweeks. A longer horizon may be used when reliable forecasts and planning context support it.
- The horizon must be explicit in the decision input and output: start Gameweek, end Gameweek, number of Gameweeks, and per-Gameweek forecast coverage.
- Do not relabel a single-Gameweek provider forecast as a five-Gameweek forecast, extrapolate it silently, or fill missing future Gameweeks with zero or repeated values.
- If complete, admissible multi-Gameweek forecasts are unavailable, return an explicit insufficient-horizon/insufficient-coverage result and **HOLD / defer the transfer decision**. A one-Gameweek xP comparison may be displayed as context only; it must not drive the transfer action.

## 3. Transfer-versus-hold comparison

For each legal transfer candidate, compare two otherwise identical squad paths over the same horizon:

1. **HOLD path:** retain the current player and current squad.
2. **TRANSFER path:** replace the outgoing player with the incoming player at the start of the horizon, applying the correct selling price, purchase price, bank, free-transfer and hit-cost rules.

At minimum, report:
- Per-Gameweek expected starting-XI points for HOLD and TRANSFER.
- Per-Gameweek incremental expected points attributable to the transfer.
- Cumulative horizon expected-points difference.
- Transfer cost, including any immediate hit and the value of the free transfer consumed where that opportunity cost is modelled.
- The Gameweek-by-Gameweek contribution, so a strong immediate week cannot conceal a poor remainder of the horizon, and a poor immediate week cannot conceal sustained future value.
- Fixture/availability/expected-minutes coverage and any uncertainty or missingness that materially affects the comparison.

A candidate must be ranked on the horizon-level squad value difference, not the immediate-week player xP difference. The action threshold must be applied to the horizon-level net value after relevant costs. Do not count the incoming player's full points as value added: compare against the outgoing player's counterfactual contribution and the actual starter displaced.

## 4. Squad and planning constraints

- Preserve the manager's confirmed starting-XI structure and no-routine-rotation preference. Bench upgrades count only if they improve the starting XI under the agreed squad policy.
- Keep goalkeeper transfers excluded unless the manager explicitly changes that constraint.
- Enforce squad legality, position, club limits, affordability and transfer availability at every simulated decision point.
- Model the future transfer flexibility consumed by acting now. Where future transfers, price changes, chips or subsequent moves are not forecast reliably, disclose the limitation rather than inventing a path.
- Do not recommend a transfer solely to improve the bench or to chase a one-week fixture when the multi-Gameweek squad value is not positive.
- A transfer may still be justified by a clear longer-term role, minutes, availability or fixture change, but those effects must appear in the horizon forecasts/evidence rather than narrative intuition alone.

## 5. Ranking and explanation

For each shortlisted transfer, the explanation must answer:
1. What is the cumulative expected value versus HOLD over the full horizon?
2. How much of that value comes from the first Gameweek versus later Gameweeks?
3. Is the outgoing player's low immediate xP temporary, or does the horizon show a persistent decline?
4. What happens to the manager's starting XI and squad structure?
5. What transfer flexibility, hit or future opportunity cost is incurred?
6. How sensitive is the conclusion to forecast coverage and uncertainty?

The recommendation should state why HOLD is preferable when no candidate creates sufficient horizon-level value. It must not manufacture a transfer to use a free transfer.

## 6. CoVar and field-relative context

This policy does not activate CoVar. Until the separate joint-forecast validation and approval gates pass, conventional transfer ranking remains based on multi-Gameweek expected value and legal squad constraints. EO/field context remains separately labelled and cannot be blended into xP. Once CoVar is validated and approved, it may be evaluated as a separate portfolio-risk contribution; it must not be used to disguise a negative expected-value transfer.

## 7. Validation requirements before implementation is treated as complete

- Regression test: a player with higher immediate-week xP but lower five-Gameweek net squad value must not be selected over HOLD or a better horizon candidate.
- Regression test: an owned player with low immediate-week xP but higher cumulative horizon value must not be sold solely on the immediate-week comparison.
- Regression test: a transfer with a negative first-week delta but positive, sufficiently large horizon-level net value can be selected when all other constraints pass.
- Regression test: missing or incomplete horizon forecasts fail closed; no single-week fallback may determine the action.
- Regression test: horizon comparison uses the same Gameweeks and coverage for HOLD and TRANSFER, and subtracts the actual displaced starter's counterfactual contribution.
- Python/JavaScript parity and frozen-decision replay must include the horizon, per-Gameweek deltas, cumulative net value and exact source snapshot provenance.
- Historical/prospective decision evaluation must score the frozen horizon policy against HOLD over the same horizon, with overlapping decision windows and repeated manager/Gameweek observations handled explicitly.

**Important implementation boundary:** The existing engine is a one-Gameweek optimiser. This policy records the required target behavior; it does not claim that multi-Gameweek forecasts, optimisation, or validation are already implemented. Until implementation and tests pass, current one-Gameweek outputs must be labelled exploratory and must not be presented as satisfying this policy.


## 8. Team stacking and correlated scoring exposure

Team stacking is a required part of the multi-Gameweek squad/transfer evaluation. It is not inherently good or bad: it deliberately increases exposure to shared team and match outcomes. The engine must quantify both the potential upside and the downside rather than automatically penalising multiple players from one club.

### 8.1 Defensive stacks

Evaluate combinations such as two or more defenders from a club with a strong clean-sheet outlook, and combinations across clubs with different fixture profiles. Defenders (and a goalkeeper, if the manager's goalkeeper-transfer constraint permits the existing pairing to be evaluated) can share clean-sheet and defensive-result exposure. A clean sheet can benefit several selected defenders simultaneously; conceding can remove clean-sheet points from multiple players at once.

For each horizon Gameweek, report:
- Club clean-sheet probability/forecast source and fixture context, where available.
- The number of selected defenders exposed to that club's clean-sheet outcome.
- Expected points contributed by the defensive stack and its share of squad/starting-XI expected points.
- Shared downside if the clean sheet fails, and whether the remaining defensive picks diversify that exposure.

A multi-club defensive portfolio can diversify club-specific clean-sheet risk, but must be assessed against the actual fixtures and player-level minutes/role forecasts. Do not assume Arsenal or Brighton, or any club, is permanently a strong clean-sheet pick; evaluate the relevant horizon.

### 8.2 Attacking stacks

Evaluate multiple attackers from the same club as shared exposure to team goals and attacking match states. A high-scoring team can create multiple routes to returns across its attackers, but individual goals, assists, bonus and minutes are not perfectly shared. The engine must distinguish:
- Common team scoring environment and expected team goals.
- Player-specific expected minutes, role, goal involvement and assist involvement.
- Dependence between player outcomes conditional on the shared match state.
- Concentration of squad points in one club/fixture and the upside/downside associated with that concentration.

### 8.3 Portfolio-level treatment

Where a validated joint scenario forecast is available, evaluate each legal squad/transfer path using the same scenarios and probabilities. Preserve player-point covariance and team/match-state dependence; calculate the contribution of within-club and cross-club combinations to total portfolio variance and relevant upside/tail outcomes. Do not assume independence between players from the same team, and do not equate positive correlation with a reason to avoid the stack.

Before a validated joint forecast is available, use transparent descriptive exposure diagnostics only (e.g. counts, club concentration, common fixture exposure, and marginal expected-points contribution). Do not invent correlation coefficients, clean-sheet probabilities, joint probabilities or CoVar adjustments from marginal xP alone. This descriptive layer must not change conventional transfer ranking.

### 8.4 Transfer decision impact

Compare the incoming player's effect on the whole five-Gameweek squad portfolio, not just the incoming/outgoing pair. A transfer can be valuable because it:
- Adds exposure to a strong defensive or attacking team environment.
- Completes or strengthens a deliberate stack.
- Diversifies an excessive existing club/fixture concentration.
- Replaces an isolated player with a player whose shared team environment increases portfolio upside.

The report must show the resulting stack before and after the transfer, the affected Gameweeks, the expected-points contribution, and—only when validated joint scenarios exist—the change in portfolio variance/dependence and upside/downside distribution.

Team stacking is therefore an explicit portfolio dimension alongside multi-Gameweek EV, field/EO context, squad legality and transfer flexibility. It remains distinct from CoVar validation: descriptive stacking analysis can be implemented now, but probabilistic dependence adjustments remain gated by joint-forecast validation and approval.


## 9. Engineering prototype status — 2026-11-22

A first isolated evaluator prototype now exists at `scripts/multi_gameweek_transfer_evaluator.py`, with focused tests at `tests/test_multi_gameweek_transfer_evaluator.py`. It:
- Requires at least five consecutive, explicit Gameweek forecast panels and complete forecasts for all current squad players plus the incoming player.
- Compares a fixed-XI HOLD path with a position-legal transfer path, reports per-Gameweek deltas and cumulative horizon value, and subtracts a hit once where applicable.
- Reports descriptive same-club defensive and attacking stacks by Gameweek, without fabricating clean-sheet probabilities, correlations or CoVar.
- Fails closed on incomplete/non-consecutive horizons.

This is an **isolated exploratory prototype**, not yet wired into `personal_squad_engine.py`, the provider forecast adapter, M4 delivery, or the live recommendation workflow. It does not yet optimize future lineups/captaincy, model transfer sequences or future transfer flexibility, or estimate joint outcome distributions. The existing one-Gameweek live recommendation behavior therefore remains unchanged and does not satisfy this policy. Integration is blocked until an approved provider supplies genuine point-in-time forecasts for each future Gameweek (or an explicitly validated multi-Gameweek forecast source is available). The prototype's tests have been added but have not yet been observed passing in CI.


### Prototype verification update — 2026-11-22 08:27 UTC

The PR #74 branch CI completed successfully on commit `11316ab252d76907e3f1326acb7a2c60ffa4d00f`: **863 Python engineering tests and 3 subtests passed**, alongside the JavaScript recommendation contract tests and canonical Python feature-core tests. The new evaluator tests are included in that run. This verifies the isolated prototype and its regression tests; it does not establish live multi-Gameweek provider coverage or integration into the production recommendation path.

[CI run 45002894747](https://github.com/uasir/CTA-FPL-Model/actions/runs/45002894747)
