# 2PM Transformer — Dastan 286-Feature Adaptation Decision

**Decision date:** 2026-11-23  
**Status:** Approved input-foundation direction; feature and sequence gates remain open  
**Model:** Independent, paper-first 2PM player-points forecaster  
**Governing paper:** Wiechno, Duch and Bartosik (2026), *Modeling Fantasy Premier League Player Performance with a Two-Component Poisson Mixture Transformer*, ICAART 2026, DOI: 10.5220/0014358000004052.

## 1. Decision

For the new 2PM implementation, replace the paper's original 116-per-match input-feature contract with the project's **Dastan 286-feature contract as the candidate input foundation**.

This is a deliberate, documented adaptation of the paper—not an exact reproduction of its original input representation or dataset.

The Dastan feature set is a candidate 286-column input contract, not yet a frozen 2PM training schema. All 286 columns must pass the feature-level semantic, point-in-time, target-leakage, coverage, missingness and sequence-compatibility audit before the 2PM schema is frozen. A feature that fails those checks must be excluded or transformed under a separately versioned, justified adaptation; the count must not be forced to remain 286 at the expense of validity.

## 2. What remains governed by the paper

Retain the paper's core predictive architecture and objective:

- Encoder-only Transformer.
- Two-component Poisson-mixture output: mixture probability (p) and positive rates (lambda_1,lambda_2).
- Analytic mixture expectation and variance.
- Mixture negative log-likelihood.
- Training-only maximum-likelihood initialization of component rates.
- Chronological train/validation/test separation.
- Strict target and temporal leakage prevention.
- Transparent treatment of negative FPL point totals, preserving original outcomes and transformation flags.

The paper's five-previous-played-match sample construction and maximum 21-day inter-observation gap remain the reference design principles. Their implementation with Dastan's engineered rolling features is an explicit open adaptation item; do not claim that the Dastan frame itself already supplies five raw match-observation vectors.

## 3. Dastan feature contract evidence

The audited CTA schema artifact identifies:

- Schema version: `1.0.0`.
- Feature count: 286 ordered numeric columns.
- Component label: `dastan_p60_minutes_adapter`.
- Upstream project: `qazybekb/smartplayfpl-dastan`.
- Upstream reconstruction commit: `758db9247e8b3a9a870c991064f74d8339d61cd0`.
- Upstream production artifact source commit recorded in the schema: `081566ac76af582588e1a9f01d125e90dff90b9b`.
- CTA schema artifact inspected at repository commit `78b06b80a9adfa96b5b7691296b70b10512ee0e3`, blob `053f499332f7e6eab6e7046bf4f0e847e3b57d1f`.

The 286 columns are grouped as follows:

| Family | Count | Description |
|---|---:|---|
| Player rolling | 115 | FPL and Understat player metrics across rolling windows |
| Own-team rolling | 60 | Understat team metrics and league-rank context |
| Opponent rolling/context | 61 | Opponent team metrics and rank context |
| Availability history | 9 | Prior appearance, 60+ minute appearance and minutes rates |
| Dastan engineered/context | 32 | Defensive contributions, starts, rest/congestion and opponent allowance |
| Pre-deadline FPL projection | 1 | `ar_ep_next` |
| Flat context | 5 | Home flag, league rank, value, selected percentage and transfer balance |
| Pre-deadline availability | 3 | Status risk, chance of playing and news-presence signals |
| **Total** | **286** | |

The exact ordered column list is held in the pinned schema artifact, not recreated manually in this decision record. The source inventory and feature schema are engineering evidence, not proof that every feature is suitable for 2PM.

## 4. Important differences from the paper's original data

The Dastan frame is materially different from the paper's 116-feature match input:

