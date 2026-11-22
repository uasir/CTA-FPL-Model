# M4 Acceptance Report and M5 Handoff

**Status:** M4 engineering contracts implemented; PR #58 remains draft and unmerged.
**Release status:** Not production/release eligible.
**Latest full CI:** 494 Python engineering tests, 3 subtests, JavaScript recommendation contract tests and all four player identity crosswalk validations passed (run 44816618006).

## 1. Delivered interfaces

### Field context
- `m4_field_context_contract.py` validates exact season, target Gameweek, deadline, snapshot capture time, decision time, cohort, sample, source hash, player coverage and frozen candidate identity.
- Field snapshot capture must be strictly before the M3 decision timestamp; both must be before the target deadline.
- Null EO values remain null. Missing coverage and duplicate IDs fail closed.

### Evidence acquisition and adaptation
- `capture_predeadline_field_eo.py` samples current manager picks before deadline and estimates provisional field EO using the existing estimator.
- `m4_predeadline_field_artifact_adapter.py` admits only the provisional pre-deadline artifact, checks status/flags/timestamps/sample/schema/Gameweek and exact CSV SHA-256.
- `m4_field_artifact_adapter.py` keeps the existing post-lock final-picks artifact retrospective-only. It cannot enter a pre-deadline comparison.

### Candidate comparison and context
- `m4_predeadline_field_comparison.py` accepts the actual M3 output envelope (`evaluation_candidate`), validates the field snapshot, binds the exact frozen decision and runs HOLD-versus-candidate exposure comparison.
- The M3 adapter verifies the candidate transfer changes only the outgoing player's existing XI/bench slot. It rejects unintended lineup, bench, reserve-goalkeeper, captain, vice-captain or formation changes.
- `m4_field_context_diagnostics.py` reports cohort, sample, coverage, metric missingness/ranges and EO interval-width diagnostics.
- `m4_portfolio_exposure_baseline.py` reports separate squad/XI/bench field exposure sums, top-player exposure and descriptive concentration metrics. It does not infer covariance.

### CoVar research gate
- `m4_covar_eligibility_gate.py` checks point-in-time evidence, explicit window/coverage policy, rolling stability, shrinkage sensitivity, independent uncertainty and positive out-of-sample incremental utility.
- Passing the gate yields review eligibility only. Decision weight remains exactly zero; production eligibility remains false.

### M3 optionality
- `m4_m3_optionality_adapter.py` verifies the M3 frozen-decision hash and embedded candidate identity.
- Missing, stale, mismatched or invalid M4 context is withheld. The M3 output, provider EV, legality and frozen decision remain unchanged.
- Existing M3 deterministic replay tests continue to verify exact frozen-input re-execution.

## 2. M5 consumption contract

M5 may consume the M4 artifact only as an optional, descriptive sidecar:
- Keep conventional M3 expected-points recommendation and M4 field-relative context as separate outputs.
- Keep expected points in points and EO/exposure in percentage points. Never add or blend them without a separately validated model and acceptance process.
- Keep general CTA/player rankings independent of manager-specific squad, rank, bank and transfer state.
- Preserve cohort, sample size, effective sample size, coverage, null counts, interval widths, source hashes and timing metadata with every field comparison.
- Treat the pre-deadline field estimate as provisional current picks, not final locked EO or a whole-game census.
- Do not allow M4 context to change M3 transfer legality, xP, recommendation or frozen decision.
- Do not use covariance or CoVar in recommendation weights. CoVar remains research-only with zero decision weight.

## 3. Outstanding evidence and blockers

1. The scheduled/manual pre-deadline capture workflow has not yet produced a verified live artifact in this PR. CI uses deterministic fixtures; a successful live run is still required to verify API availability and actual capture timing.
2. Existing FPL/Onside covariance artifacts remain exploratory. Point-in-time historical integrity, sufficient validation evidence, uncertainty assessment and positive out-of-sample incremental utility are not established.
3. M3 post-Gameweek validation remains an independent workstream and is not silently promoted by M4.
4. PR #58 is draft and unmerged. No merge or release approval has been granted.

## 4. Release decision

**M4 engineering implementation: accepted for review.**
**Production recommendation use: not approved.**
**CoVar: disabled, decision weight 0.**
**M3 behavior: unchanged when M4 is absent or withheld.**

The next release decision requires explicit review of PR #58, a successful live pre-deadline artifact capture, and independent acceptance of any future covariance research. This report does not authorize merge, production activation or a public recommendation release.
