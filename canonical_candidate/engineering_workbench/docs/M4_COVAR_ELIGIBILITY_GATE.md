# M4-T6 — CoVar eligibility research gate

The gate is intentionally fail-closed. It evaluates whether a covariance
artifact has point-in-time provenance, source hashes, sufficient window and
complete-panel coverage under an explicit policy, rolling stability,
shrinkage sensitivity, independent uncertainty assessment, and positive
out-of-sample incremental utility with an evidence artifact.

The sensitivity helper recomputes descriptive portfolio variance over a
shrinkage grid while preserving diagonal terms and scaling only off-diagonal
covariance. Missing covariance cells are reported as missing, never zero-filled.

Passing the checks yields only `READY_FOR_EXPLICIT_REVIEW`; it does not make
CoVar production eligible. `decision_weight` is always 0 and
`production_eligible` is always false. The current exploratory FPL/Onside
covariance reports are expected to remain blocked because their point-in-time
integrity and independent validation evidence are not verified.

Run with explicit evidence and policy JSON files:

```bash
PYTHONPATH=scripts python scripts/m4_covar_eligibility_gate.py \
  --report covariance_report.json \
  --pairs fpl_covariance_pairs.csv \
  --evidence covar_evidence.json \
  --policy covar_acceptance_policy.json \
  --portfolio-weights portfolio_weights.json \
  --output covar_gate_report.json
```

No expected-points, field-EO, or recommendation data are changed by this gate.
