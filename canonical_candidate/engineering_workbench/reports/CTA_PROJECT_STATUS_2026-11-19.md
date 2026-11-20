# CTA-FPL project status — 2026-11-19

## Governing objective

Improve FPL decisions, squad optimization and competitive outcomes. Point prediction remains important but is not the sole evaluation target. Forecast quality, ranking quality and downstream decision value remain separate scorecards.

## Independent model tracks

### Conventional 2PM Transformer

- Standalone conventional-FPL model; no CTA A/B/C features enter this track.
- A time-safe expanding calibration diagnostic on the matched GW4–GW7 cohort (2,647 player-gameweeks) reduced retrospective MAE from 1.6340 to 1.3226 and RMSE from 2.2754 to 2.1665. EVMax remained stronger on this cohort (MAE 1.1344, RMSE 2.1084).
- The diagnostic is archived privately and is not a promotion result: source forecasts are retrospective reconstructions, the cohort is short and restricted to EVMax coverage, and clustered uncertainty intervals are not included.
- The first controlled base-versus-position run completed on 214,956 matched player-gameweeks. Preliminary point errors did not improve with position features. Its pooled top-K statistic was invalid across mixed deadlines and is excluded. A source chronology anomaly (gameweek labels extending to 47) was also detected; the panel builder now prefers explicit `GW`, records `GW`/`round` disagreements and enforces the 1–38 range. The experiment is being rerun with this corrected panel and deadline-local ranking metrics.
- Position features are retrospective source fields; point-in-time position vintage is not verified.

### Independent CTA A/B/C predictor

- A/B/C remains a separate contextual predictor, independent of the 2PM Transformer.
- The current Wyscout historical panel is one season (2017/18), identity-limited and survivorship-biased; provider source vintages are retrospective.
- Unsupported receiver identity, xG, pressure and role evidence remains missing, not zero-filled.
- No ABC model or CTA feature layer is promoted. Broader season coverage and prospective point-in-time evidence remain required.

## Decision replay and policy evaluation

