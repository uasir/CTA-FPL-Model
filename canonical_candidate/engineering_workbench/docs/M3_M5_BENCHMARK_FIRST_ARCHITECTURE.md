# M3–M5 Benchmark-First Architecture Blueprint

**Status:** Architecture specification in progress; implementation deferred until the milestone sequence reaches each milestone.  
**Created:** 2026-11-20  
**Architecture rule:** M1 and M2 remain the active execution sequence. This document defines the downstream contracts now; it does not start M3 implementation or authorize production use of unvalidated model outputs.

## 1. Purpose and governing decisions

Define the structure for Milestones 3, 4 and 5 before implementation, so that M2 can produce model outputs compatible with the complete delivery system.

The downstream system must work initially with the agreed external FPL forecasting benchmarks. Once the project's own model has passed M2's validation and promotion gates, it can be added as another forecast provider or replace an external provider through the same versioned interface. M3–M5 must not need to be redesigned.

Governing decisions:

1. **Benchmark-first operation:** M3, M4 and M5 initially consume actual, timestamped forecasts from the agreed FPL benchmark sources. FPL history remains useful input/context for modelling and diagnostics, but it is not a substitute for the agreed external benchmark set.
2. **Provider independence:** downstream components consume a canonical forecast contract, not provider-specific payloads or hard-coded provider assumptions.
3. **Own-model integration:** ABC/CTA, 2PM, or a subsequently selected model is registered as a forecast provider only after M2 validation. A model's research status must travel with every downstream result.
4. **No fabricated coverage:** missing forecasts, EO, minutes, probabilities, CTA features or covariance remain missing with an explicit reason. Missing is never converted to zero.
5. **Separate prediction, decision and field context:** forecasts estimate player outcomes; M3 turns forecasts into FPL decisions; M4 adds field-relative context and portfolio risk; M5 packages the distinct products.
6. **Reproducibility:** every weekly decision and release records the exact squad, forecast snapshots, EO snapshot, model/provider versions, rules, configuration and code version used.
7. **Sequential execution:** this blueprint does not change the five-milestone order. M1 verification remains separate; M2 continues now. M3, M4 and M5 implementation begins only after the preceding milestone is accepted.

## 2. System boundary and flow

```text
M1 — Capture, validation, immutable archive, post-GW evaluation
                    |
                    v
Forecast provider adapters
  - FPL Review (Free and Premium/Massive Data kept separate)
  - FPL Forecaster
  - FPL Lucho (served xP and Odds xP kept distinct)
  - Sideline Quant
  - FPL Cat
  - FPLRogue
  - FPL Wildcard
  - other agreed sources only when accessible and captured pre-deadline
  - Official FPL ep_next as a clearly labelled native reference
  - future: validated project models (ABC/CTA, 2PM, approved ensemble)
                    |
                    v
Canonical forecast + provenance contract
                    |
          +---------+---------+
          |                   |
          v                   v
M3 — Decision engine     M4 — Field / portfolio context
          |                   |
          +---------+---------+
                    |
                    v
M5 — Three recommendation products and versioned release
                    |
                    v
M1 — Archive release and post-GW evaluation
```

M4 enriches M3 decisions and M5 presentation; it does not replace forecast values or create a second EO source. M3 must remain usable when optional M4 fields are unavailable.

## 3. Shared forecast-provider contract

All external benchmarks and future in-house models must map into a versioned canonical schema before use.

### 3.1 Required identity and timing

Each forecast record must identify:

- season, target Gameweek and forecast horizon;
- canonical FPL player ID and, where relevant, fixture ID;
- provider name, product/tier, forecast variant and model/version identifier when supplied;
- source-generated timestamp, retrieval timestamp (UTC), official deadline and first kickoff;
- source URL/method, raw snapshot identifier and SHA-256 content hash;
- player/fixture mapping status and normalization notes;
- forecast status and missing-value reason.

Player-fixture forecasts must be aggregated to player-Gameweek only under an explicit aggregation rule. Double Gameweeks must preserve fixture-level values and uncertainty before aggregation; never treat a single-fixture value as a full-DGW forecast.

### 3.2 Forecast values and uncertainty

Fields are optional unless the provider actually publishes them:

- expected FPL points at fixture and/or player-Gameweek grain;
- expected minutes and appearance probability;
- points distribution or quantiles;
- probabilities for scoring events / points thresholds (with event definitions);
- provider uncertainty, confidence intervals or scenario outputs;
- fixture and team context.

