# M4-T4 — Field EO artifact ingestion and temporal admission

## Existing capture semantics

`.github/workflows/cta-fpl-eo-capture.yml` runs `capture_fpl_ranked_manager_picks.py`.
That capture freezes the rank-defined manager cohort before the target deadline,
waits until deadline plus lock grace, and only then fetches the sampled managers'
15 picks. The estimator's EO values therefore describe final post-lock picks.

The rank cohort timestamp and the EO-picks timestamp are distinct evidence times.
A pre-deadline cohort does **not** make post-lock EO values available pre-deadline.

## Adapter

`scripts/m4_field_artifact_adapter.py` reads the existing
`fpl_effective_ownership_sample.csv` and
`fpl_ranked_manager_sample_report.json` artifacts. It:

- verifies capture status and lock verification;
- verifies the rank cohort was captured before deadline;
- verifies picks were captured after the configured lock grace;
- validates the estimator CSV schema, Gameweek and unique player IDs;
- carries sample size, effective sample size, rank bounds and cohort metadata;
- hashes both the exact CSV bytes and capture report;
- normalizes EO rows without zero-filling unavailable values.

## Temporal safety boundary

Output is explicitly labelled `RETROSPECTIVE_POST_LOCK` and
`NOT_VALID_FOR_PREDEADLINE_DECISION`. It is not passed to
`validate_field_context` or `compare_frozen_candidate_to_field` as if it were
pre-deadline field knowledge. A later task must source a genuinely pre-deadline
field estimate (or a prior-GW baseline) before a decision-time field comparison
can be admitted.

## Run

```bash
PYTHONPATH=scripts python scripts/m4_field_artifact_adapter.py \
  --csv path/to/fpl_effective_ownership_sample.csv \
  --report path/to/fpl_ranked_manager_sample_report.json \
  --season 2026-27 \
  --source-url https://github.com/uasir/CTA-FPL-Model/actions/runs/RUN_ID \
  --output field-eo-normalized.json
```

This is a provenance/ingestion artifact only. It does not estimate EO, combine
EO with expected points, calculate CoVar, alter M3, or enable release.
