# M3.4 — External Benchmark Decision Evaluation Protocol

**Status:** Protocol specification; no provider or recommendation is promoted by this document.  
**Scope:** M3 only. M2 continues independently. M4 field-relative/EO intelligence and M5 release remain out of scope.

## 1. Evaluation objective

Evaluate whether a frozen, deadline-eligible external forecast snapshot produces useful conventional personal-squad decisions for the manager state available at that deadline. Evaluate the complete decision, not only the incoming player's forecast.

The initial deliverable remains exactly one product: a conventional, squad-specific recommendation. CTA/ABC/2PM outputs, squad-independent rankings, provider consensus, EO/CoVar optimisation and public release are excluded until their own gates are met.

## 2. Unit of evaluation and cohort construction

The primary unit is a manager-deadline decision record:
- one manager/team ID and target gameweek;
- one immutable 15-player squad snapshot, bank, free transfers, purchase/selling prices and strategy inputs as known before the deadline;
- one provider, product, variant and immutable forecast snapshot;
- one decision timestamp strictly before the official deadline;
- one deterministic recommendation output and its complete provenance.

A decision cohort is eligible only when every required input can be shown to have existed before that gameweek's deadline. Retrospectively collected current prices, later provider revisions, post-deadline forecasts, final lineups and realised points must never enter the decision input.

Keep provider/variant cohorts separate. Never average providers or fill one provider's missing forecasts with another provider's values. Publish coverage and exclusions alongside every score.

## 3. Required archived evidence

For each evaluated deadline, retain and hash:
1. raw provider response, provider identity/variant, disclosed generation time, capture time and source URL;
2. raw official FPL metadata used at that time, including element IDs, positions, teams and prices;
3. manager squad state, bank, free transfers, purchase prices and their source/provenance;
4. official deadline and the decision as-of timestamp;
5. canonical decision input and complete output, including software commit and contract version;
6. post-deadline official FPL event data needed to calculate realised points and autosubs.

If an exact historical manager squad, bank, free-transfer count or purchase/selling-price state cannot be reconstructed from timestamp-valid evidence, that manager-deadline is not eligible for the primary personal-squad backtest. It may be retained in a clearly labelled diagnostic cohort, never silently repaired with current values.

A single live GW11 capture is an operational integration test, not a historical evaluation cohort.

## 4. Decision comparators

For every eligible manager-deadline, calculate at least:

- **Recommended action:** the frozen engine's single chosen action and resulting legal squad plan.
- **Hold baseline:** the same starting squad, no transfer, same deadline and scoring rules; optimise only the starting XI/bench/captain if that is explicitly part of the engine's decision policy. Do not give the hold baseline hindsight information.
- **Decision regret diagnostic:** compare the realised result with the best legal action discoverable after the deadline only as an explicitly hindsight-only upper bound. It is not a deployable benchmark and must not be used to claim predictive skill.

If additional conventional external decision systems are introduced later, each must have its own frozen input/output and provider-specific cohort. Do not create an undocumented consensus baseline.

## 5. Outcome calculation

Use official FPL gameweek scoring and the actual realised player points for the target gameweek. Reproduce the submitted decision's formation, starting XI, captain, vice-captain, bench order, reserve goalkeeper, automatic substitutions and captaincy fallback under the official rules.

For each recommendation, report:
- realised squad points after official substitutions and captain multipliers;
- transfer cost/hit points, if any, separately and net of squad points;
- realised net points delta versus the hold baseline;
- transfer outcome: incoming and outgoing player realised points, with the squad-level delta remaining the primary metric;
- whether the recommendation was legal and executable using the archived manager state.

Do not score a transfer by simply subtracting the outgoing player's points from the incoming player's points: the outgoing player may be on the bench, the incoming player may alter formation/substitutions, and captaincy/bench effects matter.

## 6. Forecast diagnostics (separate from decision outcomes)

At player-GW grain, score each provider only on the exact matched player-GW rows in its own eligible snapshots. Report:
- matched row count and player coverage;
- MAE and RMSE for xP;
- rank correlation (with tie handling stated);
- calibration diagnostics only where the provider's output semantics support them;
- missingness and exclusions by reason.

Do not interpret xP MAE as proof of transfer-decision value. A provider may rank players well but still produce poor manager-specific actions due to price, squad composition, constraints or captaincy.

## 7. Aggregation and uncertainty

Show per-gameweek results and pooled results. Keep all decisions from the same gameweek grouped when calculating uncertainty; player rows within a gameweek are not independent decision samples.