Preserve the provider's original fields and units alongside normalized fields. Do not reverse-engineer a provider's model or label a reconstructed number as its published forecast.

### 3.3 Eligibility and freshness

A forecast can be used for a deadline decision only if its capture timestamp is before the official deadline and its variant/horizon is identified. Snapshots captured after deadline are ineligible for pre-deadline recommendations. Multiple pre-deadline captures are separate horizons; do not overwrite earlier frozen snapshots.

Every output carries source coverage and freshness. Stale, incomplete, retrospective-only or research-only records remain visibly labelled and cannot silently enter the validated forecast set.

### 3.4 Benchmark source registry

The benchmark registry is governed by `EXTERNAL_FPL_BENCHMARK_PROTOCOL.md`. Keep these sources and variants separate:

- FPL Review Free;
- FPL Review Premium / Massive Data Model;
- FPL Forecaster;
- FPL Lucho served xP and Odds xP as distinct variants;
- Sideline Quant;
- FPL Cat;
- FPLRogue;
- FPL Wildcard;
- Official FPL `ep_next` as a native reference, not as an external independent provider.

Additional sources (for example Fantasy Football Scout, Fantasy Football Pundit, Fantasy Football Fix, Fantasy Football Hub, The Fantasy Tool, Football Meets Data, or FPL Form) enter the registry only after actual player-level pre-deadline capture, terms/access review and provenance validation. Their presence on a website alone does not make them an active benchmark.

The initial market-derived benchmark track remains FPL Forecaster and FPL Lucho. Do not substitute generic bookmaker models or create a project-side odds-to-FPL-points conversion in place of their actual published outputs.

## 4. M3 — Decision engine architecture

**Purpose:** Convert forecast inputs and an explicit manager state into legal, explainable FPL actions.

### 4.1 Inputs

- canonical forecast snapshot(s) from eligible benchmark providers or a validated project model;
- official FPL player, team, position, price, fixture and deadline data;
- explicit timestamped 15-player squad snapshot;
- bank, squad value, purchase prices where available, free transfers, transfer history, chips and chip state;
- legal formation and bench constraints;
- manager's stated risk preference and planning horizon;
- optional M4 field/portfolio context, with provenance and validation state.

If required squad state is missing, stale or inconsistent, the engine must stop with an explicit incomplete-input status. It must not invent a squad or silently optimize a generic one.

### 4.2 Decision functions

M3 is responsible for:

1. transfer-in/out candidates, alternatives and hold/roll decisions;
2. transfer legality: budget, selling price, squad composition, position and three-per-team limits;
3. starting XI and legal formation;
4. bench order and autosub implications;
5. captain and vice-captain;
6. chip-aware decisions when chip rules are implemented and validated;
7. multi-transfer and multiweek planning when those capabilities pass their own acceptance tests;
8. explanation of expected gain, uncertainty, opportunity cost, constraints and assumptions.

The engine must distinguish forecast value from decision utility. A higher projected-points player is not automatically the best transfer if price, transfer cost, squad structure, horizon or alternatives change the decision.

### 4.3 Provider handling

- Keep provider forecasts and variants separately addressable.
- Do not silently select one provider or average forecasts with arbitrary weights.
- A benchmark consensus/ensemble may be offered only after its inclusion rules, calibration, missingness treatment and weights are justified on chronological historical evidence. Until then, provider-specific decision runs remain available and the chosen forecast source is explicit.
- When the project's model is approved in M2, register it through the same provider interface. Preserve the benchmark-based run as a comparator.
- Never mix model versions or forecast horizons inside one decision run without an explicit documented policy.

### 4.4 M3 outputs

A versioned decision object containing:

- recommended transfers and ranked alternatives;
- hold/roll recommendation;
- legal starting XI, formation and bench order;
- captain and vice-captain;
- projected squad points and horizon;
- uncertainty and sensitivity to provider/model choice;
- constraints checked and rejected alternatives/reasons;
- exact input snapshot IDs, provider variants, rules/config version and engine version;
- validation status and warnings.

### 4.5 M3 acceptance gates

- legal squad and transfer constraint tests, including boundary cases;
- deterministic replay from identical frozen inputs;
- sensitivity tests when bank, transfers, squad or constraints change;
- no-squad-input and personal-squad isolation tests for general-market operations;
- exact input/provenance traceability;
- benchmark-provider comparison on identical player-GW cohorts;
- retrospective decision backtests using only forecasts actually captured before deadlines;
- post-GW evaluation of realized points, transfer opportunity cost and decision regret;
- no promotion based solely on predicted points accuracy.

