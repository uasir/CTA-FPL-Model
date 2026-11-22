# M4-T4 — Rank-cohort, coverage and uncertainty diagnostics

`scripts/m4_field_context_diagnostics.py` consumes only a validated M4 field-context
binding. It reports snapshot timing, cohort and rank bounds, manager/effective
sample sizes, field-player row count, missing-player coverage, per-metric
availability/null counts and ranges, and effective-ownership 95% interval widths.

Intervals are preserved as uncertainty diagnostics; they are not used to
reweight EO, create a player score, or convert exposure into expected points.
Incomplete or inverted effective-ownership intervals are rejected. Missing
values remain null and are counted explicitly.

The report is descriptive only: no rank forecast, utility, EV/EO blend, or CoVar
is computed. It is not release eligible.
