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

**Still outstanding:** run the manual selection workflow for the next prospective Gameweek; inspect and freeze the resulting panel; capture the first complete pre-deadline manager-state wave and forecasts/decisions for hold, conventional and CTA-informed; validate the archive; then score actual outcomes. No manager cohort has yet been selected.
