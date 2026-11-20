# M3 Gameweek-cluster bootstrap evidence screen

**Status:** Engineering screen only. No forecast/provider promotion or recommendation release is authorized.

## Purpose and resampling unit

`evaluate_m3_statistical_acceptance.py` consumes the descriptive multi-Gameweek aggregation output. It does not admit records, rescore points, or combine provider cohorts. Every provider name/product/variant receives its own result.

The bootstrap resampling unit is the complete manager/Gameweek decision record. Each replicate draws N Gameweek records with replacement from the N observed records, preserving each paired recommendation-versus-hold outcome as one unit. Player rows are never treated as independent observations.

## Default screening thresholds

- At least **20 distinct eligible Gameweeks** in a provider cohort.
- At least **10 TRANSFER decisions** in that cohort. HOLD decisions are reported separately and do not count toward this minimum.
- **10,000 deterministic bootstrap replicates** and a two-sided **95% percentile interval** for the mean net points delta versus holding.
- The lower bootstrap confidence bound must be greater than the configured material-effect threshold (default **0.0 points per Gameweek**) to return `EVIDENCE_THRESHOLD_MET`.
- The bootstrap seed is derived from the aggregation input digest, provider identity, Gameweek set and contract version. Re-running the same input and settings produces the same interval.

If either sample minimum is missed, status is `INSUFFICIENT_EVIDENCE`. If minimums are met but the lower confidence bound does not exceed the material-effect threshold, status is `INCONCLUSIVE`. The positive-event rate is accompanied by a Wilson 95% interval.

## Interpretation and limitations

The resampling unit is a decision/Gameweek record, not a player row. This is a percentile bootstrap over observed Gameweeks; it assumes the observed Gameweeks are exchangeable. Temporal dependence, fixture clustering, rule changes and changing season conditions can still invalidate nominal coverage. It is not a block bootstrap or a causal estimate and does not establish forecast accuracy, rank improvement or future performance. The small-sample threshold is a minimum engineering screen, not a guarantee of statistical power.

HOLD recommendations have zero delta versus hold by construction. They are reported separately and do not count toward the transfer minimum.

Thresholds are defaults for software implementation and are not yet an approved promotion policy. They must be reviewed and frozen before comparative results are inspected. Even `EVIDENCE_THRESHOLD_MET` means only that this narrow statistical screen passed; `promotion_eligible` and `historical_performance_validated` remain false. Separate acceptance and human approval remain mandatory.

## CLI

```bash
python scripts/evaluate_m3_statistical_acceptance.py \
  m3-multigameweek-performance.json \
  --output m3-statistical-evidence-screen.json

# Optional settings, fixed before examining outcomes:
python scripts/evaluate_m3_statistical_acceptance.py aggregate.json \
  --min-events 20 --min-transfers 10 --material-effect-points 0.0 \
  --bootstrap-replicates 10000
```

No real multi-Gameweek decision cohort is currently admitted. The GW11 capture previously identified as manager-ID-corrupted is not eligible input. Synthetic tests exercise software behavior only.
