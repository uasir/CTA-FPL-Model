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
- CTA-derived feature/model development where source rights, identity mapping and point-in-time evidence permit it.
- Forecast evaluation, calibration, benchmarking and model-selection evidence.
- Explicit uncertainty and provenance; no synthetic evidence presented as real performance.
- Separation of model research from validated model outputs.

**Conventional-provider integration ownership:** M3 owns the external conventional forecast integrations through its provider-neutral forecast-input scope; M2 owns model-layer evaluation and validation. The approved external providers are exactly:
1. FPL Cat (existing integration).
2. FPL Sideline Quant (existing integration).

No additional external forecast providers are in scope. FPLRogue, FPL Lucho and FPL Wildcard are explicitly excluded; no adapters or forecast integrations will be built for them. FPL Forecaster and FPL Review are also excluded, and their forecasts and historical data must not be used.

**Evaluation timing:** Formal provider-by-provider forecast-performance evaluation is deferred until the upcoming Gameweek's official scores are available. Work on the two approved integrations and capture engineering continues in parallel; this evaluation deferral does not block M3 implementation.

**Completion gate:** Each model output used downstream has documented data lineage, point-in-time status, evaluation evidence and an explicit validation status. Research models remain labelled as such until they pass their gates.

## Milestone 3 — Integrated Decision Engine

Integrate the entire former Milestone 4 scope into the decision engine. CoVar and field-relative portfolio intelligence are capabilities of this engine, not a separate milestone.

Scope includes:

### Forecasts and player evaluation
- A unified, provider-neutral interface for exactly two conventional forecast providers: FPL Cat and FPL Sideline Quant.
- Preserve each provider's identity, product/variant, original forecast values, forecast grain, source timestamps, capture timestamps, provenance, coverage and missingness.
- Use provider-specific source adapters and schema validation; do not fabricate endpoints, values or timestamps.
- Do not silently aggregate fixture-level forecasts into player-Gameweek forecasts. Any such transformation requires an explicit, tested and provenance-bearing aggregation contract.
- Keep provider outputs individually addressable and evaluable. Do not average or blend providers arbitrarily; any future selection or weighting must be supported by evidence.
- FPL Cat and FPL Sideline Quant are the only approved integrated providers. Do not add FPLRogue, FPL Lucho or FPL Wildcard.
- FPL Forecaster and FPL Review are excluded and must not be used as forecast or historical-data sources.
- Consume FPL Cat and FPL Sideline Quant as separate conventional forecast sources; when validated, consume the CTA-FPL model through the same canonical forecast interface.
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

1. **Conventional squad-specific recommendations:** based on the user's actual squad and FPL Cat / FPL Sideline Quant forecasts, assessed against the field using available EO and coverage context.
2. **CTA-informed squad-specific recommendations:** based on the user's actual squad and the validated CTA-FPL model. It replaces the conventional forecast inputs but uses the same canonical forecast interface and the same personal-squad recommendation pipeline, assessed against the field using EO, coverage and expected points.
3. **General CTA player recommendations/rankings:** a separate squad-independent market product that does not use a user's personal squad, budget, transfers, chip, formation or rank.

**Evaluation timing:** Formal recommendation-product performance evaluation is deferred until the upcoming Gameweek's official scores are available. Product engineering and release-readiness work may continue without treating this evaluation as complete.

**Completion gate:** Each product has a defined input contract, independent output, provenance, validation status and release/evaluation record. The conventional and CTA-informed personal-squad products share the same recommendation pipeline; only their forecast source differs. General CTA rankings remain squad-independent. One product's context or experimental outputs must not contaminate another.

## Post-GW11 and upcoming-Gameweek validation work

The following validation work remains separate from ongoing engineering and does not create a new milestone:

1. Obtain the upcoming Gameweek's official final scores.
2. Run finality reconciliation for the relevant completed Gameweek evidence, including GW11 where applicable.
3. Match captured pre-deadline provider forecasts to the corresponding actual outcomes.
4. Accumulate additional completed Gameweeks.
5. Perform the deferred M2 provider-by-provider forecast-performance evaluation.
6. Perform the deferred M4 recommendation-product performance evaluation.
7. Validate joint CoVar scenarios separately.

**Validation separation:** Conventional forecast accuracy, recommendation-product performance and joint CoVar scenario validity are distinct evaluation questions. Passing one does not validate the others.

## Operating rules

- Preserve the four milestones and their order. Do not treat parallel work as skipping or formally completing an earlier milestone.
- Continue independent engineering in parallel when dependencies allow, while retaining outstanding milestone validation gates.
- Clearly distinguish implemented, tested, evidence-validated and production-eligible capabilities.
- Never represent synthetic fixtures as real-world validation.
- Preserve data provenance and privacy; do not commit private manager picks or raw private snapshots to this public repository.
- Keep research-only CoVar separate from production decisions until its validation gate is passed.
- Do not merge pull requests without explicit user approval.