For paired recommendation-versus-hold comparisons, report:
- number of eligible manager-deadlines and number of distinct gameweeks;
- mean and median net-points delta;
- distribution and win/tie/loss counts;
- a gameweek-clustered bootstrap confidence interval, resampling gameweeks rather than individual players.

Do not declare superiority from one deadline, one gameweek, a small unclustered sample or a confidence interval that includes zero. Pre-register any minimum sample size, material-effect threshold and promotion rule before looking at comparative results; until that rule is approved and met, status remains **NOT VALIDATED**.

## 8. Determinism and leakage tests

The evaluation harness must reject:
- provider generation/capture at or after deadline;
- decision timestamps at or after deadline;
- missing generation time where the contract marks the snapshot diagnostic-only;
- source-hash mismatch or missing raw source archive;
- duplicate player-GW rows, unmapped player IDs or ambiguous forecast grain;
- manager-state rows that do not reconcile to 15 unique legal players;
- retrospective or post-deadline metadata in decision inputs;
- incomplete realised-points coverage for a scored squad;
- a recommendation output whose transfer and post-transfer 15-player plan disagree.

Identical frozen inputs, software commit and configuration must reproduce an identical decision payload (excluding explicitly non-deterministic execution metadata). Store the input and output hashes.

## 9. Promotion gates

No provider or recommendation policy is promoted until all of the following are evidenced:
1. repeatable, deadline-eligible archived captures across multiple gameweeks;
2. exact player identity and metadata joins with traceable raw hashes;
3. complete manager-state evidence for the evaluated personal-squad cohort;
4. deterministic replay and FPL-legal post-action plans;
5. official realised-points calculation independently checked against FPL scoring rules;
6. paired recommendation-versus-hold results with gameweek-clustered uncertainty;
7. provider-specific coverage, forecast diagnostics and decision outcomes disclosed together;
8. a pre-registered minimum sample and material-effect rule met;
9. all limitations and exclusions preserved in the decision output.

Software tests establish implementation behaviour, not forecast accuracy, decision value or rank improvement. A provider's website visibility, a single positive GW delta or an isolated xP metric is not a promotion criterion.

## 10. Current evidence status (2026-11-20)

- One successful live GW11 FPL Cat capture and manager-backed execution exists.
- The manager context used reconstructed purchase prices because the GW10 picks response did not expose purchase_price fields.
- The live run is useful for integration and provenance checks, but it is not a multi-gameweek backtest.
- Historical pre-deadline FPL Cat snapshots and exact historical manager states have not yet been established as a complete cohort.
- Therefore provider decision accuracy, recommendation value and release eligibility remain **NOT VALIDATED**.

## 11. Next implementation task

Implement a fail-closed evaluation input contract and deterministic scoring harness against synthetic fixtures first. The harness must encode the rules above without pretending synthetic fixtures are historical evidence. Only after its tests pass should archived real gameweeks be admitted, one at a time, with source and eligibility audits.


## Manager strategy constraints — fixed XI and budget bench

The personal-squad decision engine must represent the manager's actual operating policy, not assume a routinely rotated 15-player squad.

- The manager supplies the intended starting XI separately from the 15-player squad.
- The starting XI is held fixed across a recommendation. A transfer of a starter replaces that starter; a transfer of a bench player may displace only the weakest starter in the same position, and only when the incoming forecast improves the starting XI.
- A bench-to-bench points upgrade is not a sufficient reason to recommend a transfer.
- Goalkeeper transfers are excluded. The designated starting goalkeeper is preserved in the post-transfer XI; the reserve goalkeeper is emergency cover, not a rotation option.
- The three outfield substitutes are treated as budget emergency cover. Bench order remains relevant for automatic substitutions, not routine rotation.
- The workflow captures the manager-confirmed starting XI as a separate input. The lineup must contain 11 unique players from the confirmed 15-player squad and must pass the normal formation/position checks.

These are manager-specific constraints, not universal FPL rules. They do not imply that a transfer is worthwhile merely because it can change the XI; affordability, legal squad construction, hit cost and positive starting-XI gain still apply.


## 10. Initial deterministic scorer contract (synthetic-only implementation)

The first scorer is implemented in `scripts/evaluate_external_benchmark_decisions.py`. It validates a frozen record before scoring and currently admits only `SYNTHETIC_TEST` records. `REAL_CANDIDATE` records fail closed until a separate historical-evidence admission process is implemented.

