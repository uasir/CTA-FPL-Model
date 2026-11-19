# Personal FPL squad versus field comparison

## Purpose

Compare one manager's locked 15-player FPL squad with the existing CTA rank-stratified field EO snapshot. This is a consumer of the existing EO system; it does not create, estimate, or replace an ownership model.

## Inputs

- A runtime FPL entry ID (never hard-coded or written to output).
- The target Gameweek.
- The existing EO workflow's `fpl_effective_ownership_sample.csv` artifact for that same Gameweek.

The script fetches the official FPL bootstrap and the public entry picks endpoint. It refuses to compare a Gameweek until its official deadline plus the configured lock grace period has passed. It verifies the event returned by the picks endpoint, the 15-player squad, unique positions, and captain/vice-captain selection.

## Comparison semantics

For the personal squad:
- Owned-by exposure is 100% for each of the 15 selected players.
- Standard personal EO is 100% for ownership, plus 100% for captaincy, plus another 100% for Triple Captain.
- Personal scoring exposure counts starters, Bench Boost substitutes, captaincy and the extra Triple Captain exposure.

The report compares those values with the corresponding fields from the existing EO snapshot:
- `effective_ownership_delta_pct = personal_effective_ownership_pct - field_effective_ownership_pct`
- `scoring_exposure_delta_pct = personal_scoring_exposure_pct - field_scoring_exposure_pct`

Positive differentials mean the personal squad has more exposure than the sampled field; negative differentials mean less exposure. This is exposure, not a points or rank forecast. The separate CoVar portfolio layer remains responsible for correlated squad risk.

The field snapshot remains a weighted sample of the rank cohort, not a whole-game census. No missing owned player is silently assigned zero field EO; incomplete field coverage causes the comparison to fail.

## Run

From `canonical_candidate/engineering_workbench`, after downloading the existing EO artifact:

```bash
PYTHONPATH=scripts python scripts/compare_fpl_personal_team_to_field.py \
  --entry-id YOUR_FPL_ENTRY_ID \
  --gameweek TARGET_GAMEWEEK \
  --field-eo /path/to/fpl_effective_ownership_sample.csv \
  --out-dir /path/to/private-output
```

The entry ID is supplied at runtime and is not stored in the repository. Keep the output directory private: the CSV contains a manager-specific squad comparison.

## Outputs

- `fpl_personal_team_vs_field.csv`: player-by-player ownership, EO and scoring-exposure differentials.
- `fpl_personal_team_vs_field_report.json`: concise summary and interpretation.

The script deliberately does not recalculate field EO, alter EO sampling, compute CoVar, or infer points/rank impact.
