# 2PM Transformer — Paper-First Clean Implementation Charter

**Status:** governing implementation decision  
**Governing architecture:** Wiechno, Duch and Bartosik (2026), *Modeling Fantasy Premier League Player Performance with a Two-Component Poisson Mixture Transformer*, ICAART 2026, DOI: 10.5220/0014358000004052.  
**Input adaptation:** Dastan 286-feature candidate contract, governed by `2PM_DASTAN_286_FEATURE_ADAPTATION_DECISION.md`.

## 1. Superseding decision

The previously existing 2PM implementation is **frozen and discarded as an implementation source**. It is not the foundation for the paper-governed model.

The new implementation must be developed independently from the published paper. Do not refactor, extend, import, copy, wrap, or depend on the legacy 2PM model, its evaluator, its preprocessing, its sequence builder, its categorical heads, its training loop, its calibration, its artifacts, or its implementation assumptions.

The legacy code may remain in repository history or a clearly quarantined archive for auditability, but it must not be a runtime, training, inference, test, or data dependency of the new model. Do not delete or rewrite historical records without a separate explicit repository decision.

Historical scores and findings from the discarded implementation are not performance evidence for the new paper-governed model.

## 2. Governing sources and permitted reuse

The published paper governs the core model architecture, predictive distribution, and training objective. The approved Dastan adaptation decision governs the candidate input foundation and the additional feature/sequence audits.

Permitted reuse:
- the project's shared/versioned source data and source adapters, after independently auditing definitions, provenance, licensing, time availability, and point-in-time correctness;
- the Dastan 286-feature schema and underlying source data as a candidate input foundation, only after the feature-level and sequence-level gates in `2PM_DASTAN_286_FEATURE_ADAPTATION_DECISION.md` pass;
- generic repository infrastructure unrelated to the discarded model (CI, artifact storage conventions, logging, versioning, common schemas), after verifying it does not encode legacy model assumptions;
- the established forecast hand-off contract into M3, once the new forecast output is validated against it;
- the existing M3 decision engine and M4 recommendation delivery pipeline, without moving decision logic into the forecasting model.

Not permitted:
- legacy 2PM model modules or classes;
- legacy feature selection, preprocessing, imputation/scaling state, sequence construction or labels;
- legacy loss functions, categorical output heads, calibration, training/evaluation routines, checkpoints or model artifacts;
- Dastan minutes/points model heads, model weights, training logic, calibration, prediction outputs or model artifacts as 2PM components;
- unverified assumptions copied from the old evaluator or from Dastan's minutes-model task.

If any shared infrastructure has a hidden dependency on legacy 2PM or Dastan predictive-model semantics, isolate or replace that dependency before using it.

## 3. New model identity and boundary

Create a new, independently versioned 2PM Transformer implementation.

Its only responsibility is player-level FPL points forecasting. It must produce the two-component Poisson-mixture predictive distribution and its analytic forecast quantities.

It must not implement:
- transfers or transfer hit decisions;
- squad construction or player selection;
- starting XI, bench ordering or captaincy;
- ownership or effective ownership;
- coverage, CoVar or portfolio optimization;
- recommendation ranking or recommendation policy.

The forecast is consumed by M3. M3 remains responsible for decisions. M4 delivers the squad-specific product **2PM Squad Recommendations** through the established product architecture.

## 4. Approved input-foundation adaptation

The original paper describes 116 features per previous match. The user has approved replacing that input-feature contract with the project's Dastan **286-feature contract as the candidate input foundation**.

This is a documented architecture/data adaptation, not an exact reproduction of the paper's original feature representation or dataset.

