# M4 Field / Portfolio Intelligence — Implementation Gap Register

**Status:** M4 engineering active; M3 post-Gameweek validation remains pending independently.
**Base:** M3 unified evaluation branch head `8d7e8a96df3f0f5d69d2ed178c4baf51b754ce1f`.
**Scope:** Field-relative context and portfolio-risk infrastructure. No recommendation release, model promotion, or CoVar activation.

## 1. M4 boundary

M4 enriches a conventional M3 decision with field-relative exposure and portfolio context. It must not:
- replace or estimate a second field-ownership system;
- change provider expected-points values;
- treat EO as a points or rank forecast;
- depend on M3 historical performance being validated;
- use unvalidated CTA/ABC/2PM forecasts as decision inputs;
- activate CoVar merely because a covariance matrix can be computed.

The existing LiveFPL / rank-stratified EO pipeline remains the field reference. Official FPL selected-by ownership remains a separate metric.

## 2. Existing implementation confirmed on main

### 2.1 Field EO estimator

`scripts/estimate_fpl_effective_ownership.py` already estimates ownership, starting, captain, Triple Captain, standard EO and scoring exposure from one-GW manager-pick samples; validates 15 unique picks per manager and one captain; supports weighted and rank-stratified samples; and reports effective sample size and approximate 95% intervals. It labels results as sample estimates, not global censuses. It remains the single estimator.

### 2.2 Personal squad versus field comparison

`scripts/compare_fpl_personal_team_to_field.py` and its tests compare the official locked squad with field EO after deadline. They are not a pre-deadline comparison of a frozen M3 candidate.

### 2.3 Existing covariance research

`scripts/estimate_fpl_covariance.py` and `scripts/build_onside_fpl_covariance.py` provide exploratory covariance/correlation and stability outputs. Point-in-time integrity, coverage and stability are not sufficient for recommendation use. They remain research-only.

## 3. Completed M4 core contracts

- **M4-T1 — Readiness and boundary audit:** completed by this register.
- **M4-T2 — Versioned field-context contract:** completed; exact snapshot identity, provenance, coverage, missingness and candidate binding are validated.
- **M4-T3 — Frozen candidate-to-field comparison:** completed; HOLD and frozen transfer are compared against one EO snapshot with starter/bench slot preservation.
- **M4 evidence subtask A — Post-lock artifact adapter:** completed; existing final-picks artifacts are hash-verified and explicitly excluded from pre-deadline admission.
- **M4 evidence subtask B — Pre-deadline field acquisition:** implemented and CI-tested; captures a stratified sample of current picks before deadline, labels it provisional, and discards incomplete/late samples.
- **M4 evidence subtask C — M3 candidate binding and comparison CLI:** implemented and CI-tested; adapts the real M3 `evaluation_candidate` envelope, verifies that only the outgoing player's existing slot changes, and runs the M4 field comparison.

The evidence subtasks are additional implementation work that closes the original pre-deadline ingestion gap. They do **not** renumber or waive the remaining acceptance gates below. CI passing with deterministic fixtures does not mean a live pre-deadline field artifact has been captured.

## 4. Remaining original M4 acceptance sequence

1. **M4-T4 — Rank-cohort and uncertainty diagnostics:** completed; the diagnostics module reports cohort metadata, coverage, effective sample size, metric missingness/ranges and EO confidence-interval widths. Incomplete/inverted intervals fail closed; null values remain null.
2. **M4-T5 — Portfolio exposure baseline:** completed; report separate squad/XI/bench field-exposure sums, top-player exposure, top-3/top-5 concentration shares, HHI, effective contributor count and captain-share differential. Missing values withhold dependent sums/concentration. No covariance or correlation is inferred.
3. **M4-T6 — CoVar eligibility research gate:** gate implementation completed and CI-tested. It checks point-in-time provenance, explicit window/coverage policy, rolling stability, shrinkage sensitivity, independent uncertainty and positive out-of-sample utility evidence. Existing exploratory artifacts remain blocked; decision weight is hard-coded to zero and production eligibility remains false.
4. **M4-T7 — M3/M4 integration and regression:** completed and CI-tested. The optionality adapter verifies M3 frozen-decision hash, embedded candidate identity and exact lineup/bench order; M4 must predate the M3 decision. Absent, stale, mismatched or invalid M4 is withheld without changing M3 EV, legality or decision. Existing deterministic replay tests remain in force.
5. **M4-T8 — Acceptance report and M5 handoff:** completed as an engineering handoff. The report documents interfaces, research-only components, remaining live-data/covariance blockers and release-safe boundaries. M4 remains unmerged and not production eligible.

## 5. Non-negotiable invariants

- LiveFPL / existing rank-stratified EO is the sole field EO reference.
- Official selected-by ownership is not EO.
- EO and EV remain distinct units and separate outputs.
- Missing EO or forecast data remains missing with an explicit reason.
- One exact season / Gameweek / deadline / cohort snapshot per comparison.
- No post-deadline squad state may rewrite a pre-deadline candidate.
- No CoVar production weight without independent evidence and explicit acceptance.
- No personal squad, rank, bank or transfer state may enter squad-independent market rankings.
- Manager-specific comparison artifacts remain private and do not enter the public repository.
- M3 validation proceeds independently; it is not a prerequisite for implementing M4 contracts.

## 6. CoVar manager-level field portfolio bridge

Implemented on the M4 CoVar branch: the existing pre-deadline rank-stratified capture now emits a separate manager-ID-stripped 15-player portfolio sample with captaincy, Triple Captain multiplier, rank-page stratum and normalized expansion weights. The artifact is SHA-256-bound to the capture report and uploaded separately with 7-day retention; it is not committed to the repository. Entry IDs and exact ranks are discarded, but distinctive squad combinations may remain identifying, so the artifact is restricted manager-level data.

The adapter projects each sampled portfolio onto an explicit fixture player universe, renormalizes weights for any selected rank strata, and retains managers with no relevant fixture players as zero-point field slices. This preserves observed within-manager co-occurrence; it does not reconstruct joint portfolios from marginal EO.

Still missing: full-Gameweek manager portfolio scoring, autosubs and all chip effects, empirical representativeness/uncertainty validation for relative-score tails, set-piece taker/target attribution and event-based BPS.