- Deterministic one-gameweek replay engine implemented: formation-aware automatic substitutions, captain/vice fallback, Triple Captain, Bench Boost and exact transfer-hit accounting.
- Official-history audit on 100 sampled managers across GW1–GW10: **1,000/1,000 valid records matched official gross and net team scores exactly** (zero mean absolute net-score difference).
- The first chip-aware autosub-pair diagnostic was invalid because Bench Boost records were still included in the pair denominator. The audit loop was corrected in commit `6ce75b2770576c2116c0428eae9676c456282039`; corrected run [44644120726](https://github.com/uasir/CTA-FPL-Model/actions/runs/44644120726) excludes 96 Bench Boost records and compares 904 non-Bench-Boost records. Forward exact pair agreement is 99.67%; reverse exact pair agreement is 98.78%. Exact score parity remains 1,000/1,000 gross and net, with zero mean absolute net-score difference. Three non-Bench-Boost pair mismatches remain and should be inspected; they do not change the score-parity result.
- The audit is scoring-engine validation only. The rank-conditioned current-top-1,000 sample is not a representative manager panel and is not evidence of recommendation or strategy value.
- Private archive validator is implemented and its contract tests pass. It checks pre-deadline timestamps, stable manager cohort, legal squad/lineup structure, state/forecast hashes, policy coverage, two-set half-season chip inventory and transfer-hit arithmetic.
- The private archive now has a prospective manager-panel selection protocol and deterministic rank-stratified selector. The intended design is 100 managers (20 in each of five overall-rank bands), with a frozen cohort, recorded candidate-frame hash/seed, design weights and explicit attrition handling. The selector tests passed in private CI. No cohort has yet been selected or manager-state snapshots archived. No strategy-value or rank-gain claim is made.

## Current gates

1. Inspect the three remaining non-Bench-Boost autosub-pair mismatches; preserve exact score parity as the main replay validation gate.
2. Keep the base 2PM model as control; the position-feature ablation did not support promotion.
3. Continue independent ABC evaluation and improve historical source coverage without blending it into 2PM.
4. Run the private panel-selection workflow before the next prospective deadline, then capture complete pre-deadline states and all three frozen policies.
5. Validate the first panel wave, run paired one-step replay, and only then extend to sequential state transitions.

## Repository and workflow boundaries

- Public working branch: `work/parallel-evaluation-framework`.
- Separate 2PM research branch: `feat/four-layer-2pm-transformer-evaluation`.
- Private manager-state archive: `uasir/CTA-FPL-Private-Archive`.
- PR #47 remains open and unmerged. No branch has been merged.
- Raw manager IDs, picks, starting states and player-level counterfactuals remain private or runner-local; public outputs are aggregate only.

---

# Engineering continuation — 2026-11-20

## 2PM chronology correction

The 2019/20 source's post-lockdown rows use source labels 39–47 for FPL's rescheduled GW30+–GW38+ period. The panel builder now subtracts nine from labels 39–47 for 2019/20 only, preserves the raw-label audit count, compares explicit `GW` and `round` after normalization, and rejects any remaining out-of-range labels. The official Premier League described the rescheduled period as GW30+ through GW38+; an independent Vaastav-data processing example documents the 39–47 to 30–38 mapping.

- Panel-builder and normalization tests passed in the research CI.
- Corrected position-ablation run: [44636657035](https://github.com/uasir/CTA-FPL-Model/actions/runs/44636657035).
- The corrected panel build passed. The base 2PM training arm was still running at the time of this update; the position arm and paired comparison have not yet completed.
- The previous position-ablation results remain preliminary and must not be promoted.

## ABC evaluation correction

The independent ABC walk-forward evaluator now reports ranking quality within each FPL gameweek rather than pooling player scores across deadlines. It reports deadline-local Spearman and top-20 selection quality with macro-averages, while keeping point-error metrics separate. The one-season 2017/18 ABC evaluation is the current scope, so its gameweek grouping is appropriate; future multi-season evaluations must group by season and gameweek.

- ABC evaluator change and deadline-local ranking test passed in engineering CI.
- Latest confirmed engineering test suite: **429 passed, 1 skipped, 3 subtests passed** ([run 44637507662](https://github.com/uasir/CTA-FPL-Model/actions/runs/44637507662)).
- This is an evaluation correction, not evidence that ABC forecast or decision quality has improved.

## Replay audit diagnostic refinement

The chip-aware follow-up audit exposed Bench Boost records among the apparent autosub-pair mismatches. Because Bench Boost scores all 15 players, the official autosub pair mapping is not a scoring-relevant substitution decision for those records. The audit now excludes Bench Boost records from autosub-pair accuracy denominators while retaining them in gross/net team-score parity. A unit test covers this exclusion.

- Earlier chip-aware diagnostic run: [44636777670](https://github.com/uasir/CTA-FPL-Model/actions/runs/44636777670).
- Corrected audit rerun: [44637507732](https://github.com/uasir/CTA-FPL-Model/actions/runs/44637507732), pending at the time of this update.
- Non-Bench-Boost cases with the right substitution count and position-pair pattern but different incoming-to-outgoing assignments remain under investigation.

## Decision-value status

No strategy-value conclusion is available yet. Forecast accuracy and deadline-local ranking are being improved as supporting layers, but the core downstream test remains paired recommendations on identical private pre-deadline manager states: hold, conventional FPL and CTA-informed. The private archive validator exists; the stable manager panel and sequential state replay have not yet been completed.

## Cohort-level one-step policy replay — 2026-11-20

The one-step paired policy evaluator now supports multiple manager-deadline starting states at the same FPL deadline. It requires the same policy set for each unique `(deadline_id, starting_state_id)`, checks pre-deadline timestamps and common starting states, aggregates scores and paired deltas across states, and omits private starting-state IDs from the aggregate report. A synthetic two-manager test verifies the cohort aggregation and state-ID privacy.

- Engineering CI passed: **430 passed, 1 skipped, 3 subtests passed** ([run 44637806183](https://github.com/uasir/CTA-FPL-Model/actions/runs/44637806183)).
- This closes the evaluator's single-manager-per-deadline limitation, but does not create the manager archive or solve sequential squad/bank/free-transfer/chip state transitions.
- Statistical uncertainty and field-relative rank effects remain outside this deterministic one-step scorer.


## Final corrected 2PM position ablation — 2026-11-20

The corrected multi-season experiment completed on 214,956 matched player-gameweeks across 332 deadline-local gameweeks and nine seasons ([run 44636657035](https://github.com/uasir/CTA-FPL-Model/actions/runs/44636657035)). The position-feature arm did not demonstrate a useful improvement over the base 2PM model:

| Metric | Base | Position features |
|---|---:|---:|
| Macro deadline-local Spearman | 0.6932 | 0.6892 |
| Top-100 selected mean points | 3.5592 | 3.5621 |
| Calibrated MAE | 1.143429 | 1.143503 |
| Calibrated RMSE | 2.140013 | 2.141651 |

The paired top-100 difference was approximately +0.0030 points with 95% CI [−0.0153, +0.0225], so there is no clear improvement. Spearman declined slightly (paired difference about −0.00097; 95% CI [−0.00194, −0.00019]); calibrated errors were effectively unchanged or marginally worse. **Decision: retain the base 2PM model as the control; do not promote these position one-hot features.** This rejects this specific feature addition, not every possible use of position. Position-vintage point-in-time validity remains unverified, so this is retrospective evidence only.

## Corrected official-history replay audit — 2026-11-20

The corrected Bench Boost exclusion is now confirmed. Run [44644120726](https://github.com/uasir/CTA-FPL-Model/actions/runs/44644120726) passed:
- 1,000/1,000 exact gross team-score matches and 1,000/1,000 exact net team-score matches;
- zero mean absolute net-score difference;
- 96 Bench Boost autosub records excluded from scoring-relevant pair accuracy;
- 904 non-Bench-Boost autosub comparisons, with 99.67% forward exact pair agreement and 98.78% reverse exact pair agreement.

The audit is still a scoring-engine validation sample, conditioned on current rank/survivorship. It is not a representative manager panel or a strategy backtest. Three forward pair mismatches remain for diagnosis.

## Prospective manager-panel implementation — 2026-11-20

Private repository work:
- Added the manager-panel selection protocol, linked from the decision-replay archive protocol.
- Added deterministic selector script, which samples full pages from five fixed overall-rank bands, then selects a fixed quota per band. It records the seed, page frame, frame hash, rank, weights and excluded partial tail.
- Added selector tests and wired them into private CI. Run [44656783106](https://github.com/uasir/CTA-FPL-Private-Archive/actions/runs/44656783106) passed 11 tests. The selector weight field was then aligned with the archive validator contract; follow-up private CI run [44656852143](https://github.com/uasir/CTA-FPL-Private-Archive/actions/runs/44656852143) passed.
- Added manual workflow to create the private season manifest and candidate frame. It refuses to overwrite an existing panel.

**Panel selection is complete.** Private workflow [44657538350](https://github.com/uasir/CTA-FPL-Private-Archive/actions/runs/44657538350) selected the 2026-27 GW11 cohort at 2026-11-20 01:59:26 UTC, ahead of the official 2026-11-21 11:00 UTC deadline ([Premier League GW11 deadline confirmation](https://www.premierleague.com/en/news/4764714)). It contains 100 managers, 20 in each of five overall-rank bands, selected from a 2,500-manager candidate frame. The normalized design weights sum to 1; 16 entries in the final incomplete standings page were excluded from the sampling frame. The private manifest and candidate frame are committed in the private archive; no manager IDs or candidate rows are public.\n\n**Still outstanding:** capture the first complete pre-deadline manager-state wave for all 100 managers; freeze hold, conventional and CTA-informed forecasts/actions for each state; validate the archive; then score actual GW11 outcomes. The cohort is fixed and must not be replaced after outcomes.


## Sequential manager-state transition groundwork — 2026-11-20

A separate deterministic transition module is now implemented in scripts/transition_fpl_manager_state.py, with a contract in docs/FPL_SEQUENTIAL_STATE_TRANSITION_CONTRACT.md. It handles:
- one-for-one same-position transfers, squad composition, budget and club-limit checks;
- official selling-price arithmetic and next-deadline price refresh;
- normal free-transfer rollover and the five-transfer cap;
- Wildcard/Free Hit preservation of banked free transfers, permanent Wildcard changes and Free Hit squad/bank restoration;
- two-half chip inventory, including the GW19/GW20 consecutive Free Hit restriction.

Engineering CI passed **450 tests, 1 skipped, 3 subtests** in [run 44658968955](https://github.com/uasir/CTA-FPL-Model/actions/runs/44658968955). The state-transition primitive now persists lineups, restores the original lineup after Free Hit, and supports terminal Gameweeks without synthetic next deadlines.

The sequential architecture deliberately diverges policy states after a common initial state: hold, conventional and CTA-informed each carry forward their own squad, bank, free transfers and chip inventory. Reusing the actual manager's later squad for every policy would be one-step evaluation, not sequential policy evaluation.


## Fixed GW11 manager panel selected — 2026-11-20

The private prospective panel has now been selected successfully before GW11:
- 100 managers total; 20 from each of five overall-rank strata (1–100k, 100k–500k, 500k–1m, 1m–2m, 2m+).
- 2,500 candidate managers captured from 50 randomly selected full standings pages (10 pages per stratum).
- Candidate-frame SHA-256: a2d3fe5cdd6685bcbc5f6ac65443148c81b77072641168b8d8c81dd9bb60a1ab.
- Selection timestamp: 2026-11-20T01:59:26Z; target GW11 deadline: 2026-11-21T11:00:00Z.
- Normalized design weights sum to 1; the final 16-entry partial standings page is excluded and recorded.
- Private workflow [44657538350](https://github.com/uasir/CTA-FPL-Private-Archive/actions/runs/44657538350) completed successfully; private archive contract CI [44657522022](https://github.com/uasir/CTA-FPL-Private-Archive/actions/runs/44657522022) passed 11 tests.

The fixed cohort is selected, but the first pre-deadline state wave is not yet captured. Next gate is to capture all 100 manager states before GW11 lock, then freeze three decisions (hold, conventional, CTA-informed) against each state. Do not backfill or replace missing managers after the deadline.


## GW11 private state capture — 2026-11-20

The fixed 100-manager cohort was selected before the GW11 deadline. State capture attempt 001 exposed a schema assumption: the public historical picks endpoint does not return purchase_price. The corrected attempt 002 reconstructs purchase prices from the latest permanent transfer-in cost, or for GW1 initial players from bootstrap now_cost minus cost_change_start; Free Hit transfer-ins are excluded. Each player record stores purchase-price provenance.

Private workflow [44658380753](https://github.com/uasir/CTA-FPL-Private-Archive/actions/runs/44658380753) captured 94 manager states before the deadline and validated every captured state against the private state contract. Six managers remain missing because they started in GW2 and at least one initial player price has no permanent transfer-in record. All six belong to the 2m+ rank stratum. They carry 24.69% of the original normalized design weight; 75.31% of the panel weight is represented by captured states. No replacements or guessed prices are allowed.

Additional diagnostics:
- 93 states use the GW10 permanent squad; one uses GW9 because GW10 was Free Hit.
- Free-transfer counts at the GW11 starting state: 25 managers with 1, 32 with 2, 17 with 3, 6 with 4, and 14 with 5.
- One state has a temporary over-three-club warning; it is preserved for review.
- The 94 states passed individual validation, but the full 100-manager wave is marked incomplete. Do not report an overall weighted policy result as representative until missingness is resolved or explicitly bounded.


## Sequential paired policy runner — 2026-11-20

A separate runner is now implemented in scripts/replay_fpl_policy_trajectories.py, with its contract in docs/FPL_SEQUENTIAL_POLICY_REPLAY_CONTRACT.md. It executes hold, conventional and CTA-informed policies from the same initial state, then carries each policy's own squad, bank, free transfers, chips and lineup forward independently.

The runner:
- verifies per-policy starting-state SHA-256 hashes and forecast/decision timestamps before each deadline;
- enforces Hold as a true no-op (no transfers, no chip, no lineup/captain/bench changes);
- applies transfers/chips through the state-transition engine and scores each Gameweek through the validated one-Gameweek scorer;
- supports a terminal final Gameweek without inventing a future deadline;
- produces paired cumulative net-point deltas against Hold;
- preserves original panel design weights and labels incomplete results CAPTURED_SUBSET_ONLY rather than renormalizing missing managers into a population claim.

The runner and terminal/lineup transition tests pass in [engineering CI run 44658968955](https://github.com/uasir/CTA-FPL-Model/actions/runs/44658968955): **450 passed, 1 skipped, 3 subtests**.

**Important boundary:** no real conventional or CTA-informed action bundles have been frozen or replayed yet. This is replay infrastructure, not evidence of decision value. Next is the action-generation/freeze layer, then consecutive official-history parity checks, followed by actual paired trajectories. Current GW11 state coverage is 94/100 with 24.69% of the original design weight missing, so any captured-subset result must be labelled accordingly.


## Independent ABC evaluation hardening — 2026-11-20

The ABC walk-forward evaluator now uses season-Gameweek as the deadline key throughout:
- Player-fixture rows aggregate to player-season-Gameweek, preventing same player IDs and Gameweek numbers from different seasons being collapsed.
- Ranking is computed within each season-Gameweek, then macro-averaged across deadlines.
- Expanding folds preserve chronological season-Gameweek boundaries.
- Paired error bootstrap clusters by season-player, not player ID alone.
- Feature coverage diagnostics report observed/missing training rows and coverage rates per feature and fold; the model's training-only median imputation plus missingness-indicator policy is explicit.
- Layer-level availability summaries distinguish declared ABC features from features actually observed in the source panel.
- The ABC-vs-2PM matching key includes normalized season. The current 2PM comparison explicitly restricts its validated overlap to 2017-18 rather than silently pooling or pretending to support multi-season 2PM training.

Engineering CI [run 44659599769](https://github.com/uasir/CTA-FPL-Model/actions/runs/44659599769) passed: **457 tests, 1 skipped, 3 subtests**.

This is evaluation and coverage hardening, not evidence that ABC improved. The repository currently contains empty provider identity crosswalk placeholders and no full Wyscout event archive or FPL player-fixture history. No numeric ABC-vs-2PM result has been generated from a complete source panel yet. A private workflow is now downloading pinned Wyscout 2017-18 and FPL source snapshots to produce a pending-only identity review queue; no player identity will be automatically promoted to verified.
