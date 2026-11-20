# M4 CoVar — Manager-ID-stripped field portfolio adapter

## Purpose

Bridge the existing pre-deadline rank-stratified manager-pick capture into the
synthetic CoVar scenario scorer without creating a second ownership estimator.
The existing EO estimator remains the source of marginal EO; this adapter uses
the same sampled manager-pick rows to preserve observed within-manager player
co-occurrence and captaincy.

## Capture output

`capture_predeadline_field_eo.py` now emits a separate
`fpl_predeadline_manager_portfolios.json` artifact alongside the existing EO
CSV and report. It is built in memory from the exact manager-pick rows already
used by the EO estimator.

The portfolio artifact:
- contains one sampled portfolio per captured manager;
- retains all 15 FPL element IDs, captain, Triple Captain multiplier, sample
  expansion weight and 1-based 50-rank-page stratum;
- discards manager entry IDs and exact ranks;
- is bound to the same Gameweek, deadline and pre-deadline pick capture time;
- is provisional: managers may still change picks before lock.

**Privacy qualification:** removing entry IDs does not make a 15-player squad
unidentifiable. Squad combinations may be distinctive. The portfolio artifact
must be treated as restricted manager-level data, must not be committed to the
repository, and is uploaded as a separate GitHub Actions artifact with a
7-day retention period. The ordinary EO CSV/report retain their existing
90-day artifact retention.

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

## Run

After downloading both the standard EO/report artifact and the restricted
manager-portfolio artifact from the same workflow run:

```bash
cd canonical_candidate/engineering_workbench
PYTHONPATH=scripts python scripts/m4_covar_field_portfolio_adapter.py \
  --artifact path/to/fpl_predeadline_manager_portfolios.json \
  --report path/to/fpl_predeadline_field_report.json \
  --modeled-player-ids 101,205,311 \
  --gameweek 12 \
  --deadline 2026-11-28T11:00:00Z \
  --as-of 2026-11-27T18:00:00Z \
  --output run_artifacts/m4_covar_field_portfolios_gw12.json
```

Add `--rank-strata 1,2,3` to select specific 50-rank-page strata. The as-of
timestamp must be strictly after field capture and strictly before the same
Gameweek deadline.

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