Important constraints:
- Dastan's 286 columns are engineered, deadline-anchored player-fixture features, not 286 raw statistics from one match.
- The 286-column contract was designed for a minutes model. Its feature schema and data representation may be audited and adapted; its predictive model is not reused.
- All 286 columns are candidates, not automatically approved 2PM predictors. Each must pass semantic, point-in-time, target-leakage, coverage, rights, missingness and sequence-compatibility checks.
- The paper's five-previous-played-match and maximum 21-day sequence principles remain the reference. The mapping from Dastan's deadline snapshots to sequence tokens is an open design gate and must not be assumed solved by the existence of 286 columns.
- The exact feature admission, source-semantics, dataset/identity freshness, and sequence design records are: `2PM_DASTAN_286_FEATURE_ADAPTATION_DECISION.md`, `2PM_DASTAN_286_FEATURE_ADMISSION_REGISTER.md`, `2PM_DASTAN_SOURCE_SEMANTICS_AUDIT.md`, `2PM_DASTAN_DATASET_AND_IDENTITY_READINESS.md`, and `2PM_DASTAN_SEQUENCE_REPRESENTATION_PROPOSAL.md`. These records collectively define the schema-freeze criteria and build order; the sequence representation remains a proposal.

Do not claim exact paper reproduction. The project must label the resulting system as a Dastan-input adaptation of the paper's two-component Poisson-mixture Transformer.

## 5. Core paper requirements retained

- Encoder-only Transformer.
- Mixture probability (p) and two positive Poisson rates (lambda_1,lambda_2).
- Two-component Poisson-mixture predictive distribution.
- Analytic expected points and variance derived from the mixture.
- Mixture negative log-likelihood objective.
- Training-only MLE initialization of component rates.
- Chronological data separation and no target leakage.
- Transparent treatment of negative FPL point totals; preserve original actual outcomes and record all target transformations.
- The five-previous-played-match and maximum 21-day requirements remain the paper reference; any adaptation to Dastan feature snapshots must be explicitly justified and versioned before implementation.

The paper does not fully specify every implementation detail (including selected layer count and certain sampling/representation details). Do not fabricate these as paper requirements; document and justify independent choices.

## 6. Clean implementation sequence

1. Pin the paper and record all explicitly specified versus unspecified model details.
2. Pin the Dastan 286-column schema and source inventory.
3. Complete the 286-feature semantic, source-rights, temporal, missingness and leakage admission audit.
4. Resolve the Dastan-to-five-played-match sequence-token representation, including the 21-day rule, before building a sequence dataset.
5. Establish lawful historical target labels, source vintages and player/fixture identity mappings.
6. Freeze a versioned 2PM adaptation schema only after the feature and sequence gates pass.
7. Implement a new sequence dataset and encoder-only Transformer from a clean module, without importing legacy 2PM or Dastan predictive-model code.
8. Implement the paper's mixture negative log-likelihood, training-only MLE rate initialization, and documented training protocol. Record any paper-unspecified choices.
9. Implement independent training, chronological evaluation, artifact serialization, inference, and forecast-interface validation.
10. Connect only the validated forecast interface to M3. Keep M3/M4 logic unchanged.
11. Run essential acceptance tests and a controlled adaptation evaluation. The previously completed legacy evaluation does not count toward these gates.

## 7. Production and change controls

- New model starts research-only.
- Keep production weight 0 and `production_eligible=false` until separate validation and approval.
- Do not merge any PR without explicit user approval.
- Do not modify or delete the frozen legacy implementation as part of this work.
- Do not claim compliance, successful tests, or performance until verified against the new implementation.
- The previous M2 model/forecast evaluation deferral remains in force; this clean implementation work does not waive it.

## 8. Relationship to earlier specifications

`2PM_PAPER_ARCHITECTURE_COMPLIANCE.md` remains a technical reference for the published model's core requirements. The new Dastan adaptation does not rewrite what the paper originally used; it records the deliberate input-data departure and its outstanding gates.

`2PM_DASTAN_286_FEATURE_ADAPTATION_DECISION.md` is the governing record for the 286-feature input adaptation, feature admission audit, sequence representation and schema-freeze conditions. If a general paper specification and the adaptation record differ on the original feature count, treat the paper's 116 as the published-paper fact and the Dastan 286 as the approved project adaptation.

## 9. Governing decision

Build the new 2PM forecaster from a clean slate. Preserve the paper's two-component Poisson-mixture Transformer core, use the Dastan 286-feature contract as the candidate input foundation subject to explicit admission gates, and do not reuse either legacy 2PM implementation code or Dastan predictive-model code. Integrate validated forecasts into the existing M3/M4 architecture, and nothing more.
