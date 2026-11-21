# M3 squad recommendation: field-relative and CoVar integration

## Architectural decision

Field-Relative Analysis and CoVar are components of the personal-squad recommendation path. They are not a separate recommendation destination, detached dashboard, or post-processing product.

The conventional and CTA-informed squad-specific products consume the same squad-bound decision context. The squad-independent General CTA market product remains isolated from manager-specific data.

## Required personal-squad flow

1. **Forecast input:** accept eligible, provider-labelled player-Gameweek forecasts through the shared provider router. Preserve provider identity, native variant, snapshot hash, target Gameweek, point-in-time status and coverage. Do not average or blend providers without a separately approved, evidence-based policy.
2. **Conventional EV baseline:** calculate the legal starting-XI-first hold and transfer alternatives from the manager's frozen squad, bank, free transfers, formation, captain and vice-captain. Preserve the existing transfer legality, affordability and emergency-bench constraints.
3. **Field-relative context:** join a separate, timestamped pre-deadline field evidence artifact. Surface ownership/EO, rank-cohort exposure, sample size, coverage, missingness and uncertainty beside the same hold and transfer alternatives. Keep observed EO distinct from poll-implied estimates and label provisional estimates explicitly.
4. **Portfolio/CoVar context:** attach the available CoVar view to those same alternatives. The current historical covariance proxy may describe starting-XI variance, covariance contribution and EV/variance trade-offs. Prospective joint-scenario analysis may additionally compare explicit sampled manager-pick portfolios. Marginal EO must never be used to reconstruct joint manager portfolios.
5. **Integrated recommendation:** return one squad-specific recommendation record with the conventional EV choice intact and field-relative/CoVar evidence attached to the corresponding hold and transfer candidates. Show the evidence, uncertainty, limitations and EV opportunity cost together; do not send the user to a separate analytics destination.

## Safety and decision authority

- CoVar remains research-only: `decision_weight=0` and `production_eligible=false`. It may explain and compare candidates, but cannot silently change the EV ranking, transfer action, starting XI, formation, captaincy or vice-captaincy.
- Field-relative evidence is contextual and must not override transfer legality, affordability, deadline or frozen-decision integrity.
- Missing, stale, post-deadline or insufficiently covered field/CoVar evidence is explicitly marked unavailable; it must not be fabricated or imputed.
- The conventional EV baseline must remain reproducible when field or CoVar inputs are absent. Optional evidence failure must not mutate the baseline decision.
- Free Hit analysis is used only when explicitly selected; regular Gameweek is the default.
- Starting XI is the primary objective. Bench players are emergency cover; no routine rotation or bench-to-bench upgrade is recommended unless a legal move improves the starting XI.
- General CTA market rankings must not receive squad, bank, transfer, formation, rank, personal-risk or personal-preference fields.

## Evidence contract and acceptance tests

Every attached field/CoVar artifact must bind to the exact decision candidate and forecast context. At minimum retain:

- season, target Gameweek, official deadline and timezone-aware capture/as-of timestamps;
- provider forecast snapshot ID, provider/product/variant and model version;
- field artifact ID, source, sample/cohort definition, row coverage and uncertainty metadata;
- CoVar method/version, covariance or scenario-set ID, portfolio IDs where applicable, provenance and eligibility status;
- candidate identity (hold or exact transfer-out/transfer-in pair), formation and starting-XI binding.

Required regression coverage:

1. Field-relative and CoVar evidence appears inside the personal-squad recommendation result for the matching hold/transfer alternatives.
2. Missing or stale evidence is withheld with a reason and does not change the conventional EV recommendation.
3. Mismatched forecast snapshot, Gameweek, candidate IDs, deadline or model version is rejected.
4. CoVar cannot alter ranking, transfer, XI, formation or captaincy while decision weight is zero.
5. No marginal-EO-to-joint-portfolio reconstruction is permitted.
6. General CTA market requests reject personal-squad and field-portfolio identifiers.
7. Provider identity and native forecast variant remain visible; no silent cross-provider blend is introduced.

## Milestone placement

This integration belongs to **M3 — Integrated Decision Engine**. It is part of the squad-specific decision workflow. **M4 — Release the Three Recommendation Products** consumes the completed, release-gated interfaces; it does not own a detached field/CoVar analytics product.

Formal M2 forecast evaluation and M4 recommendation-product evaluation remain deferred until the upcoming Gameweek's official scores. That deferral does not block M3 interface and integration engineering.
