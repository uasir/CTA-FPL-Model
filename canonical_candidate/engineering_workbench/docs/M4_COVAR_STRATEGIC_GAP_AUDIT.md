# M4 CoVar Strategic Gap Audit

**Status:** Audit complete; prototype not yet implemented  
**Branch:** `feat/m4-field-portfolio-intelligence`  
**Scope:** Map the article-derived Field CoVar methodology to existing M4 components.  
**Production status:** Research only; CoVar decision weight remains 0 and production eligibility remains false.

## 1. Executive finding

M4 already provides useful field-exposure infrastructure and exploratory historical covariance diagnostics. It does not yet implement strategic Field CoVar.

The current system can describe:
- player-level historical points covariance from complete gameweek panels;
- sample-based ownership, starting, captain, Triple Captain and scoring exposure;
- a user's frozen squad exposure relative to one pre-deadline field sample;
- basic portfolio concentration and exposure gaps.

It cannot yet estimate whether a proposed stack or contrarian captain improves the probability of outperforming a defined field cohort after accounting for expected-points opportunity cost.

## 2. Existing components and permitted use

| Component | What it currently provides | Permitted CoVar use | Missing capability |
|---|---|---|---|
| `estimate_fpl_covariance.py` | Historical player-points covariance/correlation, complete-case panel, off-diagonal shrinkage and descriptive summaries | Exploratory historical dependence diagnostic | No fixture/team event structure, field portfolios, pre-deadline point-in-time guarantee or forward simulation |
| `build_onside_fpl_covariance.py` | Exploratory covariance from Onside actual-points ledger and rolling correlation stability | Independent historical diagnostic, with stated source limitations | No verified point-in-time forecast panel, manager portfolios or objective-specific utility |
| `estimate_fpl_effective_ownership.py` | One-GW manager-pick sample; ownership, starting, captain, Triple Captain, EO/scoring exposure, rank stratification and uncertainty intervals | Sole existing field exposure estimator; reuse its source and definitions | Aggregates manager picks into player exposure outputs; does not export a manager-by-player joint portfolio panel for CoVar |
| `m4_predeadline_field_comparison.py` | Binds provisional pre-deadline field snapshot to frozen M3 candidate; reports diagnostics, exposure baseline and candidate comparison | Decision-time field exposure context | No joint scenario scoring or comparison of strategy portfolios' relative-score distributions |
| `m4_candidate_field_comparison.py` | HOLD/TRANSFER player exposure differences, preserving the outgoing player's existing slot | Explain how a transfer changes field exposure | Not a portfolio optimizer and does not evaluate CoVar utility |
| `m4_portfolio_exposure_baseline.py` | Squad/XI/bench exposure sums, concentration, HHI, effective contributors and captain-share differential | Baseline portfolio concentration description | Does not infer covariance, joint field ownership or expected relative points |
| `m4_covar_eligibility_gate.py` | Fail-closed evidence gate and descriptive portfolio-variance sensitivity under off-diagonal shrinkage | Keep research artifacts blocked and document sensitivity | No joint-event calibration, manager-level field composition, strategy EV trade-off or objective-specific out-of-sample utility |

## 3. Key design gaps

### G1 — Manager-level field portfolio composition

The EO estimator processes complete manager pick sets and validates 15 unique picks and one captain, but its current output is player-level aggregate exposure. It does not preserve a reusable manager-by-player matrix or cohort-level joint ownership combinations.

**Required:** an optional privacy-safe aggregate representation of joint portfolio composition, retaining manager-level linkage only within the controlled analysis artifact. Do not publish manager IDs or personal manager records in public outputs. If only marginal EO is available, explicitly mark field portfolio dependence as unavailable rather than infer it.

### G2 — Forward-looking joint football events

Historical points covariance does not explain why players move together and cannot reliably forecast a specific fixture stack.

**Required:** a deterministic scenario contract that represents shared team/match outcomes and maps event allocations, player minutes and FPL scoring to player points. Historical covariance can remain a diagnostic, not the primary forward model.

### G3 — Strategy comparison and EV opportunity cost

