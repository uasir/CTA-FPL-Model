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

`scripts/estimate_fpl_effective_ownership.py` already:
- estimates ownership, starting, captain, Triple Captain, standard EO and scoring exposure from one-GW manager-pick samples;
- validates 15 unique picks per manager and one captain;
- supports weighted and rank-stratified samples;
- reports effective sample size and approximate 95% intervals;
- explicitly labels the result as a sample estimate, not a global census.

The estimator is a source component, not a new M4 estimator to rebuild.

### 2.2 Personal squad versus field comparison

`scripts/compare_fpl_personal_team_to_field.py` and its tests already:
- fetch the official locked 15-player squad after the deadline plus lock grace;
- validate Gameweek, squad size, unique positions and captain/vice-captain;
- compare owned, standard EO and scoring exposure with the existing field EO CSV;
- handle Bench Boost and Triple Captain;
- fail when any owned player is missing from the field snapshot;
- keep manager-specific output private and entry ID runtime-only.

This is a post-lock actual-squad comparison. It is not yet a pre-deadline comparison of a frozen M3 recommendation candidate.

### 2.3 Existing covariance research

`scripts/estimate_fpl_covariance.py` and `scripts/build_onside_fpl_covariance.py` already provide:
- complete-case player-GW panels with no missing-value zero-fill;
- sample covariance and correlation;
- off-diagonal shrinkage;
- incomplete/zero-variance player exclusions;
- rolling-window stability diagnostics for the Onside actual-points panel.

These outputs are explicitly exploratory. The generic official-FPL history path marks point-in-time status unverified; the Onside path also documents limited coverage and short-window uncertainty. Neither is eligible to drive recommendations.

## 3. Main M4 integration gaps

1. **Pre-deadline candidate exposure:** accept a frozen M3 hold/transfer candidate and compute the candidate squad's player, starter, captain and chip exposure against the exact target-GW field EO snapshot. Do not call the post-lock picks endpoint to reconstruct a pre-deadline recommendation.
2. **Snapshot compatibility:** bind field EO to season, target GW, cohort/rank range, capture time, deadline, sample size/weights, coverage and source artifact hash. Reject mismatched or post-deadline snapshots for pre-deadline use.
3. **Candidate comparison:** report hold versus each eligible M3 candidate using the same EO snapshot. Keep forecast EV deltas separate from field-exposure deltas; never add them together as if they shared units.
4. **Coverage and uncertainty:** propagate field coverage, missing player IDs, sample size, effective sample size and EO intervals. Missing EO remains null; no implicit zero or whole-game ownership claim.
5. **Field context outputs:** add transparent differential/template concentration and rank-cohort exposure summaries without implying a guaranteed rank movement.
6. **Portfolio risk gate:** formalize a no-CoVar default and a separate eligibility contract for covariance-backed metrics. Covariance must remain disabled until point-in-time integrity, sufficient coverage, stability, uncertainty and out-of-sample incremental utility are demonstrated.
7. **M3 optionality:** M3 recommendation generation must remain valid when M4 context is absent, stale, incomplete or ineligible. M4 failure must not corrupt or silently alter the frozen M3 decision.

## 4. Implementation sequence

- **M4-T1 — Readiness and boundary audit:** completed by this register; existing assets and blockers recorded.
- **M4-T2 — Versioned field-context input/output contract:** define and test exact snapshot identity, provenance, coverage, missingness, candidate binding and fail-closed rules.
- **M4-T3 — Pre-deadline candidate-to-field comparison:** implement hold-versus-transfer exposure comparison using the frozen M3 candidate and existing EO snapshot.
- **M4-T4 — Rank-cohort and uncertainty diagnostics:** expose cohort metadata, coverage, effective sample size and confidence intervals in a consistent report.
- **M4-T5 — Portfolio exposure baseline:** implement transparent concentration / correlated exposure summaries that do not require covariance.
- **M4-T6 — CoVar eligibility research gate:** test historical covariance coverage, point-in-time status, stability, shrinkage sensitivity and uncertainty. Keep decision weight zero unless all gates pass.
- **M4-T7 — M3/M4 integration and regression:** verify optional M4 context cannot change M3 EV, legality, or frozen decision hash; add deterministic replay and degraded-mode tests.
- **M4-T8 — Acceptance report and handoff to M5:** document what is implemented, what remains research-only, and the exact release-safe interface.

## 5. Non-negotiable invariants

- LiveFPL / existing rank-stratified EO is the sole field EO reference.
- Official selected-by ownership is not EO.
- EO and EV remain distinct units and separate outputs.
- Missing EO or forecast data remains missing with an explicit reason.
- One exact season / Gameweek / deadline / cohort snapshot per comparison.
- No post-deadline squad state may be used to rewrite a pre-deadline candidate.
- No CoVar production weight without independent evidence and explicit acceptance.
- No personal squad, rank, bank or transfer state may enter squad-independent market rankings.
- Manager-specific comparison artifacts remain private and do not enter the public repository.
- M3 validation proceeds independently; it is not a prerequisite for implementing these M4 contracts.
