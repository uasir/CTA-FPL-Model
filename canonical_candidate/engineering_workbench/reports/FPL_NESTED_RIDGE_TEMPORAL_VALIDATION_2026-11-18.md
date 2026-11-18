# Nested rolling-origin FPL ridge validation — 2026-11-18

## Verified execution

- Full FPL ingestion + nested ridge run: https://github.com/uasir/CTA-FPL-Model/actions/runs/44354131782
- Artifact: https://github.com/uasir/CTA-FPL-Model/actions/runs/44354131782/artifacts/14450580753
- Artifact digest: `sha256:89370feea299167637734e02188cbddd17fe8533820a1ef0d266bac9a180cb4b`
- FPL season: 2026/27; target forecast: GW11.
- Official FPL ingestion: 672/672 player summaries, 380 fixtures, 6,562 player-fixture rows; zero missing summaries, orphan fixtures, minutes mismatches or points mismatches.

## Method

- Outer training window: GW1–GW6 (3,216 player-fixture rows; rows without prior gameweek history are excluded from model fitting).
- Outer validation window: GW7–GW10 (2,679 player-gameweek rows).
- Inner training window for alpha selection: GW1–GW4 (1,890 eligible fixture rows).
- Inner validation window: GW5–GW6 (1,334 fixture rows).
- Ridge alpha grid: `[0.1, 1, 3, 10, 30, 100, 300]`.
- Points and minutes alpha are selected separately using inner-validation MAE, with RMSE and then smaller alpha as tie-breakers.
- The final models are refit on the full outer training window and evaluated once on GW7–GW10.
- No feature selection or outer-holdout tuning is performed.

## Results

| Metric | Fixed alpha 10 | Nested-tuned alpha | Naive last-GW baseline |
|---|---:|---:|---:|
| Points MAE | 1.201603 | **1.199065** | **1.185511** |
| Points RMSE | 2.015697 | **2.009075** | 2.151323 |
| Minutes MAE | 15.375251 | 15.367280 | **11.098918** |
| Minutes RMSE | **23.717878** | 23.914775 | 24.512614 |

Selected alpha:
- Points: **300.0** (upper boundary of the tested grid).
- Minutes: **0.1**.

Nested tuning improved points MAE by 0.002538 and RMSE by 0.006622 against fixed alpha 10. However, points MAE still trails the naive last-five-GW baseline by 0.013554. Minutes MAE remains substantially worse than the naive last-GW baseline. The small points improvement is not sufficient to justify promotion.

## Decision

**DO NOT PROMOTE.** The model remains exploratory and disconnected from both recommendation engines. The source-vintage status is `NOT_VERIFIED`, so this is not a strict point-in-time backtest.

The GW7–GW10 outer holdout has now been inspected and is considered consumed. Do not expand the alpha grid and re-test on this same holdout. The points alpha selecting the upper grid boundary may justify a broader grid in a future experiment, but that experiment must use a new untouched validation window (e.g. later gameweeks) or another season.

The nested model is not used for expected points, minutes, market rankings, transfers, captaincy, or CoVar.