- Dastan rows are at player-fixture grain.
- The 286 columns are engineered, deadline-anchored rolling/context features, not 286 raw event statistics for one match.
- Rolling windows overlap (including 1, 3, 5, 10 and 38-match windows).
- The frame combines player, team, opponent, availability, market and pre-deadline snapshot information.
- The published Dastan frame covers EPL seasons 2020/21–2025/26, rather than the paper's six-league 2017/18–2024/25 dataset.
- The Dastan feature schema was created for a minutes model. Its upstream model outputs and weights are not part of 2PM.

Therefore:
1. Do not describe this as an exact 2PM paper reproduction.
2. Do not pass the 286-column row directly into the old five-match sequence code.
3. Do not import Dastan minutes or points prediction heads, weights, preprocessing state, calibration or model outputs into 2PM.
4. Do not assume all 286 columns are available in every historical deadline vintage.
5. Do not treat a row's player-fixture grain as proof that it is an actual player appearance.

## 5. Source-semantics audit and high-priority risks

The pinned upstream source-code inspection is recorded in `2PM_DASTAN_SOURCE_SEMANTICS_AUDIT.md`. A critical refinement is now confirmed: Dastan's `assert_deadline_anchored` checks only selected prefixes and excludes all `opp_*` columns and the direct rank columns; its per-player/Gameweek anchor is not an independent proof that every feature was reconstructed at the official deadline. The wider kickoff-relative team/opponent/defensive-allowance/congestion families also require event-level reconstruction. This is a structural guarantee gap, not yet a quantified row-level leak. It identifies potential double-Gameweek leakage in the unanchored `opp_*` and standalone rank fields, unverified timestamp semantics for `value`/`selected`/`transfers_balance`, historical Understat identity corrections, and season-limited defensive-stat coverage. These are mandatory admission checks; none is considered cleared by the existence of the released feature frame.

## 6. Sequence representation — mandatory design gate

The paper's five previous played matches are observations in a temporal sequence. Dastan's 286-column rows are deadline snapshots for target player-fixtures. Those are not interchangeable objects.

Before implementing the 2PM sequence builder, establish and document:

1. What constitutes one eligible historical player-match observation, using actual fixture participation and minutes rather than calendar Gameweeks.
2. How a 286-feature vector is constructed for each sequence position, including its exact as-of timestamp.
3. Whether each token represents a pre-match state, a post-match state, or a separately reconstructed match-observation vector.
4. How the latest completed match's information becomes available to the target forecast without leaking any later event or snapshot.
5. How same-Gameweek double fixtures, blank Gameweeks, postponed fixtures, player transfers and gaps over 21 days are handled.
6. Whether repeated rolling windows across five tokens create unacceptable redundancy or unstable representation.
7. Whether target-specific context fields (opponent, home/away, target deadline, price/ownership, `ep_next`, status/news) belong in every token, only a target-context token, or a separate context path.

The sequence builder must be new and independent. The legacy 2PM sequence builder is frozen and prohibited. The existing Dastan/CTA five-Gameweek feature builder is not automatically reusable as a historical five-played-match sequence builder.

**No sequence design is approved by this record.** The first implementation task is to resolve this design using the audited raw source tables and temporal semantics. If a defensible five-match sequence cannot be built from the Dastan representation, return with a concrete alternative for approval rather than silently changing the paper's sequence length or pretending that a single row is a five-match sequence.

## 7. Feature-by-feature admission audit

Create a versioned 286-row register containing, at minimum:

- exact schema column and ordinal;
- family and intended meaning;
- source table/provider and source commit or snapshot;
- formula and rolling window;
- row grain and entity key;
- observation period and as-of timestamp;
- availability at each historical target deadline;
- target leakage risk and same-fixture/same-Gameweek safeguards;
- source rights and retention status;
- missingness semantics (`-1` snapshot sentinel versus residual `0` fill versus genuine zero);
- historical coverage and mapping coverage;
- sequence-token suitability;
- decision: `ADMIT`, `EXCLUDE`, or `HOLD`, with rationale.

Pay particular attention to these groups:

