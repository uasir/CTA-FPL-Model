# M4-T3 — Frozen candidate versus field exposure comparison

## Purpose

Compare the user's frozen M3 HOLD decision with its frozen TRANSFER candidate against the same pre-deadline field EO snapshot. The comparison makes the exposure consequences of a decision visible without translating EO into expected points or rank.

## Inputs

The comparison consumes the normalized output of `validate_field_context` from `m4_field_context_contract.py`. It therefore inherits the snapshot identity, source hash, rank cohort, effective sample size, coverage, deadline and frozen decision binding.

The normalized candidate retains the original 15-player squad, starting XI, outfield bench order, reserve goalkeeper and captain/vice-captain identity. A transfer replaces the outgoing player's existing squad slot; a starter remains a starter and a bench player remains in the same bench slot. Goalkeeper rotation is not part of this comparison. A transfer of the captain is rejected unless a future contract explicitly carries a replacement captain decision.

## Outputs

`compare_frozen_candidate_to_field` returns:
- HOLD and frozen-candidate player-level EO and starting-exposure comparisons;
- the percentage-point exposure changes caused by the proposed transfer;
- the cohort and sample context attached to the comparison;
- portfolio exposure-gap sums, explicitly labelled as sums of percentage-point differences, not points or utility.

## Boundaries

- No forecast xP is consumed or changed.
- EV and EO are not combined.
- Field EO is never recalculated here.
- Missing field values remain null; missing candidate-player coverage fails closed.
- No whole-field census claim is made.
- CoVar remains disabled.
- Output is not release eligible and cannot alter the frozen M3 recommendation.

## Implementation

- `scripts/m4_candidate_field_comparison.py`
- `tests/test_m4_candidate_field_comparison.py`
