# M4 CoVar — Manager-ID-stripped field portfolio adapter

## Purpose

Bridge the existing pre-deadline rank-stratified manager-pick capture into the
synthetic CoVar scenario scorer without creating a second ownership estimator.
The existing EO estimator remains the source of marginal EO; this adapter uses
the same sampled manager-pick rows to preserve observed within-manager player
co-occurrence and captaincy.

## Capture output

`capture_predeadline_field_eo.py` builds the manager-level portfolio
representation in memory from the exact manager-pick rows already used by the
EO estimator. It writes `fpl_predeadline_manager_portfolios.json` only when
the caller explicitly supplies `--manager-portfolio-output`.

The portfolio artifact:
- contains one sampled portfolio per captured manager;
- retains all 15 FPL element IDs, captain, Triple Captain multiplier, sample
  expansion weight and 1-based 50-rank-page stratum;
- discards manager entry IDs and exact ranks;
- is bound to the same Gameweek, deadline and pre-deadline pick capture time;
- is provisional: managers may still change picks before lock.

**Privacy qualification:** removing entry IDs does not make a 15-player squad
unidentifiable. Squad combinations may be distinctive. The ordinary public
workflow therefore never writes or uploads this manager-level artifact. It
keeps the rows in memory, emits only aggregate EO CSV/report, and records
`manager_portfolio_export_status: NOT_EXPORTED_LOCAL_ONLY`. A user may opt in
with `--manager-portfolio-output` to write the manager-ID-stripped artifact to
an explicitly chosen private local path. Do not commit it or upload it to the
public repository's Actions artifacts. The ordinary EO CSV/report retain
their existing workflow artifact retention.

## Scenario projection

`m4_covar_field_portfolio_adapter.py` verifies the artifact against the capture
report's SHA-256 manifest and projects each sampled 15-player squad onto the
explicit player universe in a synthetic fixture scenario.

- The original sample weights are normalized to sum to one.
- Optional rank-stratum filtering renormalizes weights within the selected
  cohort.
- Managers with no players in the modeled fixture are retained as zero-point
  field portfolios; they are not silently dropped.
- If a manager's captain is outside the modeled player universe, the fixture
  slice has no captain multiplier (1x). If the captain is in scope, the
  captured captain or Triple Captain multiplier is retained.
- Projection coverage and captain coverage are reported.

This is a fixture-slice comparison, not a full-GW manager score. A complete
Gameweek comparison requires all relevant fixtures, player outcomes and
Gameweek scoring mechanics, including autosubs and chip effects.

## Run locally

The public GitHub Actions workflow intentionally does not export manager-level
portfolios. Run the capture locally at the relevant pre-deadline window and
choose a private path outside the repository working tree:

```bash
python canonical_candidate/engineering_workbench/scripts/capture_predeadline_field_eo.py \
  --out-dir /tmp/fpl-eo-gw12 \
  --manager-portfolio-output /secure/private/fpl_predeadline_manager_portfolios.json
```

The report and aggregate EO CSV are written under `--out-dir`; the report
contains a SHA-256 manifest for the separate local portfolio file. Keep both
files private and do not commit or upload the portfolio file.

Then adapt the local artifact to a fixture slice:

```bash
cd canonical_candidate/engineering_workbench
PYTHONPATH=scripts python scripts/m4_covar_field_portfolio_adapter.py \
  --artifact /secure/private/fpl_predeadline_manager_portfolios.json \
  --report /tmp/fpl-eo-gw12/fpl_predeadline_field_report.json \
  --modeled-player-ids 101,205,311 \
  --gameweek 12 \
  --deadline 2026-11-28T11:00:00Z \
  --as-of 2026-11-27T18:00:00Z \
  --output /secure/private/m4_covar_field_portfolios_gw12.json
```

Add `--rank-strata 1,2,3` to select specific 50-rank-page strata. The as-of
timestamp must be strictly after field capture and strictly before the same
Gameweek deadline. The adapted output also contains manager-level squad
combinations and must remain at a private local path.

## Contract boundary

The output uses `portfolio_role: FIELD` and explicit `field_weight` values
compatible with the synthetic CoVar contract. It never reconstructs joint
manager portfolios from marginal EO. It does not create forecasts, calculate
BPS, estimate missing picks, infer Free Hit usage, or enable production
recommendations. The default comparison mode remains `REGULAR_GW`; Free Hit
segmentation is not required.

The current artifact captures the overall top-rank cohort. Rank strata are
available for controlled cohort selection; small stratum sample sizes must be
reported and must not be presented as precise cohort estimates.
