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
- Reconstructing the deadline XI and bench by reversing official `automatic_subs` pairs produced **99.1% exact substitution-pair agreement** with forward absent-starter order. A reverse-order variant was worse at 98.6%, so the existing forward default remains. The remaining nine mismatches are concentrated in GW1, GW4, GW6 and GW8; both algorithms still reproduce all 1,000 team scores exactly.
- The audit is scoring-engine validation only. The rank-conditioned current-top-1,000 sample is not a representative manager panel and is not evidence of recommendation or strategy value.
- Private archive validator is implemented and its contract tests pass. It checks pre-deadline timestamps, stable manager cohort, legal squad/lineup structure, state/forecast hashes, policy coverage, two-set half-season chip inventory and transfer-hit arithmetic.
- No stable manager decision panel has yet been archived. No strategy-value or rank-gain claim is made.

## Current gates

1. Finish the autosub algorithm comparison and validate all official score/substitution mechanics.
2. Complete the 2PM position ablation; inspect fold stability, forecast errors and ranking metrics before deciding whether the feature is useful.
3. Continue independent ABC evaluation and improve historical source coverage without blending it into 2PM.
4. Assemble a fixed, private pre-deadline manager panel with frozen conventional, CTA-informed and hold decisions.
5. Run paired one-step and then sequential policy replays on identical feasible starting states.

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
