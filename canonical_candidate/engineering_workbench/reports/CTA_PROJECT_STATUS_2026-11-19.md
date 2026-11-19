# CTA-FPL project status — 2026-11-19

## Governing objective

Improve FPL decisions, squad optimization and competitive outcomes. Point prediction remains important but is not the sole evaluation target. Forecast quality, ranking quality and downstream decision value remain separate scorecards.

## Independent model tracks

### Conventional 2PM Transformer

- Standalone conventional-FPL model; no CTA A/B/C features enter this track.
- A time-safe expanding calibration diagnostic on the matched GW4–GW7 cohort (2,647 player-gameweeks) reduced retrospective MAE from 1.6340 to 1.3226 and RMSE from 2.2754 to 2.1665. EVMax remained stronger on this cohort (MAE 1.1344, RMSE 2.1084).
- The diagnostic is archived privately and is not a promotion result: source forecasts are retrospective reconstructions, the cohort is short and restricted to EVMax coverage, and clustered uncertainty intervals are not included.
- A controlled base-versus-position ablation is running on identical expanding-season folds. The base arm has completed; the position-aware arm is training. The comparison uses exact player-gameweek matching and runner-local player-level predictions.
- Position features are retrospective source fields; point-in-time position vintage is not verified.

### Independent CTA A/B/C predictor

- A/B/C remains a separate contextual predictor, independent of the 2PM Transformer.
- The current Wyscout historical panel is one season (2017/18), identity-limited and survivorship-biased; provider source vintages are retrospective.
- Unsupported receiver identity, xG, pressure and role evidence remains missing, not zero-filled.
- No ABC model or CTA feature layer is promoted. Broader season coverage and prospective point-in-time evidence remain required.

## Decision replay and policy evaluation

- Deterministic one-gameweek replay engine implemented: formation-aware automatic substitutions, captain/vice fallback, Triple Captain, Bench Boost and exact transfer-hit accounting.
- Official-history audit on 100 sampled managers across GW1–GW10: **1,000/1,000 valid records matched official gross and net team scores exactly** (zero mean absolute net-score difference).
- Reconstructing the deadline XI and bench by reversing official `automatic_subs` pairs raised exact automatic-substitution pair agreement to **99.1%** on the same sample. Remaining mismatches are being investigated with forward-versus-reverse absent-starter ordering variants.
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