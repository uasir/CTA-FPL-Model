# M3 statistical evidence screen

**Status:** Engineering screen only. No forecast/provider promotion or recommendation release is authorized.

## Purpose

`evaluate_m3_statistical_acceptance.py` consumes the descriptive multi-Gameweek aggregation output. It does not admit records, rescore points, or combine provider cohorts. Every provider name/product/variant receives its own result.

## Default screening thresholds

- At least **20 distinct eligible Gameweeks** in a provider cohort.
- At least **10 TRANSFER decisions** in that cohort. HOLD decisions are reported separately and do not count toward this minimum.
- Two-sided **95% Student-t confidence interval** for the mean gameweek-level net points delta versus the hold baseline.
- The lower confidence bound must be greater than the configured material-effect threshold (default **0.0 points per Gameweek**) to return `EVIDENCE_THRESHOLD_MET`.

If either sample minimum is missed, status is `INSUFFICIENT_EVIDENCE`. If the minimums are met but the lower confidence bound does not exceed the material-effect threshold, status is `INCONCLUSIVE`. The positive-event rate is also accompanied by a Wilson 95% interval.

## Interpretation and limitations

The unit is a manager/Gameweek decision, not a player row. The Student-t interval currently treats Gameweek-level deltas as independent; serial dependence may make it too narrow. This is a provisional screening interval, not the gameweek-clustered bootstrap specified in the main M3 protocol. Do not use it to claim causality, forecast accuracy, rank improvement or future performance.

HOLD recommendations have zero delta versus hold by construction. They are reported separately and are not evidence of transfer value. The transfer minimum prevents a large number of HOLD decisions from satisfying the sample requirement without meaningful transfer exposure.

Thresholds are defaults for software implementation and are not yet an approved promotion policy. They must be reviewed and frozen before comparative results are inspected. Even `EVIDENCE_THRESHOLD_MET` means only that the narrow statistical screen passed; `promotion_eligible` and `historical_performance_validated` remain false. Separate acceptance and human approval remain mandatory.

## CLI

```bash
python scripts/evaluate_m3_statistical_acceptance.py \
  m3-multigameweek-performance.json \
  --output m3-statistical-evidence-screen.json

# Optional pre-registered overrides, set before examining outcomes:
python scripts/evaluate_m3_statistical_acceptance.py aggregate.json \
  --min-events 20 --min-transfers 10 --material-effect-points 0.0
```

No real multi-Gameweek decision cohort is currently admitted. The GW11 capture previously identified as manager-ID-corrupted is not eligible input. Synthetic tests exercise software behavior only.