Required evidence archives are separately hashed for:
- provider forecast (including provider generation timestamp);
- pre-deadline official player metadata;
- pre-deadline manager state;
- post-deadline realised player points, captured only after the Gameweek is finalised.

The frozen decision is independently SHA-256 sealed. The contract checks deadline ordering, raw archive hashes, full 15-player squad composition, team limits, prices, legal formation, captain/vice, reserve goalkeeper, transfer legality, exact post-transfer roster, fixed starting-XI replacement constraints, and realised-points coverage. A transfer comparison requires realised rows for the 15 original players plus the incoming player (16 rows), so the outgoing player's hold-baseline score is not lost.

The scorer uses official FPL per-player `total_points` as its realised points input; it does not independently reconstruct goals, assists, clean sheets, bonus points or other player-level scoring events. It applies the manager-level effects: ordered automatic substitutions, reserve-goalkeeper substitution, captain/vice fallback and the one-transfer four-point hit rule. It rejects chips in this initial implementation.

The appearance flag follows FPL's published definition: a player counts as having played if they appeared or received a yellow/red card. Therefore zero minutes alone is not enough to qualify a player as absent. Official rule references:
- https://fantasy.premierleague.com/help/faqs
- https://www.premierleague.com/en/news/2174899

The scoring implementation remains provisional until independently reconciled against completed official FPL manager Gameweek scores and substitution outcomes. Synthetic test success demonstrates deterministic software behaviour only; it is not evidence of historical decision value or release eligibility.

The transfer validator also enforces the manager strategy’s no-goalkeeper-transfer rule, exact incoming/outgoing position match, three-per-club squad limit, one-transfer free-transfer/hit treatment, and affordability using captured bank plus FPL half-profit selling-price rounding. The output retains the frozen decision hash, evaluation-input hash, source archive IDs/hashes, software commit and transfer financials.

For a transfer comparison, the realised-points cohort must contain all 15 original squad players plus the incoming player. This is necessary to score both the recommendation and the no-transfer hold baseline against the same Gameweek. The outgoing player is retained in that comparison even though he is absent from the post-transfer squad.

The initial implementation rejects malformed transfer IDs, invalid or incomplete source archives, unaffordable transfers, changed designated goalkeepers, incomplete realised rows, unsupported chips and all real-world candidate records pending admission.
Each record also binds the manager team ID, provider snapshot ID, decision-contract version, software commit, requested formation and personal risk profile. The risk profile is retained for provenance but is explicitly marked not applied by this initial engine.

The realised-points archive must carry a Gameweek finalisation timestamp and be captured after finalisation. A post-deadline but pre-finalisation points snapshot is not eligible for scoring. Player rows require official integer `total_points`, minutes, yellow cards and red cards; the appearance test follows the official FPL rule that a player counts as having played if they appeared or received a yellow/red card.

For a one-transfer action, the contract verifies the transfer hit (zero when a free transfer is available, otherwise four points), outgoing selling price using FPL half-profit rounding, incoming price and non-negative post-transfer bank. It returns the calculated financials alongside the paired score.

## 12. Independent official-manager reconciliation harness

The separate `scripts/reconcile_official_fpl_manager_result.py` module compares a local hold-plan score with the completed official manager picks response and official event-live points. It checks:
- the official manager event number and exact frozen starting XI, outfield bench order, reserve goalkeeper, captain and vice-captain;
- the official `automatic_subs` pairs against the locally simulated outfield and goalkeeper substitutions;
- the effective captain selected by the official player multipliers against local captain/vice fallback;
- the official multiplier-weighted gross score against the local gross score;
- the official gross score less `event_transfers_cost` against `entry_history.points`.

Chip gameweeks, unsupported multipliers, missing player live points, duplicate picks, inconsistent official event totals and lineup mismatches fail closed. The output is labelled `RECONCILED` only for that specific manager/gameweek score comparison and explicitly sets `historical_evidence_admitted: false`; it does not by itself admit a record into the historical cohort or validate forecast quality.

Synthetic contract tests are added in `tests/test_reconcile_official_fpl_manager_result.py`. These verify the comparison logic only. No completed official manager payload has yet been reconciled in this implementation step; the next acceptance action is to archive a completed, non-chip manager picks response and matching event-live payload, run the harness, and independently confirm the event history score. Until that is done, the scorer remains **PROVISIONAL / NOT INDEPENDENTLY RECONCILED**.
