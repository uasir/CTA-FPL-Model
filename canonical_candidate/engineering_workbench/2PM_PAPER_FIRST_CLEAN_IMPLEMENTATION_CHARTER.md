# 2PM Transformer — Paper-First Clean Implementation Charter

**Status:** governing implementation decision  
**Governing architecture:** Wiechno, Duch and Bartosik (2026), *Modeling Fantasy Premier League Player Performance with a Two-Component Poisson Mixture Transformer*, ICAART 2026, DOI: 10.5220/0014358000004052.

## 1. Superseding decision

The previously existing 2PM implementation is **frozen and discarded as an implementation source**. It is not the foundation for the paper-governed model.

The new implementation must be developed independently from the published paper. Do not refactor, extend, import, copy, wrap, or depend on the legacy 2PM model, its evaluator, its preprocessing, its sequence builder, its categorical heads, its training loop, its calibration, its artifacts, or its implementation assumptions.

The legacy code may remain in repository history or a clearly quarantined archive for auditability, but it must not be a runtime, training, inference, test, or data dependency of the new model. Do not delete or rewrite historical records without a separate explicit repository decision.

Historical scores and findings from the discarded implementation are not performance evidence for the new paper-faithful model.

## 2. Governing sources and permitted reuse

The published paper is the authority for model architecture, sample construction, feature contract, predictive distribution, and training objective.

Permitted reuse:
- the project's shared/versioned source data and source adapters, after independently auditing definitions, provenance, licensing, time availability, and point-in-time correctness;
- generic repository infrastructure unrelated to the discarded model (CI, artifact storage conventions, logging, versioning, common schemas), after verifying it does not encode legacy model assumptions;
- the established forecast hand-off contract into M3, once the new forecast output is validated against it;
- the existing M3 decision engine and M4 recommendation delivery pipeline, without moving decision logic into the forecasting model.

Not permitted:
- legacy 2PM model modules or classes;
- legacy feature selection, preprocessing, imputation/scaling state, sequence construction or labels;
- legacy loss functions, categorical output heads, calibration, training/evaluation routines, checkpoints or model artifacts;
- unverified assumptions copied from the old evaluator.

If any shared infrastructure has a hidden dependency on legacy 2PM semantics, isolate or replace that dependency before using it.

## 3. New model identity and boundary

Create a new, independently versioned paper-governed 2PM Transformer implementation.

Its only responsibility is player-level FPL points forecasting. It must produce the two-component Poisson-mixture predictive distribution and its analytic forecast quantities.

It must not implement:
- transfers or transfer hit decisions;
- squad construction or player selection;
- starting XI, bench ordering or captaincy;
- ownership or effective ownership;
- coverage, CoVar or portfolio optimization;
- recommendation ranking or recommendation policy.

The forecast is consumed by M3. M3 remains responsible for decisions. M4 delivers the squad-specific product **2PM Squad Recommendations** through the established product architecture.

## 4. Paper-first build sequence

1. Retrieve and inspect the complete published paper and any author-provided supplementary material/code, if available. Separate explicitly specified details from details that the paper leaves unspecified.
2. Independently audit the shared data foundation for match-level observations, player identity mapping, historical coverage, source definitions, point-in-time availability, and rights.
3. Establish the complete 116-feature dictionary. Do not invent missing feature definitions or claim exact reproduction without evidence. If the full schema cannot be recovered, document a source-backed reconstruction and label the implementation an adaptation.
4. Build a new five-previous-played-match sequence dataset with the paper's maximum 21-day gap rule and strict pre-deadline point-in-time controls.
5. Implement the encoder-only Transformer and two-component Poisson-mixture output from a clean module, without importing any legacy 2PM code.
6. Implement the paper's mixture negative log-likelihood, training-only MLE rate initialization, and paper-described training protocol. Record any paper-unspecified choices.
7. Implement independent training, chronological evaluation, artifact serialization, inference, and forecast-interface validation.
8. Connect only the validated forecast interface to M3. Keep M3/M4 logic unchanged.
9. Run essential acceptance tests and a controlled paper-reproduction evaluation. The previously completed legacy evaluation does not count toward these gates.

## 5. Paper-specific points that must remain explicit

- Five consecutive prior matches actually played by the player.
- No more than 21 days between selected matches.
- 116 features per match, with a fully documented feature dictionary.
- Encoder-only Transformer.
- Mixture probability (p) and two positive Poisson rates (lambda_1,lambda_2).
- Mixture likelihood objective.
- Training-only MLE initialization of component rates.
- Chronological data separation and no target leakage.
- Paper's handling of negative FPL points must be represented transparently; preserve original actual outcomes for evaluation and record all target transformations.
- The paper does not fully specify every implementation detail (including selected layer count and certain sampling/representation details). Do not fabricate these as paper requirements; document and justify the independent choices.

## 6. Production and change controls

- New model starts research-only.
- Keep production weight 0 and `production_eligible=false` until separate validation and approval.
- Do not merge any PR without explicit user approval.
- Do not modify or delete the frozen legacy implementation as part of this work.
- Do not claim compliance, successful tests, or performance until verified against the new implementation.
- The previous M2 model/forecast evaluation deferral remains in force; this clean implementation work does not waive it.

## 7. Relationship to the earlier compliance specification

The earlier `2PM_PAPER_ARCHITECTURE_COMPLIANCE.md` remains a technical reference for paper requirements and acceptance criteria. This charter supersedes any interpretation that the legacy implementation is to be refactored or used as the new model's starting point. Any specification details not directly supported by the paper must remain labelled as implementation decisions or unresolved items.

## 8. Governing decision

**Build the paper-governed 2PM Transformer from a clean slate. Reuse audited shared data and generic platform infrastructure only. Integrate its forecasts into the existing M3/M4 architecture, and nothing more.**
