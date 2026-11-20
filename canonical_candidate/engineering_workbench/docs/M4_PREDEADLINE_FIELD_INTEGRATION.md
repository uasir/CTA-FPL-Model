# M4-T6 — Pre-deadline field artifact admission and comparison

## End-to-end path
1. M4-T5 captures a stratified rank cohort and current manager picks before the target deadline.
2. The capture report and CSV are hashed and timestamped.
3. The pre-deadline adapter checks status, provisional evidence role, lock flag,
   both capture timestamps, sample metadata, schema, Gameweek and CSV SHA-256.
4. The M4 field-context contract binds the snapshot to the frozen candidate and
   requires both field capture and candidate decision before the same deadline.
5. Cohort/coverage/uncertainty diagnostics and a non-covariance portfolio baseline are added to the report. The baseline separates squad, starting XI and bench field exposures; reports top-player exposure, concentration shares/HHI and captain-share differential; and withholds sums/concentration when required inputs are missing.

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

Candidate input accepts the real M3 output envelope (using its `evaluation_candidate` object) or a direct M4 contract fixture. The adapter maps the original M3 squad snapshot and hold plan into the M4 contract, then verifies that the M3 proposed plan changes only the outgoing player's existing squad slot. Any unrelated XI, bench-order, goalkeeper, captain, vice-captain or formation change is rejected. This task does not mutate M3 outputs or the frozen candidate. Evidence remains provisional: sampled picks
can change before lock. The comparison is descriptive exposure context, not a
points/rank forecast or recommendation utility. EV and EO remain separate;
CoVar remains disabled; output is not release eligible.

## CoVar manager-level field portfolio extension

The capture now also writes `fpl_predeadline_manager_portfolios.json` from the same in-memory sampled manager-pick rows. The adapter verifies its SHA-256 manifest against the capture report, preserves sample expansion weights, captain/Triple Captain and rank-page stratum, then projects each manager onto the explicit modeled fixture players. Managers with no modeled player are retained as zero-point field slices. The separate Actions artifact is retained for 7 days and is not committed to the repository. Squad combinations can still be identifying, so treat it as restricted manager-level data.

This is a fixture-slice input bridge only. It does not yet provide full-Gameweek field scores, autosubs, complete chip effects or validated field-relative tail probabilities.
