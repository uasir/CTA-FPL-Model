# M4 CoVar Strategic Gap Audit

**Status:** Synthetic contract, 2026/27 event scorer, deterministic portfolio aggregation and weighted explicit-field-portfolio comparison implemented; initial defensive-stack, opposing-player hedge and low-EO captaincy mechanics covered by tests; full-GW field data integration pending  
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

### G4 — Cohort-specific field comparison (Free Hit optional)

The pre-deadline pipeline currently documents a top-10,000 rank-stratified sample. It does not classify Free Hit users versus non-Free Hit users for CoVar evaluation.

**Default requirement:** regular-GW CoVar must work with the existing overall/rank-stratified field cohort and must not depend on chip-use classification.

**Optional extension:** when the user explicitly activates Free Hit and reliable chip-use cohort data are available, support Free Hit users, non-Free Hit users and the combined overall field. If chip-use classification is unavailable, disclose the limitation and use only the available, clearly labelled field benchmark.

### G5 — Objective and risk profile

The current gate measures evidence readiness, not whether a strategy suits a rank/risk objective.

**Required:** make the comparison objective explicit (e.g. upper-tail/rank upside, balanced relative score, or downside protection). Report outcomes rather than inventing a universal CoVar score. A user's selected risk profile may guide interpretation, but must not alter the underlying forecasts or field evidence.

## 4. Smallest useful prototype — proposed scope

Build a deterministic, synthetic one-fixture research prototype before attempting a full-season model. Regular-GW mode is the default. It should compare a small set of explicitly supplied portfolios, not optimize a full 15-player squad. Free Hit-specific behavior is out of scope for this first prototype and may be added later as an optional mode.

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
4. Calculate relative outcomes against explicitly supplied, anonymized field portfolios with positive weights summing to one. The synthetic scorer now implements this; real manager-portfolio ingestion and cohort construction remain pending.
5. Report the EV opportunity cost and changes in probability of beating the field.
6. Explain which scenarios create each portfolio's boom and bust.

**Prototype coverage added:** tests now demonstrate positive covariance in a same-team two-player stack, negative covariance contribution for an opposing-player pair in the supplied two-scenario fixture, and the expected-points cost of changing captain to a lower-EO player. The lower-EO test deliberately confirms that marginal EO alone does not produce a field-relative result; `field_comparison_status` remains `NOT_AVAILABLE_NO_EXPLICIT_FIELD_PORTFOLIO`. These are controlled mechanics tests, not evidence that a particular real-world stack or captain is optimal.

**Now implemented for synthetic research:** field portfolio rows can be explicitly labelled `portfolio_role: FIELD` with positive `field_weight` values summing to one. Candidate portfolios are compared with each field portfolio under the same scenarios; outputs include expected field points, candidate-minus-weighted-field expected points, probability of outscoring a randomly sampled field portfolio, relative-score quantiles and relative-score standard deviation. Field rows are treated as anonymized portfolio samples; do not include public manager identifiers or personal records. This does not estimate joint field composition from marginal EO.

**Still not implemented:** real field portfolio ingestion and cohort sampling, set-piece taker/target attribution, event-based BPS, and a robust multi-fixture/full-GW scenario space. The current scenario fixture's points are hand-supplied; event scoring is tested separately and must be run before portfolio aggregation when using event inputs. The current scorer does not infer a set-piece link merely because two players share a team.

### Required first test cases

- Same-team goalkeeper/defender stack: clean-sheet boom and conceded-goal bust.
- Same-team attacking stack: multi-goal upside and attacking blank downside.
- Opposing attacker versus own defender: show the hedge effect without assuming perfect negative correlation.
- Lower-EO captaincy: demonstrate the captain multiplier and field-relative effect.
- Same-team set-piece taker plus target: pending an explicit set-piece event/assist attribution schema; do not infer the link from team membership.
- Rejection case: a stack with lower EV than the alternative and no sufficient improvement in the declared relative-outcome objective.

### Explicit exclusions

- No live recommendations or transfer optimization.
- No assumption that the user is using Free Hit; regular-GW mode is the default unless chip activation is explicitly supplied.
- No production data inference from synthetic examples.
- No personal team/rank/bank/transfer state in squad-independent market rankings.
- No alteration to M3 EV, frozen decisions, legality or decision hashes.
- No alteration to conventional M5 recommendations.
- No CoVar production weight or activation.

## 5. M4-COVAR-P1 — Synthetic scenario input contract

**Status:** Implemented; CI verification is running for the event-scoring and portfolio-aggregation changes.

Created:
- `scripts/m4_covar_scenario_contract.py`
- `tests/test_m4_covar_scenario_contract.py`