- **Past FPL points and outcomes:** permissible only as completed historical observations; never include the target fixture's result in its own inputs.
- **Understat player/team metrics:** verify player/team identity, match alignment, source vintage and availability before each target deadline.
- **Defensive-contribution/CBIT/recovery/tackle features:** audit the season in which each source statistic became available; do not backfill newer statistics into earlier seasons as if observed.
- **Price, selected percentage and transfer balance:** require archived pre-deadline snapshots for historical training.
- **`ar_ep_next` and `sig_*`:** require matching target-Gameweek metadata, a deadline-consistent snapshot, and a capture timestamp before the deadline. Current bootstrap values cannot be substituted for historical vintages.
- **League ranks and rest/congestion:** reconstruct strictly from information available before the target fixture and validate the exact upstream definitions.
- **Missing values:** preserve the upstream two-stage semantics—snapshot absence sentinel `-1.0`, then residual NaN fill `0.0`—only where source provenance proves that those semantics apply. Do not globally impute all unavailable features to zero.

## 8. Dataset freshness and player identity

The pinned six-season Dastan release ends in 2025/26 and does not contain 2026/27 player-fixture feature rows. Its 2026/27 roster/mapping snapshot is separate and must be refreshed and hashed before current-season use.

The immutable historical assignments used to reproduce Dastan retain two documented incorrect Understat identities. The 2PM rebuild must apply the evidence-backed corrected mapping to the historical assignment intervals and rebuild player rolling histories; it must not reuse the frozen assignments unchanged or merely patch final feature rows. The exact evidence and requirements are in `2PM_DASTAN_DATASET_AND_IDENTITY_READINESS.md`.

## 9. Data and rights constraints

The upstream Dastan repository's MIT software licence does not grant rights to the underlying FPL, Understat or other provider datasets. The relevant source terms, retention rights and model-training permissions must be checked separately.

The historical frame's existence does not by itself prove:
- that every row/feature has an archived as-of vintage;
- that all 286 features are complete across all seasons;
- that source corrections can be reproduced;
- that every historical market/snapshot feature is available;
- or that source data may be retained and used for this model.

Keep source hashes, acquisition manifests, feature-schema version and row-level provenance with every training snapshot.

## 10. Build order and gates

1. Pin the exact 286-column schema and source inventory.
2. Recover the canonical Dastan raw player-match, team-match and pre-deadline snapshot source contracts; build a corrected historical identity assignment table and refresh current-season mappings.
3. Build a corrected-identity historical candidate frame and a separately pinned 2026/27 candidate frame; build the 286-row semantic and point-in-time admission register.
4. Resolve sequence-token construction and the five-played-match/21-day policy.
5. Establish lawful historical target labels and source rights.
6. Freeze a versioned 2PM adaptation schema only after the above gates pass.
7. Implement the new independent sequence dataset and clean 2PM model.
8. Validate leakage controls, schema, missingness, chronological splits and forecast interface before any training/evaluation claims.

Until these gates are passed, the state is `DASTAN_286_ADAPTATION_AUDIT_IN_PROGRESS`; no training, production use, data promotion or M3 integration is authorized.

## 11. Boundaries unchanged

- The 2PM model predicts player FPL points only.
- M3 remains the integrated decision engine; M4 owns recommendation products.
- The output product remains **2PM Squad Recommendations**.
- The new model remains research-only, with production weight 0 and `production_eligible=false`.
- The discarded legacy 2PM implementation remains frozen and is not a dependency.
- Do not merge PRs without explicit user approval.
- M2 forecast evaluation and M4 recommendation-product evaluation remain deferred until the upcoming Gameweek's official scores are available.

## 12. Governing decision

Use Dastan's 286-feature contract as the candidate input foundation for a clearly labelled 2PM architecture adaptation. Preserve the paper's two-component Poisson-mixture Transformer core. Complete the feature and sequence audits before freezing the schema or implementing training. Do not reuse Dastan's predictive models or the legacy 2PM implementation.
