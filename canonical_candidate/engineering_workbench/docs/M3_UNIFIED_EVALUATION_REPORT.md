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

## GitHub Actions workflow

`.github/workflows/build-m3-unified-evaluation-report.yml` provides the multi-Gameweek orchestration after it is available on the default branch. It accepts a manager ID and comma-separated successful run IDs from the existing **Reconcile official FPL manager Gameweeks** workflow. For every run it verifies the workflow name and successful conclusion, downloads the manager-specific reconciliation artifact, requires exactly one scored M3 event-result file, and validates the expected manager and real-event admission status before report generation.

Each source reconciliation run must have been supplied with its matching pre-deadline decision-evidence run ID; reconciliation-only or unadmitted events do not produce an eligible scored result. Use one completed Gameweek per source run. The report workflow rejects duplicate run IDs, missing/multiple result files, manager mismatches, non-successful source runs, and any unadmitted result.

The workflow file is added here but cannot be manually dispatched until the PR stack containing it reaches the repository's default branch. No PR is merged by this change.

## Workflow integration limitations

The existing capture workflow creates frozen pre-deadline decisions and replay evidence. The reconciliation workflow produces a scored result only when the corresponding pre-deadline decision artifact is supplied and independently admitted. No admitted real multi-Gameweek cohort is currently available. Therefore this orchestration is executable once the workflow is on the default branch and eligible event artifacts exist; synthetic fixtures remain software tests, not historical evidence.

The statistical bootstrap is an engineering screen assuming exchangeability of observed Gameweeks. It is not a block bootstrap, causal estimate, forecast validation, provider promotion, or release authorization. The next workflow step requires real multi-Gameweek evidence and review of temporal dependence and pre-registered thresholds.