The versioned v1.0.0 contract validates fixture identity and deadline timing, team/player identities, explicit player outcomes, team-score consistency, scenario probabilities, portfolio membership and captaincy. It accepts only `SYNTHETIC_FIXTURE_ONLY` inputs. It preserves negative player point totals where scoring deductions apply, and returns hard-coded `decision_weight = 0.0` and `production_eligible = false`.

This input contract is now paired with `scripts/m4_covar_scenario_scoring.py` and `tests/test_m4_covar_scenario_scoring.py`. The pipeline now has three isolated stages: (1) `m4_covar_scenario_contract.py` validates synthetic fixture, player, team, scenario and portfolio inputs; (2) `m4_covar_fpl_event_scoring.py` calculates 2026/27 FPL points from explicit position-specific match events; and (3) `m4_covar_scenario_scoring.py` applies captain multipliers and reports scenario totals, expected points, variance, standard deviation, weighted quantiles and a covariance-contribution reconciliation. The event scorer is explicitly bound to the 2026-27 season and covers appearance, position-weighted goals, assists, clean sheets, goalkeeper saves/penalty saves (including an outfield player explicitly marked as taking goalkeeping duties), defensive contributions, penalty misses, explicit bonus points, goals conceded, cards and own goals. Every scoring-stat input must be explicit; missing event data is rejected rather than silently treated as zero. Bonus points are supplied as scenario inputs because official BPS ranking and tie resolution require match-wide event statistics; BPS is not inferred. Player-level goals conceded are explicit so a player substituted before a later concession can retain clean-sheet points. The portfolio scorer defaults to `REGULAR_GW`; `FREE_HIT` is accepted only when explicitly selected. A baseline comparison is calculated only when a portfolio ID is explicitly supplied. It does not infer a field portfolio from marginal EO, and field comparison remains unavailable without explicit manager/benchmark portfolio inputs. Official scoring references: [Premier League FPL scoring rules](https://www.premierleague.com/en/news/2174909/fpl-basics-scoring), [2026/27 BPS changes](https://www.premierleague.com/en/news/4679946/) and [FPL Help/FAQs](https://fantasy.premierleague.com/help/faqs). Scenario-matched field-relative comparison with explicit manager portfolios is implemented in the full-Gameweek synthetic scorer. The private manager-pick bridge and full-Gameweek document builder now compose complete anonymized manager portfolios without using marginal EO to infer co-occurrence. Do not build a public/live-data workflow until the independent FPL rules audit, empirical representativeness and uncertainty tests, and synthetic scenario-generation gaps are closed.

The prototype should demonstrate mechanics and EV opportunity-cost reporting, not claim predictive validity. Predictive validation remains a later, independent task.

## 6. Safeguards

- Existing LiveFPL/rank-stratified EO remains the sole field EO estimator.
- Missing manager-level joint ownership remains unavailable; never reconstruct it from marginal EO.
- Historical covariance remains exploratory.
- Synthetic scenarios are labelled synthetic and cannot be used as live evidence.
- `decision_weight = 0`.
- `production_eligible = false`.
- No PR merge without explicit user approval.


**Manager-level field input bridge now implemented:** the existing pre-deadline rank-stratified capture builds a manager-ID-stripped 15-player sample in memory and exports it only when an explicit private local output path is supplied. The adapter verifies its capture-report SHA-256 manifest, enforces same-GW/deadline/as-of timing, preserves actual manager co-occurrence and captain/Triple Captain multipliers, normalizes existing sample weights, supports rank-page cohort filtering, and retains zero-player fixture slices. It uses actual sampled manager-pick rows rather than attempting to reconstruct joint ownership from marginal EO. Entry IDs and exact ranks are discarded; squad combinations may still be identifying, so the artifact is restricted. It is exported only to an explicitly chosen local path; the public Actions workflow never writes or uploads it.

**Still not implemented:** full-Gameweek manager portfolio scoring, empirical representativeness/uncertainty validation of the sample for relative-score tails, set-piece taker/target attribution, and event-based BPS.


## 7. 2026-11-22 — Historical covariance source-integrity hardening

The historical covariance builder now independently verifies that the realized player-Gameweek panel contains exactly the Gameweeks covered by the finality batch and dataset manifest. It fails closed on duplicate finality event IDs, duplicate player-Gameweek rows, panel rows outside the reconciled Gameweek set, missing reconciled Gameweeks, invalid player IDs, and non-finite or non-integer FPL total points. The manifest SHA-256 check remains mandatory.

This closes a source-set integrity gap; it does **not** establish point-in-time forecast validity, covariance stability, a calibrated forward joint distribution, manager-level field representativeness, or recommendation eligibility. The output remains retrospective and exploratory, with `decision_weight = 0` and `production_eligible = false`.

Validation:
- Full engineering CI: 847 tests and 3 subtests passed — [run 44994911593](https://github.com/uasir/CTA-FPL-Model/actions/runs/44994911593).
- Focused CoVar validation: 128 tests passed — [run 44994911531](https://github.com/uasir/CTA-FPL-Model/actions/runs/44994911531).
- Real official FPL replay: 10 completed Gameweeks passed, including 10/10 official team-score reconciliations — [run 44994911531](https://github.com/uasir/CTA-FPL-Model/actions/runs/44994911531).

The real replay baseline now includes actual goalkeeper and outfield autosubs. The next validation priority is field-sample representativeness and uncertainty for relative-score tails, followed by event-derived full-Gameweek scenario validation. Only normalized identity-field-stripped replay cases are retained in a 30-day Actions artifact; raw manager API payloads are not committed or uploaded.

## 8. 2026-11-22 — Official event-scoring reconciliation

A new audit consumes the official FPL per-fixture `explain` breakdown and
compares it with the local 2026/27 event scorer. Across GW1-GW10, all 6,562
player-fixture rows matched exactly; there were zero mismatches and zero
unmapped positive scoring identifiers. Both the official and locally
calculated totals summed to 9,145 points. GW11 was skipped because its official
data was not final-scored at capture time.

This validates the scorer's observed fixture-point arithmetic, including
official bonus as an input. It does not independently calculate BPS, predict
bonus, or establish forward forecast calibration. The sample did not contain
Double Gameweek fixture rows; synthetic DGW tests cover separate fixture
scoring and aggregate minutes above 120.

Validation:
- Focused CoVar + event-scoring + manager replay workflow: [run 44995259297](https://github.com/uasir/CTA-FPL-Model/actions/runs/44995259297).
- Full engineering CI: 852 tests and 3 subtests — [run 44995259271](https://github.com/uasir/CTA-FPL-Model/actions/runs/44995259271).
- Focused CoVar suite: 133 passed.

Next priority: move from per-player/per-fixture scoring validation to full
Gameweek portfolio scoring with actual field samples, then test sample
representativeness and relative-score tail stability. Official bonus remains
an input; a BPS forecast is still out of scope.

## 9. 2026-11-22 — Real autosub validation and aggregate field portfolio structure

### Official FPL replay evidence

The API adapter now reverses the official post-autosub pick positions using
`automatic_subs` pairs to reconstruct the submitted deadline XI and bench.
Final scoring multipliers remain attached to their players. This corrected the
earlier assumption that completed-GW pick positions were the original
deadline order.

- Private manager replay: GW1-GW10, **10/10 PASS**.
- Real autosubs in that replay: **3** — one outfield substitution in GW4,
  plus one goalkeeper and one outfield substitution in GW5.
- Final multipliers, player points, captaincy, official autosub pairs and
  `entry_history.points`: all reconciled, zero failures.
- Public Overall-league sample: 25 managers across five separated standings
  pages, **125/125 PASS** across GW6-GW10, zero capture failures.
- Public sample autosubs: **52** replays involving **68** incoming players;
  six captain fallbacks; 125/125 official team-point reconciliations.
- Six public records differed only in exact pair assignment. The incoming and
  outgoing player sets and final scoring multipliers matched; these are
  diagnostics, not scoring mismatches. No autosub player-set mismatch remained.

The public sample is a resolver stress-test, not a representative estimate of
the whole field or a pre-deadline field portfolio census. The private replay
and public sample are retrospective validation only.

### Aggregate-only predeadline portfolio structure

The existing rank-stratified predeadline capture now computes an aggregate
portfolio-structure summary from its in-memory manager-pick sample. The public
report contains weighted squad/XI/bench inclusion shares, captain/Triple
Captain shares, pairwise co-selection covariance/correlation and portfolio
overlap. It does not export individual manager portfolios, manager IDs, names
or exact ranks.

This summary is derived from the same manager-pick sample as the existing EO
estimator. It is not a second EO estimator: the existing rank-stratified EO
estimator remains the sole field EO source. Binary player co-selection
covariance is distinct from historical player-points covariance and does not
create a joint match-outcome distribution. The summary remains provisional,
not a global census, `decision_weight=0` and `production_eligible=false`.
The first live predeadline capture for the next target Gameweek is still
pending.

### Validation and next work

- Full engineering CI: **871 tests and 3 subtests passed** — [run 44998077270](https://github.com/uasir/CTA-FPL-Model/actions/runs/44998077270).
- Focused CoVar validation: **155 passed** — [run 44998077310](https://github.com/uasir/CTA-FPL-Model/actions/runs/44998077310).
- Official manager replay, public field replay and event-scoring audits: [run 44998077310](https://github.com/uasir/CTA-FPL-Model/actions/runs/44998077310).

Next: capture the first live predeadline portfolio-structure sample; quantify
its sampling uncertainty and rank-cohort representativeness; then connect
observed portfolio structure to scenario-matched full-Gameweek score
distributions. Event-derived scenario generation, set-piece attribution and
event-based BPS remain open. CoVar remains research-only.