Current M4 compares a frozen candidate's exposure to the field; it does not compare alternative CoVar portfolio constructions against a conventional EV-oriented portfolio.

**Required:** compare like-for-like legal portfolios under identical budgets and point-in-time inputs. Keep projected points, field EO and simulated outcome distributions as separate quantities. Report EV difference and changes in probability of beating the chosen field cohort.

### G4 — Cohort-specific field comparison

The pre-deadline pipeline currently documents a top-10,000 rank-stratified sample. It does not classify Free Hit users versus non-Free Hit users for CoVar evaluation.

**Required:** support a cohort identifier and sample metadata in the scenario comparison contract. Free Hit/non-Free Hit segmentation is optional and must be withheld when reliable chip-use cohort data are unavailable.

### G5 — Objective and risk profile

The current gate measures evidence readiness, not whether a strategy suits a rank/risk objective.

**Required:** make the comparison objective explicit (e.g. upper-tail/rank upside, balanced relative score, or downside protection). Report outcomes rather than inventing a universal CoVar score. A user's selected risk profile may guide interpretation, but must not alter the underlying forecasts or field evidence.

## 4. Smallest useful prototype — proposed scope

Build a deterministic, synthetic one-fixture research prototype before attempting a full-season model. It should compare a small set of explicitly supplied portfolios, not optimize a full 15-player squad.

### Inputs

- Versioned fixture and deadline identity.
- Player IDs, teams, positions, roles, expected points and minutes assumptions.
- Explicit field ownership/EO/captain exposure snapshot, with provenance and cohort.
- Explicit scenario rows with scenario probability, team goals/conceded/clean-sheet state, minutes and goal/assist/set-piece allocation.
- Candidate portfolio membership and captaincy multipliers.
- A conventional EV-oriented comparison portfolio and one or more CoVar alternatives.

All probabilities and player assumptions must be supplied as fixture inputs; the prototype must not fabricate or infer missing forecasts.

### Calculations

1. Validate that scenario probabilities are finite, non-negative and sum to one.
2. Convert each scenario's player events to FPL points using the declared scoring rules.
3. Calculate portfolio points, expected points, variance and lower/upper quantiles.
4. Calculate relative outcomes against an explicitly supplied field benchmark or sampled manager portfolios.
5. Report the EV opportunity cost and changes in probability of beating the field.
6. Explain which scenarios create each portfolio's boom and bust.

### Required first test cases

- Same-team goalkeeper/defender stack: clean-sheet boom and conceded-goal bust.
- Same-team attacking stack: multi-goal upside and attacking blank downside.
- Opposing attacker versus own defender: show the hedge effect without assuming perfect negative correlation.
- Lower-EO captaincy: demonstrate the captain multiplier and field-relative effect.
- Same-team set-piece taker plus target: score only when the supplied event allocation supports the combination.
- Rejection case: a stack with lower EV than the alternative and no sufficient improvement in the declared relative-outcome objective.

### Explicit exclusions

- No live recommendations or transfer optimization.
- No production data inference from synthetic examples.
- No personal team/rank/bank/transfer state in squad-independent market rankings.
- No alteration to M3 EV, frozen decisions, legality or decision hashes.
- No alteration to conventional M5 recommendations.
- No CoVar production weight or activation.

## 5. Recommended next implementation task

**M4-COVAR-P1 — Joint-event prototype contract and deterministic fixture tests.**

First create the versioned input/output contract and hand-authored deterministic scenarios. Only after the contract tests pass should a separate adapter be designed for real point-in-time forecasts and field samples.

The first prototype should demonstrate the mechanics and opportunity-cost reporting, not claim predictive validity. Predictive validation remains a later, independent task.

## 6. Safeguards

- Existing LiveFPL/rank-stratified EO remains the sole field EO estimator.
- Missing manager-level joint ownership remains unavailable; never reconstruct it from marginal EO.
- Historical covariance remains exploratory.
- Synthetic scenarios are labelled synthetic and cannot be used as live evidence.
- `decision_weight = 0`.
- `production_eligible = false`.
- No PR merge without explicit user approval.
