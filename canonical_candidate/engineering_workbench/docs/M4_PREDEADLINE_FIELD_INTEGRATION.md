# M4-T6 — Pre-deadline field artifact admission and comparison

## End-to-end path
1. M4-T5 captures a stratified rank cohort and current manager picks before the target deadline.
2. The capture report and CSV are hashed and timestamped.
3. The pre-deadline adapter checks status, provisional evidence role, lock flag,
   both capture timestamps, sample metadata, schema, Gameweek and CSV SHA-256.
4. The M4 field-context contract binds the snapshot to the frozen candidate and
   requires both field capture and candidate decision before the same deadline.
5. The candidate-field comparison emits HOLD and frozen candidate exposure views.

## Run
```bash
cd canonical_candidate/engineering_workbench
PYTHONPATH=scripts python scripts/m4_predeadline_field_comparison.py \
  --csv path/to/fpl_predeadline_effective_ownership.csv \
  --report path/to/fpl_predeadline_field_report.json \
  --candidate path/to/frozen_m3_candidate.json \
  --season 2026-27 \
  --source-url https://github.com/uasir/CTA-FPL-Model/actions/runs/RUN_ID \
  --output run_artifacts/m4_predeadline_comparison.json
```

Candidate JSON must use the M4 contract schema. This task does not mutate M3
outputs or the frozen candidate. Evidence remains provisional: sampled picks
can change before lock. The comparison is descriptive exposure context, not a
points/rank forecast or recommendation utility. EV and EO remain separate;
CoVar remains disabled; output is not release eligible.
