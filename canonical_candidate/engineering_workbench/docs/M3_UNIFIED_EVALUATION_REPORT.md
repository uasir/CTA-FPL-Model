# M3 unified multi-Gameweek evaluation report

**Status:** Engineering integration only. This report cannot validate historical performance, promote a provider, or authorize recommendation release.

## One-command pipeline

`build_m3_unified_evaluation_report.py` is the orchestration entry point. It accepts independently admitted and scored real event-result JSON files, then executes these existing stages in order:

1. Validate and aggregate event-level outcomes using `aggregate_m3_multigameweek_evaluations.py`.
2. Pass that exact in-memory aggregate to `evaluate_m3_statistical_acceptance.py`.
3. Emit one JSON document containing descriptive performance, provider-specific bootstrap evidence, the shared aggregate digest, and explicit non-promotion flags.

The orchestration layer does not admit records, repair missing evidence, calculate player points, or rescore events. Either stage failing causes the command to fail; no partial report is emitted.

## Determinism and provider isolation

Input records are canonically ordered by manager, target Gameweek, provider identity and evaluation-input hash before aggregation. Thus reordering file arguments does not change the aggregate digest, bootstrap seed or report. Provider name/product/variant cohorts remain separate through both stages.

The statistical screen uses the deterministic 10,000-replicate default Gameweek decision-record bootstrap and the preconfigured engineering thresholds. Overrides are possible on the CLI, but must be frozen before examining comparative outcomes.

## CLI

Run from `canonical_candidate/engineering_workbench`:

```bash
PYTHONPATH=scripts python scripts/build_m3_unified_evaluation_report.py \
  gw11-evaluation-result.json gw12-evaluation-result.json \
  --output m3-unified-evaluation-report.json

# Optional, pre-outcome settings:
PYTHONPATH=scripts python scripts/build_m3_unified_evaluation_report.py \
  gw11-evaluation-result.json gw12-evaluation-result.json \
  --min-events 20 --min-transfers 10 \
  --material-effect-points 0.0 --bootstrap-replicates 10000 \
  --output m3-unified-evaluation-report.json
```

The report includes:
- `descriptive_performance`: event counts, action mix, net deltas, cumulative value, hit costs and per-provider cohorts;
- `statistical_evidence`: per-provider Gameweek bootstrap intervals, sample thresholds and evidence status;
- `aggregation_input_sha256`: the same digest in both stages;
- `promotion_eligible=false`, `historical_performance_validated=false` and `release_eligible=false`.

## Workflow integration status

The existing `capture-predeadline-decision-evidence.yml` workflow captures and freezes a pre-deadline recommendation and replay. It does not produce post-deadline scored event records. No dedicated M3 multi-Gameweek scoring/aggregation workflow currently exists, and no admitted real multi-Gameweek cohort is available. Therefore this change provides the deterministic orchestration command and its tests, but deliberately does not wire an automatic GitHub Actions evaluation job to nonexistent real event artifacts.

The next workflow step requires a separately approved, auditable post-deadline event-scoring/admission artifact contract. Until then, only synthetic fixtures may exercise the software tests; they are not historical evidence.
