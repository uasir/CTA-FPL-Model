# ABC–2PM matched comparison: research findings and next validation gates

## Status

The matched comparison completed in GitHub Actions workflow run #584 with status
`PASS_EXACT_MATCHED_PREDICTION_KEYS_RESEARCH_ONLY`.

- Season: 2017/18 only
- Matched test population: 1,261 player–Gameweeks, 91 players, 19 deadlines
- Five expanding whole-Gameweek test folds
- All five manifest, ABC prediction and 2PM prediction test-key hashes match
- Player-level prediction files and private partition keys remain runner-local; the published report is aggregate-only
- Historical source-vintage integrity: `NOT_VERIFIED_RETROSPECTIVE_SOURCE_VINTAGES`
- Promotion status: `RESEARCH_ONLY_DO_NOT_PROMOTE`

## Paired forecast findings

All values below use the exact same matched test observations.

| Forecast | MAE | RMSE |
|---|---:|---:|
| ABC calibrated | 2.5350 | 3.3844 |
| ABC raw | 2.4939 | 3.3804 |
| Shared FPL-history reference | 2.5475 | 3.3978 |
| 2PM affine-calibrated | 2.6023 | 3.4280 |
| 2PM raw | 2.4666 | 3.4668 |

Paired player-season cluster bootstrap, 2,000 replicates:

- ABC calibrated minus 2PM affine-calibrated MAE: **−0.0674**, 95% CI **[−0.1169, −0.0176]**.
- ABC calibrated minus 2PM affine-calibrated MSE: **−0.2967**, 95% CI **[−0.5592, −0.0308]**.
- ABC had lower absolute error on 55.7% of paired rows; 95% CI **[52.0%, 59.3%]**.
- ABC calibrated minus shared FPL-history reference MAE: **−0.0125**, 95% CI **[−0.0456, +0.0230]**. This does not establish incremental forecast value over the reference.
- 2PM affine-calibrated minus shared FPL-history reference MAE: **+0.0548**, 95% CI **[+0.0190, +0.0925]** on this restricted cohort.

Raw 2PM has lower MAE than its affine-calibrated output but higher RMSE. Calibration and tail-error behaviour must therefore remain separately visible; do not select a calibration method using MAE alone.

## Ranking findings

Deadline-local ranking metrics are descriptive over 19 deadlines from one season:

- ABC calibrated macro Spearman: **0.1683**.
- 2PM affine-calibrated macro Spearman: **0.0255**.
- Shared FPL-history reference macro Spearman: **0.1739**.
- Paired ABC-minus-2PM macro Spearman delta: **+0.1428**, deadline-bootstrap 95% CI **[+0.0716, +0.2190]**.
- Paired ABC-minus-FPL-history macro Spearman delta: **−0.0057**, deadline-bootstrap 95% CI **[−0.0702, +0.0614]**.

ABC's ranking comparison against 2PM is favourable within this cohort, but it does not demonstrate incremental ranking value over the FPL-history reference. The deadline bootstrap is descriptive only and cannot establish cross-season generalisation.

## Interpretation boundary

This is not a general model-selection result and does not justify production weighting, recommendation use, or promotion of ABC over 2PM.

Reasons:

1. The comparison is restricted to one historical season and 91 verified Wyscout–FPL identities, not a representative FPL player universe.
2. Wyscout source vintages were not archived as available at the historical FPL deadlines. Retrospective leakage cannot be ruled out.
3. ABC does not yet show a statistically resolved improvement over the shared FPL-history reference on either forecast MAE or macro ranking.
4. Model architecture, feature availability and calibration differ; the comparison is a controlled matched-test-population comparison, not proof of equal information sets.
5. No FPL+ABC or ABC+2PM hybrid has been tested.

## Required next M2 gates

1. **Point-in-time data audit:** identify whether additional ABC seasons and source snapshots can be obtained with defensible as-of-deadline provenance. If not, explicitly constrain ABC's research scope rather than treating retrospective data as live-valid.
2. **Cross-season cohort expansion:** build verified player identity and player–Gameweek panels for additional seasons; quantify coverage, attrition and selection bias by season and position.
3. **Repeat the matched contract across seasons:** retain whole-Gameweek expanding folds, exact fixture/points/minutes parity, disjoint fit/calibration/test partitions, identical test keys and aggregate-only outputs.
4. **Reassess calibration:** compare raw and calibrated forecasts with MAE, RMSE, signed error and tail-error metrics; fit calibration only on training-side calibration partitions.
5. **Incremental-value decision:** require ABC to demonstrate repeatable incremental value over the same FPL-history reference, not merely beat another candidate on a restricted cohort. Report forecast and ranking value separately.
6. **Only then consider hybrids:** evaluate FPL+ABC and/or ABC+2PM as separate ablations under the same leakage-safe, matched-cohort contract.

Until these gates are met, retain the result as research evidence only. Do not alter the live recommendation pipeline or move into the M3 decision engine on the basis of this experiment.