## 5. M4 — Field-relative and portfolio intelligence

**Purpose:** Explain how the manager's decisions differ from relevant competitors and quantify portfolio exposure/risk without manufacturing ownership or covariance.

### 5.1 Inputs

- M3 candidate decisions and squad exposure;
- existing LiveFPL effective-ownership (EO) snapshots, preserving rank cohort, sample size, timestamp, deadline and coverage;
- official FPL ownership only as a separately named metric; never relabel global ownership as EO;
- player forecasts and distributions from the selected eligible provider;
- player-level covariance or joint outcome samples only when supported by validated data;
- manager's target rank / risk preference if explicitly supplied.

The project consumes the existing LiveFPL EO system as the field reference. It does not create a competing EO estimator. Rank cohorts and sample coverage must remain explicit.

### 5.2 Field-relative measures

- owned-player exposure versus sampled field EO;
- captaincy and vice-captain exposure;
- scoring exposure, including chip effects when applicable;
- differential and template concentration;
- rank-cohort-specific exposure gaps;
- coverage and sampling uncertainty;
- scenario comparisons showing how choices may gain or lose relative to the field.

EO is an exposure measure, not a points forecast or a guaranteed rank forecast. Missing player EO must remain missing; incomplete coverage must be surfaced rather than filled with zero.

### 5.3 Portfolio risk and CoVar

CoVar/covariance belongs to the portfolio layer, not to an individual player score.

- Begin with transparent exposure/concentration summaries that do not require covariance.
- Add covariance, correlated variance and scenario simulation only after player-level coverage, stability, shrinkage, calibration and out-of-sample decision utility pass documented gates.
- Use the selected provider's compatible player outcome distributions; do not combine incompatible forecast variants or time horizons.
- Report uncertainty in covariance estimates and sensitivity to sample window / shrinkage.
- Never activate CoVar in production merely because a matrix can be calculated.
- Retain an auditable no-CoVar fallback.

### 5.4 M4 outputs

- player-by-player owned exposure versus field EO;
- captaincy/scoring-exposure differences;
- rank-cohort comparison and sample coverage;
- template/differential concentration;
- validated portfolio variance/CoVar and scenario summaries when eligible;
- uncertainty, data-quality warnings and source timestamps.

### 5.5 M4 acceptance gates

- EO source, cohort and timestamp provenance checks;
- coverage and missingness tests, including fail-closed incomplete cohorts;
- correct ownership/captaincy/chip exposure arithmetic;
- rank-cohort sensitivity and sample-uncertainty reporting;
- covariance stability and out-of-sample calibration tests before use;
- demonstrate incremental decision utility over the no-CoVar baseline;
- preserve a no-EO / no-CoVar degraded mode with explicit status.

## 6. M5 — Three recommendation products

M5 publishes three distinct, versioned products. They share the canonical data and release infrastructure but must not be collapsed into one blended ranking.

### Product 1 — Conventional squad-specific recommendations

- Uses the manager's actual, timestamped squad and constraints.
- Initially powered by eligible conventional FPL benchmark forecasts through M3.
- Uses M4's existing LiveFPL field reference where available.
- Produces transfers, hold/roll, starting XI, formation, bench, captaincy and multiweek advice as each capability is validated.
- Later can use the project's validated forecast model through the same interface, with benchmark-based comparisons retained.

### Product 2 — CTA-informed squad-specific recommendations

- Uses the same actual squad snapshot and legal constraints as Product 1.
- Uses conventional benchmark forecasts as the initial points baseline.
- Adds CTA/ABC information only when the relevant features and model outputs pass M2 evidence, point-in-time, coverage and incremental-value gates.
- Until those gates pass, CTA remains explicitly `RESEARCH_ONLY / NOT_IN_BASELINE`, with zero decision weight. The product may be scaffolded, but it must not be marketed or released as CTA-informed actionable advice when CTA has no validated influence.
- Once approved, record exactly which CTA features/model version changed the decision and retain the benchmark-only counterfactual.

### Product 3 — Squad-independent CTA player rankings

- Does not read or depend on the manager's personal squad, bank, transfers or rank.
- Provides general player rankings and contextual CTA explanations for the eligible player universe.
- Can be scaffolded now with the same forecast-provider and release contracts, but actionable CTA rankings remain unavailable until the CTA model passes M2 validation.
- When released, distinguish CTA signal/ranking from expected-points ranking; show benchmark forecasts and coverage as context rather than pretending they are CTA outputs.
- Enforce an invariance test: identical inputs produce identical rankings regardless of any personal-squad state.

