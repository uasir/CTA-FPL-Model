# CTA-FPL-Model — Four-Milestone Project Roadmap

**Status:** Agreed roadmap structure, 2026-11-21  
**Repository:** https://github.com/uasir/CTA-FPL-Model

This document is the current agreed milestone structure. It replaces the previous five-milestone sequence as the project roadmap. The former Milestone 4 scope is fully absorbed into Milestone 3; the former Milestone 5 becomes the new Milestone 4.

## Milestone 1 — Recommendation Delivery Backbone

Establish the reliable operational path for producing, validating, recording and evaluating recommendations.

Scope includes:
- Deadline-aware input and forecast capture with provenance.
- Data and schema validation, freshness checks and failure-safe handling.
- Reproducible recommendation runs and evidence capture.
- Auditable output storage, run identifiers and retrospective evaluation hooks.
- Clear separation between research artifacts and production-eligible outputs.

**Completion gate:** The end-to-end delivery path is reproducible and its operational, evidence and validation requirements are satisfied. Existing implementation does not by itself constitute sign-off; outstanding verification remains open.

## Milestone 2 — Model Layer

Develop and validate the forecast/model layer that supplies player-level estimates and uncertainty to the decision engine.

Scope includes:
- Conventional forecast integration and model-output contracts.
- CTA-derived feature/model development where source rights, identity mapping and point-in-time evidence permit it.
- Forecast evaluation, calibration, benchmarking and model-selection evidence.
- Explicit uncertainty and provenance; no synthetic evidence presented as real performance.
- Separation of model research from validated model outputs.

**Completion gate:** Each model output used downstream has documented data lineage, point-in-time status, evaluation evidence and an explicit validation status. Research models remain labelled as such until they pass their gates.

## Milestone 3 — Integrated Decision Engine

Integrate the entire former Milestone 4 scope into the decision engine. CoVar and field-relative portfolio intelligence are capabilities of this engine, not a separate milestone.

Scope includes:

### Forecasts and player evaluation
- Consume the approved conventional and, when validated, CTA model outputs.
- Evaluate expected points, uncertainty and relevant player-level evidence.
- Keep forecast quality and joint-outcome quality as distinct validation questions.

### Field-relative intelligence
- Ownership and effective ownership (EO), with clear definitions and provenance.
- Rank-cohort and field-coverage analysis.
- Distinguish marginal EO from actual sampled manager portfolios; do not reconstruct joint portfolios from marginal ownership percentages.

### Variance and CoVar / portfolio intelligence
- Player-points covariance and joint-scenario analysis.
- Portfolio-level variance, field-relative outcomes and CoVar.
- Validate joint CoVar scenarios separately from conventional player forecast accuracy.
- Keep historical covariance proxies and synthetic test scenarios explicitly labelled; do not imply calibrated forward-looking probabilities without supporting evidence.
- Keep research-only CoVar outputs from silently changing production decisions until the relevant validation and approval gates pass.

### FPL decisions
- Transfers and transfer alternatives.
- Legal formation, starting XI and bench selection.
- Captaincy and vice-captaincy, including chip-aware decisions.
- Multiweek and portfolio-aware decision support.
- Preserve distinct responsibilities for `personal_squad` and `general_market`; squad-specific information must not leak into squad-independent market rankings.
- Respect the agreed starting-XI-first strategy where applicable: bench players are emergency cover, not routine rotation targets.

**Completion gate:** The integrated engine produces legal, reproducible and auditable decisions; forecast, field-data and joint-CoVar validation states are visible and enforced independently. Experimental capabilities cannot silently override conventional recommendations.

## Milestone 4 — Release the Three Recommendation Products

Deliver the three distinct recommendation products through a controlled, auditable Gameweek release.

1. **Conventional squad-specific recommendations:** based on the user's actual squad and conventional expected-points forecasts, assessed against the field using available EO and coverage context.
2. **CTA-informed squad-specific recommendations:** based on the user's actual squad, with validated CTA/model and decision-engine intelligence, assessed against the field using EO, coverage and expected points.
3. **General CTA player recommendations/rankings:** squad-independent market rankings that do not use a user's personal squad, budget, transfers, chip, formation or rank.

**Completion gate:** Each product has a defined input contract, independent output, provenance, validation status and release/evaluation record. One product's context or experimental outputs must not contaminate another.

## Explicit post-GW11 validation work

The following work remains a post-deadline validation sequence associated with the relevant M2/M3 evidence gates. It does not create a separate milestone and does not require pausing independent engineering that can safely proceed.

1. Wait for GW11 official final scoring.
2. Run finality reconciliation including GW11.
3. Match the conventional forecast captured before the GW11 deadline to GW11 actual outcomes.
4. Accumulate additional completed Gameweeks.
5. Evaluate conventional forecast performance across the accumulated evidence.
6. Validate joint CoVar scenarios separately.

**Validation separation:** A successful conventional forecast evaluation does not automatically validate joint CoVar scenarios. The two gates must be reported independently.

## Operating rules

- Preserve the four milestones and their order. Do not treat parallel work as skipping or formally completing an earlier milestone.
- Continue independent engineering in parallel when dependencies allow, while retaining outstanding milestone validation gates.
- Clearly distinguish implemented, tested, evidence-validated and production-eligible capabilities.
- Never represent synthetic fixtures as real-world validation.
- Preserve data provenance and privacy; do not commit private manager picks or raw private snapshots to this public repository.
- Keep research-only CoVar separate from production decisions until its validation gate is passed.
- Do not merge pull requests without explicit user approval.