### Release contract

Each weekly release records:

- season, Gameweek, publication time and deadline;
- product identifier and schema version;
- exact player/squad/fixture snapshot IDs;
- forecast provider, product/tier, variant, model version, capture time and hashes;
- EO snapshot/cohort metadata where used;
- M3/M4 engine versions and configuration;
- validation/promotion state, coverage, missingness and warnings;
- recommendation output and concise decision explanations;
- links/IDs to immutable M1 archive records and later post-GW evaluation.

A release is immutable. Corrections create a new version with a reason; they do not overwrite the original recommendation.

## 7. Model-provider transition plan

The transition from benchmark-first to project-model-powered operation is an input-provider change, not a downstream redesign.

### Initial state

- External FPL benchmark captures power the canonical forecast contract.
- Official FPL `ep_next` remains a labelled native reference.
- M3 decisions are provider-specific unless a validated benchmark ensemble is available.
- M4 consumes existing LiveFPL EO; CoVar stays disabled until its gates pass.
- M5 Product 1 can operate on eligible benchmark forecasts. Products 2 and 3 remain scaffolded/research-gated until CTA is validated.

### Transition gate

A project model can enter the eligible provider registry only after M2 documents:

- multi-season chronological out-of-sample evidence;
- comparisons against the agreed external benchmark set on exact common cohorts;
- coverage and source-vintage / point-in-time integrity;
- calibration and uncertainty quality;
- ranking and decision-utility results;
- paired uncertainty and season stability;
- explicit promotion decision and model version.

ABC/CTA and 2PM are judged separately. A result that beats one internal candidate but not the agreed benchmark standard does not qualify by itself. A hybrid must pass its own matched ablation and promotion gates.

### After approval

- Add the approved model as a provider with its own version and provenance.
- Run benchmark and project-model decision tracks side by side for a defined shadow period.
- Compare recommendations and post-GW outcomes on identical deadlines and squads.
- Promote only through a recorded decision; preserve benchmark fallback and rollback.
- Do not rewrite historical recommendations with newer model versions.

## 8. Relationship to the five milestones

| Milestone | Execution status | What this blueprint establishes |
|---|---|---|
| M1 — Delivery backbone | Awaiting scheduled verification | Immutable input/output archive and post-GW evaluation remain the system foundation. |
| M2 — Model layer | Active | Canonical forecast-provider contract and external benchmark comparison requirements for downstream integration. |
| M3 — Decision engine | Design only; implementation not started | Inputs, decisions, outputs and acceptance gates. |
| M4 — Field/portfolio intelligence | Design only; implementation not started | LiveFPL EO consumption, rank cohorts, exposure, CoVar gates and fallback. |
| M5 — Recommendation products | Design only; implementation not started | Three distinct products, release contract and model transition. |

This is a design artifact, not evidence that M3–M5 have been implemented or validated. Work continues sequentially: finish M2, then implement and validate M3, M4 and M5 in order.

## 9. Existing repository assets to reuse

Before implementation, inspect and extend rather than replace:

- `DUAL_RECOMMENDATION_ARCHITECTURE.md` — existing general-market / personal-squad separation and engine contracts;
- `EXTERNAL_FPL_BENCHMARK_PROTOCOL.md` — agreed provider registry, capture and scoring policy;
- `PERSONAL_TEAM_FIELD_COMPARISON.md` — existing LiveFPL EO field comparison;
- `CTA_FPL_DECISION_INTEGRATION_STATUS.md` — current CTA integration and promotion boundaries;
- existing Python/JavaScript general-market and personal-squad engines and parity tests;
- M1 capture, archive and post-GW evaluation workflows.

Any implementation proposal must identify which existing asset it extends and include regression tests for its current behaviour.

## 10. Open design questions to resolve during the relevant milestone

These are deliberately not decided by assumption in this blueprint:

- benchmark eligibility and source-specific freshness thresholds by forecast horizon;
- whether a benchmark consensus is justified, and its validation-derived weights;
- transfer hit-cost and multiweek objective configuration;
- exact decision-utility and regret definitions;
- rank-cohort selection and EO sampling uncertainty;
- covariance estimator, shrinkage and minimum sample requirements;
- release cadence and correction/version policy;
- which CTA outputs, if any, pass M2 promotion and become eligible for Products 2 and 3.

Each question must be resolved with evidence and recorded before the corresponding implementation gate.